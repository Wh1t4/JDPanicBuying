import base64
import json
import os
import shutil
import sqlite3
import tempfile
from pathlib import Path
from typing import Any

import requests
from requests.cookies import create_cookie
from requests.cookies import RequestsCookieJar


def _browser_roots() -> list[tuple[str, Path]]:
    local_app_data = Path(os.environ["LOCALAPPDATA"])
    return [
        ("chrome", local_app_data / "Google" / "Chrome" / "User Data"),
        ("edge", local_app_data / "Microsoft" / "Edge" / "User Data"),
    ]


def _load_encryption_key(local_state_path: Path) -> bytes:
    import win32crypt

    state = json.loads(local_state_path.read_text(encoding="utf-8"))
    encrypted_key_b64 = state["os_crypt"]["encrypted_key"]
    encrypted_key = base64.b64decode(encrypted_key_b64)[5:]
    return win32crypt.CryptUnprotectData(encrypted_key, None, None, None, 0)[1]


def _copy_cookie_db(cookie_db: Path) -> Path:
    fd, temp_name = tempfile.mkstemp(prefix="jd-cookie-db-", suffix=".sqlite")
    os.close(fd)
    temp_db = Path(temp_name)
    shutil.copy2(cookie_db, temp_db)
    return temp_db


def _decrypt_cookie_value(encrypted_value: bytes) -> str:
    import win32crypt

    try:
        if encrypted_value.startswith(b"v10") or encrypted_value.startswith(b"v11"):
            raise ValueError("requires aes decrypt")
        return win32crypt.CryptUnprotectData(encrypted_value, None, None, None, 0)[1].decode("utf-8", errors="ignore")
    except Exception:
        return ""


def _decrypt_cookie_value_with_key(encrypted_value: bytes, key: bytes) -> str:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    if encrypted_value.startswith(b"v10") or encrypted_value.startswith(b"v11"):
        nonce = encrypted_value[3:15]
        ciphertext = encrypted_value[15:]
        try:
            return AESGCM(key).decrypt(nonce, ciphertext, None).decode("utf-8", errors="ignore")
        except Exception:
            return ""
    return _decrypt_cookie_value(encrypted_value)


def _extract_jd_cookies(cookie_db: Path, key: bytes) -> list[dict[str, Any]]:
    temp_db = _copy_cookie_db(cookie_db)
    conn = sqlite3.connect(str(temp_db))
    try:
        cur = conn.cursor()
        cur.execute(
            """
            select host_key, name, path, expires_utc, is_secure, is_httponly, encrypted_value
            from cookies
            where host_key like '%jd.com%'
            """
        )
        rows = cur.fetchall()
    finally:
        conn.close()
        try:
            temp_db.unlink(missing_ok=True)
        except Exception:
            pass
    cookies: list[dict[str, Any]] = []
    for host_key, name, path, expires_utc, is_secure, is_httponly, encrypted_value in rows:
        value = _decrypt_cookie_value_with_key(encrypted_value, key)
        if not value:
            continue
        cookies.append(
            {
                "host_key": host_key,
                "name": name,
                "value": value,
                "path": path or "/",
                "expires_utc": expires_utc,
                "is_secure": bool(is_secure),
                "is_httponly": bool(is_httponly),
            }
        )
    return cookies


def _probe_login(cookies: list[dict[str, Any]]) -> bool:
    session = requests.Session()
    session.cookies = to_requests_cookiejar(cookies)
    response = session.get(
        "https://order.jd.com/center/list.action",
        params={"rid": "1"},
        allow_redirects=False,
        timeout=15,
    )
    return response.status_code == 200


def to_requests_cookiejar(cookies: list[dict[str, Any]]) -> RequestsCookieJar:
    jar = RequestsCookieJar()
    for item in cookies:
        jar.set_cookie(
            create_cookie(
                name=item["name"],
                value=item["value"],
                domain=item["host_key"],
                path=item["path"],
                secure=item["is_secure"],
                rest={"HttpOnly": item["is_httponly"]},
            )
        )
    return jar


def import_best_jd_cookies() -> dict[str, Any]:
    best: dict[str, Any] | None = None
    for browser_name, root in _browser_roots():
        local_state = root / "Local State"
        cookie_db = root / "Default" / "Network" / "Cookies"
        if not local_state.exists() or not cookie_db.exists():
            continue
        try:
            key = _load_encryption_key(local_state)
            cookies = _extract_jd_cookies(cookie_db, key)
            if not cookies:
                continue
            ok = _probe_login(cookies)
            candidate = {
                "browser": browser_name,
                "cookies": cookies,
                "cookie_count": len(cookies),
                "login_ok": ok,
            }
            if ok:
                return candidate
            if best is None or candidate["cookie_count"] > best["cookie_count"]:
                best = candidate
        except Exception as exc:
            message = str(exc)
            if "being used by another process" in message:
                message = "Chrome 正在运行，无法读取登录态数据库，请先关闭 Chrome。"
            best = {
                "browser": browser_name,
                "cookies": [],
                "cookie_count": 0,
                "login_ok": False,
                "error": message,
            }
    return best or {
        "browser": "",
        "cookies": [],
        "cookie_count": 0,
        "login_ok": False,
        "error": "未找到可用的 Chrome/Edge 京东 cookie。",
    }

import os
import pickle
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Dict


MANAGED_BROWSER_PORT = 9223
MANAGED_BROWSER_PROFILE_DIR = Path("D:/AI/JDPanicBuying/.codex-tasks/jd-managed-browser-profile")


def _cookie_file_path() -> str:
    cookies_dir = "./cookies/"
    if not os.path.exists(cookies_dir):
        return ""
    for name in os.listdir(cookies_dir):
        if name.endswith(".cookies"):
            return os.path.join(cookies_dir, name)
    return ""


def _load_playwright_cookies() -> list[dict[str, Any]]:
    cookie_file = _cookie_file_path()
    if not cookie_file:
        return []
    with open(cookie_file, "rb") as file_obj:
        jar = pickle.load(file_obj)

    cookies: list[dict[str, Any]] = []
    for cookie in jar:
        entry: dict[str, Any] = {
            "name": cookie.name,
            "value": cookie.value,
            "domain": cookie.domain,
            "path": cookie.path or "/",
            "secure": bool(cookie.secure),
            "httpOnly": bool(cookie._rest.get("HttpOnly")) if hasattr(cookie, "_rest") else False,
        }
        if cookie.expires:
            entry["expires"] = cookie.expires
        same_site = None
        if hasattr(cookie, "_rest"):
            same_site = cookie._rest.get("SameSite")
        if same_site in ("Lax", "None", "Strict"):
            entry["sameSite"] = same_site
        cookies.append(entry)
    return cookies


def _default_chrome_path() -> str | None:
    candidates = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return None


def _managed_login_url() -> str:
    return "https://passport.jd.com/new/login.aspx?ReturnUrl=https%3A%2F%2Ftrade.jd.com%2Fshopping%2Forder%2FgetOrderInfo.action%3FcartSplitPage%3D1"


def _playwright_cookies_to_internal(cookies: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for cookie in cookies:
        result.append(
            {
                "host_key": cookie.get("domain", ""),
                "name": cookie.get("name", ""),
                "value": cookie.get("value", ""),
                "path": cookie.get("path", "/"),
                "expires_utc": cookie.get("expires", -1),
                "is_secure": bool(cookie.get("secure")),
                "is_httponly": bool(cookie.get("httpOnly")),
            }
        )
    return result


def open_managed_browser_login() -> Dict[str, Any]:
    executable = _default_chrome_path()
    if not executable:
        return {
            "ok": False,
            "message": "本机未找到 Chrome/Edge，无法打开专用京东浏览器。",
        }

    MANAGED_BROWSER_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    args = [
        executable,
        f"--remote-debugging-port={MANAGED_BROWSER_PORT}",
        f"--user-data-dir={str(MANAGED_BROWSER_PROFILE_DIR)}",
        "--no-first-run",
        "--no-default-browser-check",
        _managed_login_url(),
    ]
    subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return {
        "ok": True,
        "message": "已打开专用京东浏览器，请在其中完成登录。",
        "port": MANAGED_BROWSER_PORT,
        "profile_dir": str(MANAGED_BROWSER_PROFILE_DIR),
    }


def import_managed_browser_cookies(timeout_seconds: float = 20) -> Dict[str, Any]:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.connect_over_cdp(f"http://127.0.0.1:{MANAGED_BROWSER_PORT}")
        except Exception:
            return {
                "browser": "managed",
                "cookies": [],
                "cookie_count": 0,
                "login_ok": False,
                "error": "专用京东浏览器未启动。",
            }

        try:
            if not browser.contexts:
                return {
                    "browser": "managed",
                    "cookies": [],
                    "cookie_count": 0,
                    "login_ok": False,
                    "error": "专用京东浏览器上下文未初始化。",
                }
            context = browser.contexts[0]
            page = context.new_page()
            page.set_default_timeout(int(timeout_seconds * 1000))
            page.goto("https://order.jd.com/center/list.action?rid=1", wait_until="domcontentloaded")
            page.wait_for_timeout(1500)
            current_url = page.url
            title = page.title()
            login_ok = "passport.jd.com/new/login.aspx" not in current_url and "欢迎登录" not in title
            cookies = _playwright_cookies_to_internal(context.cookies())
            page.close()
            return {
                "browser": "managed",
                "cookies": cookies,
                "cookie_count": len(cookies),
                "login_ok": login_ok,
                "current_url": current_url,
                "title": title,
                "error": None if login_ok else "专用京东浏览器尚未完成登录。",
            }
        finally:
            browser.close()


def _run_checkout_with_context(context, sku_id: str, quantity: int, timeout_seconds: float, submit_order: bool) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "ok": False,
        "step": "init",
        "message": "浏览器抢购未开始。",
    }
    page = context.new_page()
    page.set_default_timeout(int(timeout_seconds * 1000))

    product_url = f"https://item.jd.com/{sku_id}.html"
    page.goto(product_url, wait_until="domcontentloaded")
    page.wait_for_timeout(1500)
    final_url = page.url
    title = page.title()
    if "risk_handler" in final_url or "京东验证" in title:
        return {
            "ok": False,
            "step": "product_page",
            "message": "商品页触发京东验证，无法继续自动下单。",
            "final_url": final_url,
            "title": title,
        }

    selected_name = ""
    click_result = page.evaluate(
        """() => {
            const labels = ['立即购买', '加入购物车'];
            const nodes = Array.from(document.querySelectorAll('div,a,button,span'));
            for (const node of nodes) {
                const text = (node.innerText || node.textContent || '').trim();
                if (!labels.includes(text)) continue;
                const rect = node.getBoundingClientRect();
                const style = window.getComputedStyle(node);
                const visible = rect.width > 0 && rect.height > 0 && style.display !== 'none' && style.visibility !== 'hidden';
                if (!visible) continue;
                node.click();
                return { clicked: true, text, id: node.id || '', className: node.className || '' };
            }
            return { clicked: false };
        }"""
    )
    if not click_result.get("clicked"):
        return {
            "ok": False,
            "step": "product_page",
            "message": "商品页未找到可点击的购买入口。",
            "final_url": final_url,
            "title": title,
        }
    selected_name = click_result.get("text") or ""
    page.wait_for_timeout(2500)

    if "trade.jd.com" not in page.url:
        page.goto("https://cart.jd.com/cart_index", wait_until="domcontentloaded")
        page.wait_for_timeout(2500)
        checkout_click = page.evaluate(
            """() => {
                const nodes = Array.from(document.querySelectorAll('div,a,button,span'));
                for (const node of nodes) {
                    const text = (node.innerText || node.textContent || '').trim();
                    const rect = node.getBoundingClientRect();
                    const style = window.getComputedStyle(node);
                    const visible = rect.width > 0 && rect.height > 0 && style.display !== 'none' && style.visibility !== 'hidden';
                    if (!visible) continue;
                    if (!text.startsWith('去结算')) continue;
                    node.click();
                    return { clicked: true, text, id: node.id || '', className: node.className || '' };
                }
                return { clicked: false };
            }"""
        )
        page.wait_for_timeout(2500)
        if not checkout_click.get("clicked"):
            return {
                "ok": False,
                "step": "cart",
                "message": "购物车页未找到去结算入口。",
                "final_url": page.url,
            }

    if "login.aspx" in page.url or "欢迎登录" in page.title():
        return {
            "ok": False,
            "step": "login",
            "message": "专用京东浏览器尚未完成登录，请先点击“打开专用京东浏览器”并在其中登录。",
            "final_url": page.url,
            "title": page.title(),
        }

    if "trade.jd.com" not in page.url:
        return {
            "ok": False,
            "step": "checkout",
            "message": f"点击购买入口({selected_name})后未能进入京东结算页，请检查商品是否支持当前流程。",
            "final_url": page.url,
        }

    submit_btn = page.locator("div,button,span").filter(has_text="提交订单")
    if not submit_btn.count():
        return {
            "ok": False,
            "step": "checkout",
            "message": "已到结算页，但未找到提交订单按钮。",
            "final_url": page.url,
        }

    if not submit_order:
        result.update({
            "ok": True,
            "step": "checkout",
            "message": "已进入结算页并定位到提交订单按钮。",
            "final_url": page.url,
            "title": page.title(),
        })
        return result

    submit_btn.first.click()
    page.wait_for_timeout(3000)
    body = page.evaluate("() => document.body ? document.body.innerText.slice(0,4000) : ''")
    current_url = page.url
    if "登录" in page.title():
        return {
            "ok": False,
            "step": "submit",
            "message": "点击提交订单后登录态失效，请重新登录。",
            "final_url": current_url,
            "title": page.title(),
        }
    if current_url != final_url or any(key in body for key in ["支付", "收银台", "订单号", "微信支付", "付款"]):
        return {
            "ok": True,
            "step": "submitted",
            "message": "已点击提交订单，请继续在支付页完成后续流程。",
            "final_url": current_url,
            "title": page.title(),
        }
    if any(key in body for key in ["失败", "错误", "请重试", "提交过快"]):
        return {
            "ok": False,
            "step": "submit",
            "message": "已点击提交订单，但页面提示失败或需要重试。",
            "final_url": current_url,
            "title": page.title(),
        }
    return {
        "ok": True,
        "step": "submit",
        "message": "已点击提交订单，请检查当前页面结果。",
        "final_url": current_url,
        "title": page.title(),
    }


def run_browser_checkout(sku_id: str, quantity: int, timeout_seconds: float = 30, submit_order: bool = False) -> Dict[str, Any]:
    from playwright.sync_api import sync_playwright

    executable = _default_chrome_path()
    if not executable:
        return {
            "ok": False,
            "step": "browser",
            "message": "本机未找到 Chrome/Edge，无法执行浏览器下单流程。",
        }

    with sync_playwright() as playwright:
        if MANAGED_BROWSER_PROFILE_DIR.exists():
            try:
                browser = playwright.chromium.connect_over_cdp(f"http://127.0.0.1:{MANAGED_BROWSER_PORT}")
                try:
                    contexts = browser.contexts
                    if contexts:
                        return _run_checkout_with_context(contexts[0], sku_id, quantity, timeout_seconds, submit_order)
                finally:
                    browser.close()
            except Exception:
                pass

            browser = playwright.chromium.launch_persistent_context(
                user_data_dir=str(MANAGED_BROWSER_PROFILE_DIR),
                headless=True,
                executable_path=executable,
                viewport={"width": 1400, "height": 960},
            )
            try:
                return _run_checkout_with_context(browser, sku_id, quantity, timeout_seconds, submit_order)
            finally:
                browser.close()
                time.sleep(0.2)

        cookies = _load_playwright_cookies()
        if not cookies:
            return {
                "ok": False,
                "step": "cookies",
                "message": "本地没有可用 cookies，请先扫码登录，或打开专用京东浏览器完成登录。",
            }

        user_data_dir = tempfile.mkdtemp(prefix="jd-browser-checkout-")
        browser = playwright.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=True,
            executable_path=executable,
            viewport={"width": 1400, "height": 960},
        )
        try:
            browser.add_cookies(cookies)
            return _run_checkout_with_context(browser, sku_id, quantity, timeout_seconds, submit_order)
        finally:
            browser.close()
            time.sleep(0.2)

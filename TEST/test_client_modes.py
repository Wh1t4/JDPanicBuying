import unittest
import tempfile
import os
import pickle
from types import SimpleNamespace
from unittest.mock import Mock, patch

from Server import api
from Core.login import SpiderSession


class FakeThread:
    def __init__(self, target=None, args=(), daemon=None):
        self.target = target
        self.args = args
        self.daemon = daemon
        self.started = False

    def start(self):
        self.started = True

    def is_alive(self):
        return self.started

    def join(self, timeout=None):
        self.started = False


class FakeWaiter:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.status = "created"
        self.last_message = "任务已创建"
        self.last_error = None
        self.spider_session = None
        self.session = None
        self.qrlogin = None

    def snapshot(self):
        return {
            "sku": self.kwargs.get("skuids"),
            "status": self.status,
            "message": self.last_message,
        }


class ClientModeTests(unittest.TestCase):
    def setUp(self):
        api.glo.waiter = None
        api.glo.thread = None
        api.glo.login = False
        api.glo.login_confirmed = False
        api.glo.cookies_saved = False
        api.glo.spider_session = None
        api.glo.qrlogin = None
        api.glo.browser_report = None

    def request(self, mode):
        return {
            "mode": mode,
            "date": "2026-05-16T18:00",
            "area": "1_2_3_4",
            "skuid": "100021044189",
            "count": "1",
            "retry": "5",
            "work_count": "1",
            "timeout": "3",
        }

    @patch("Server.api.Thread", side_effect=FakeThread)
    @patch("Server.api.Waiter", side_effect=lambda **kwargs: FakeWaiter(**kwargs))
    def test_mode_1_routes_to_auto_buy_flow(self, waiter_cls, thread_cls):
        result = api.jdShopper(self.request("1"))

        self.assertTrue(result["started"])
        self.assertEqual(api.glo.thread.args, ("waitAndBuy_by_proc_pool",))

    @patch("Server.api.Thread", side_effect=FakeThread)
    @patch("Server.api.Waiter", side_effect=lambda **kwargs: FakeWaiter(**kwargs))
    def test_mode_2_routes_to_timed_buy_flow(self, waiter_cls, thread_cls):
        result = api.jdShopper(self.request("2"))

        self.assertTrue(result["started"])
        self.assertEqual(api.glo.thread.args, ("waitTimeAndBuy",))

    @patch("Server.api.import_best_jd_cookies")
    @patch("Server.api.import_managed_browser_cookies")
    @patch("Server.api._ensure_login_session")
    def test_import_browser_login_returns_clear_error_when_no_cookies_imported(self, ensure_login_session, import_managed_browser_cookies, import_best_jd_cookies):
        spider_session = Mock()
        qrlogin = Mock()
        ensure_login_session.return_value = (spider_session, qrlogin)
        import_managed_browser_cookies.return_value = {
            "browser": "managed",
            "cookies": [],
            "cookie_count": 0,
            "login_ok": False,
            "error": "专用京东浏览器尚未完成登录。",
        }
        import_best_jd_cookies.return_value = {
            "browser": "chrome",
            "cookies": [],
            "cookie_count": 0,
            "login_ok": False,
            "error": "Chrome 正在运行，无法读取登录态。",
        }

        result = api.importBrowserLogin({})

        self.assertFalse(result["login"])
        self.assertEqual(result["message"], "Chrome 正在运行，无法读取登录态。")
        self.assertEqual(result["browser"], "chrome")

    @patch("Server.api.to_requests_cookiejar")
    @patch("Server.api.import_best_jd_cookies")
    @patch("Server.api.import_managed_browser_cookies")
    @patch("Server.api._ensure_login_session")
    def test_import_browser_login_saves_imported_login_state(self, ensure_login_session, import_managed_browser_cookies, import_best_jd_cookies, to_requests_cookiejar):
        spider_session = Mock()
        spider_session.has_login_cookies.return_value = True
        qrlogin = Mock()
        qrlogin.is_login = False
        ensure_login_session.return_value = (spider_session, qrlogin)
        import_managed_browser_cookies.return_value = {
            "browser": "managed",
            "cookies": [{"name": "thor", "value": "x"}],
            "cookie_count": 1,
            "login_ok": True,
        }
        import_best_jd_cookies.return_value = {
            "browser": "chrome",
            "cookies": [{"name": "thor", "value": "x"}],
            "cookie_count": 1,
            "login_ok": True,
        }
        to_requests_cookiejar.return_value = Mock()

        result = api.importBrowserLogin({})

        self.assertTrue(result["login"])
        spider_session.replace_cookies_and_save.assert_called_once()
        self.assertIn("managed", result["browser"])
        self.assertIn("managed", result["message"])
        import_best_jd_cookies.assert_not_called()

    @patch("Server.api.openManagedBrowserLogin")
    def test_open_managed_browser_login_returns_success_message(self, open_managed_browser_login):
        open_managed_browser_login.return_value = {
            "ok": True,
            "message": "已打开专用京东浏览器，请在其中登录。",
            "port": 9223,
        }

        result = api.openBrowserLogin({})

        self.assertTrue(result["ok"])
        self.assertEqual(result["port"], 9223)
        self.assertIn("专用京东浏览器", result["message"])

    @patch("Server.api.import_managed_browser_cookies")
    def test_managed_browser_status_reflects_login_state(self, import_managed_browser_cookies):
        import_managed_browser_cookies.return_value = {
            "browser": "managed",
            "cookies": [{"name": "thor", "value": "x"}],
            "cookie_count": 1,
            "login_ok": True,
            "current_url": "https://order.jd.com/center/list.action?rid=1",
            "title": "我的京东--我的订单",
            "error": None,
        }

        result = api.managedBrowserStatus({})

        self.assertTrue(result["ok"])
        self.assertTrue(result["login"])
        self.assertEqual(result["browser"], "managed")
        self.assertEqual(result["cookie_count"], 1)

    def test_spider_session_loads_newest_cookie_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            old_path = os.path.join(temp_dir, "old.cookies")
            new_path = os.path.join(temp_dir, "new.cookies")
            with open(old_path, "wb") as file_obj:
                pickle.dump(["old"], file_obj)
            with open(new_path, "wb") as file_obj:
                pickle.dump(["new"], file_obj)
            os.utime(old_path, (1, 1))
            os.utime(new_path, (2, 2))

            session = SpiderSession()
            session.cookies_dir_path = temp_dir + os.sep
            loaded = []
            session.set_cookies = lambda cookies: loaded.append(cookies)

            self.assertTrue(session.load_cookies_from_local())
            self.assertEqual(loaded[-1], ["new"])


if __name__ == "__main__":
    unittest.main()

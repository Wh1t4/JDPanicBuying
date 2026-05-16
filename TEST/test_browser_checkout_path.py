import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from Core.spider import Waiter


class BrowserCheckoutPathTests(unittest.TestCase):
    def make_waiter(self):
        waiter = Waiter.__new__(Waiter)
        waiter.skuids = "100021044189"
        waiter.timeout = 5
        waiter.user_agent = "ua"
        waiter.status = "created"
        waiter.last_message = ""
        waiter.last_error = None
        waiter.last_check_time = None
        waiter.last_stock_state = None
        waiter.stop_requested = False
        waiter.retry = 1
        waiter.count = 1
        waiter.auto_submit = False
        waiter.random_time = 1
        waiter.sku_title = "test sku"
        waiter.manual_purchase_url = lambda: "https://item.jd.com/100021044189.html"
        return waiter

    def test_product_page_falls_back_to_browser_probe_when_validation_page_detected(self):
        waiter = self.make_waiter()
        waiter.session = Mock()
        waiter.session.get.return_value = SimpleNamespace(
            text="京东验证",
            content=b"<html><head><title>\xe4\xba\xac\xe4\xb8\x9c\xe9\xaa\x8c\xe8\xaf\x81</title></head></html>",
            url="https://cfe.m.jd.com/privatedomain/risk_handler/test",
        )
        waiter.fail_monitor = Mock()
        waiter.browser_probe_stock = Mock(return_value=True)

        result = Waiter.get_stock_from_product_page(waiter, waiter.skuids)

        self.assertTrue(result)
        waiter.browser_probe_stock.assert_called_once_with(waiter.skuids)
        waiter.fail_monitor.assert_not_called()

    def test_buy_prefers_browser_checkout_flow(self):
        waiter = self.make_waiter()
        waiter.browser_buy = Mock(return_value=True)
        waiter.cancel_select_all_cart_item = Mock()
        waiter.cart_detail = Mock(return_value={})
        waiter.add_item_to_cart = Mock(return_value=True)
        waiter.get_checkout_page_detail = Mock(return_value="risk")
        waiter.submit_order = Mock(return_value=True)

        result = Waiter.buy.__wrapped__(waiter)

        self.assertTrue(result)
        waiter.browser_buy.assert_called_once()

    def test_wait_and_buy_by_proc_pool_runs_browser_buy_directly(self):
        waiter = self.make_waiter()
        waiter.work_count = 1
        waiter.browser_buy = Mock(return_value=True)
        waiter.qrlogin = SimpleNamespace(is_login=True)

        result = Waiter.waitAndBuy_by_proc_pool(waiter)

        self.assertTrue(result)
        waiter.browser_buy.assert_called_once()

    def test_browser_buy_uses_safe_non_submit_mode_by_default(self):
        waiter = self.make_waiter()
        waiter.count = 2
        waiter.timeout = 8
        waiter.last_check_time = None
        with unittest.mock.patch("Core.spider.run_browser_checkout", return_value={
            "ok": True,
            "step": "checkout",
            "message": "已进入结算页并定位到提交订单按钮。",
        }) as runner:
            result = Waiter.browser_buy(waiter)

        self.assertTrue(result)
        runner.assert_called_once_with(
            sku_id="100021044189",
            quantity=2,
            timeout_seconds=8.0,
            submit_order=False,
        )


if __name__ == "__main__":
    unittest.main()

from threading import Thread
import re
from Config.settings import config
from Core.browser_cookie_import import import_best_jd_cookies, to_requests_cookiejar
from Core.browser_checkout import open_managed_browser_login as openManagedBrowserLogin, import_managed_browser_cookies
from Core.spider import Waiter
from Core.login import SpiderSession, QrLogin
from Logger.logger import logger


class Global(object):

    def __init__(self):
        self.waiter = None
        self.login = None
        self.thread= None
        self.browser_report = None
        self.spider_session = None
        self.qrlogin = None
        self.login_confirmed = False
        self.cookies_saved = False

    def update(self):
        if not self.spider_session:
            self.spider_session = SpiderSession()
            self.cookies_saved = bool(self.spider_session.load_cookies_from_local()) and self.spider_session.has_login_cookies()
        if self.qrlogin:
            try:
                self.qrlogin.refresh_login_status()
                self.login_confirmed = bool(self.qrlogin.is_login)
            except Exception:
                logger.exception("刷新登录状态失败")
        elif self.waiter and self.waiter.qrlogin:
            self.login_confirmed = bool(self.waiter.qrlogin.is_login)
        if self.spider_session:
            self.cookies_saved = self.spider_session.has_login_cookies()
        self.login = bool(self.login_confirmed or self.cookies_saved)

    def is_running(self):
        return bool(self.thread and self.thread.is_alive())

    def snapshot(self):
        data = self.waiter.snapshot() if self.waiter else {}
        data.update({
            "running": self.is_running(),
            "login": self.login,
            "login_confirmed": self.login_confirmed,
            "cookies_saved": self.cookies_saved,
            "browser_report": self.browser_report,
        })
        return data


glo = Global()


def _int_value(request, name, default, minimum=None, maximum=None):
    try:
        value = int(request.get(name, default))
    except (TypeError, ValueError):
        value = default
    if minimum is not None:
        value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


def _float_value(request, name, default, minimum=None, maximum=None):
    try:
        value = float(request.get(name, default))
    except (TypeError, ValueError):
        value = default
    if minimum is not None:
        value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


def _bool_value(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "y", "on")
    return False


def _normalize_sku(value):
    value = str(value or '').strip()
    match = re.search(r'item\.jd\.com/(\d{5,20})\.html', value)
    if match:
        return match.group(1)
    if re.fullmatch(r'\d{5,20}', value):
        return value
    return ''


def _normalize_stock_provider(value):
    value = str(value or '').strip().lower()
    if value == "jos":
        return "jos"
    return "page"

def log(request):
    file_path = config.path() + config.settings("Logger", "FILE_PATH") + \
        config.settings("Logger", "FILE_NAME")
    file_page_file = open(file_path, 'r', encoding="utf-8")
    return str(file_page_file.read())


def serverConfig(request):
    appConfig = {}
    for model in config._config.sections():
        appConfig[model] = {}
        for item, value in config._config.items(model):
            appConfig[model][item] = config.parse_value(value)
    return appConfig


def _run_waiter(method_name):
    try:
        getattr(glo.waiter, method_name)()
    except Exception as e:
        logger.exception("监控任务异常")
        if glo.waiter:
            glo.waiter.status = "error"
            glo.waiter.last_message = "监控任务异常"
            glo.waiter.last_error = str(e)


def _ensure_login_session():
    if not glo.spider_session:
        glo.spider_session = SpiderSession()
        glo.cookies_saved = bool(glo.spider_session.load_cookies_from_local()) and glo.spider_session.has_login_cookies()
    if not glo.qrlogin:
        glo.qrlogin = QrLogin(glo.spider_session)
    return glo.spider_session, glo.qrlogin


def startQrLogin(request):
    spider_session, qrlogin = _ensure_login_session()
    qrlogin.refresh_login_status()
    if qrlogin.is_login:
        glo.login_confirmed = True
        glo.login = True
        glo.cookies_saved = spider_session.has_login_cookies()
        return {
            "login": True,
            "login_confirmed": True,
            "cookies_saved": glo.cookies_saved,
            "message": "当前 cookies 已登录。",
        }
    ok = qrlogin.prepare_qrcode()
    return {
        "login": False,
        "qrcode": "/runtime/qr_code.png?t={}".format(time_string().replace(' ', '_')),
        "message": "二维码已生成，请用京东 App 扫码确认。" if ok else "二维码生成失败。",
    }


def pollQrLogin(request):
    spider_session, qrlogin = _ensure_login_session()
    qrlogin.refresh_login_status()
    if qrlogin.is_login:
        nick_name = "jd"
        try:
            nick_name = _get_login_nick(spider_session)
        except Exception:
            pass
        spider_session.save_cookies_to_local(nick_name)
        glo.login_confirmed = True
        glo.cookies_saved = spider_session.has_login_cookies()
        glo.login = True
        return {
            "login": True,
            "login_confirmed": True,
            "cookies_saved": glo.cookies_saved,
            "message": "扫码登录成功，cookies 已保存。",
        }
    try:
        ticket = qrlogin._get_qrcode_ticket()
        if ticket and qrlogin._validate_qrcode_ticket(ticket):
            qrlogin.refresh_login_status()
            nick_name = "jd"
            try:
                nick_name = _get_login_nick(spider_session)
            except Exception:
                pass
            spider_session.save_cookies_to_local(nick_name)
            glo.login_confirmed = True
            glo.cookies_saved = spider_session.has_login_cookies()
            glo.login = True
            return {
                "login": True,
                "login_confirmed": True,
                "cookies_saved": glo.cookies_saved,
                "message": "扫码登录成功，cookies 已保存。",
            }
    except Exception as e:
        return {
            "login": False,
            "message": "等待扫码确认：{}".format(e),
        }
    return {
        "login": False,
        "message": "等待扫码确认。",
    }


def _get_login_nick(spider_session):
    import json
    import time
    url = 'https://passport.jd.com/new/helloService.ashx?callback=jQuery339448&_=' + str(int(time.time() * 1000))
    resp = spider_session.get_session().get(url=url, allow_redirects=True)
    text = resp.text.replace('jQuery339448(', '').rstrip(')')
    return json.loads(text).get('nick') or 'jd'


def importBrowserLogin(request):
    spider_session, qrlogin = _ensure_login_session()
    result = import_managed_browser_cookies()
    if not result.get("cookies"):
        result = import_best_jd_cookies()
    if not result.get("cookies"):
        return {
            "login": False,
            "cookies_saved": False,
            "login_confirmed": False,
            "message": result.get("error") or "未读取到浏览器中的京东登录态。",
            "browser": result.get("browser"),
        }
    jar = to_requests_cookiejar(result["cookies"])
    spider_session.replace_cookies_and_save(jar, result.get("browser") or "jd")
    qrlogin.refresh_login_status()
    glo.cookies_saved = spider_session.has_login_cookies()
    glo.login_confirmed = bool(qrlogin.is_login)
    glo.login = bool(glo.cookies_saved or glo.login_confirmed)
    return {
        "login": glo.login,
        "cookies_saved": glo.cookies_saved,
        "login_confirmed": glo.login_confirmed,
        "message": "已导入 {} 浏览器中的京东登录态。".format(result.get("browser") or "本机"),
        "browser": result.get("browser"),
        "cookie_count": result.get("cookie_count", 0),
    }


def openBrowserLogin(request):
    return openManagedBrowserLogin()


def managedBrowserStatus(request):
    result = import_managed_browser_cookies()
    return {
        "ok": bool(result.get("cookies")),
        "login": bool(result.get("login_ok")),
        "browser": result.get("browser"),
        "cookie_count": result.get("cookie_count", 0),
        "current_url": result.get("current_url"),
        "title": result.get("title"),
        "message": result.get("error") or ("专用京东浏览器已登录。" if result.get("login_ok") else "专用京东浏览器尚未登录。"),
    }


def jdShopper(request):
    if glo.is_running():
        return {
            "started": False,
            "running": True,
            "message": "已有监控任务正在运行，请先停止当前任务。"
        }

    mode = request.get('mode', '1')
    date = request.get('date', '')
    skuids = _normalize_sku(request.get('skuid', ''))
    area = str(request.get('area', '')).strip()
    eid = str(request.get('eid', '')).strip()
    fp = str(request.get('fp', '')).strip()
    submit_order = _bool_value(request.get('submit_order', config.settings("Spider", "submit_order")))
    count = _int_value(request, 'count', 1, 1, 999)
    retry = _int_value(request, 'retry', 10, 1, 1000)
    work_count = _int_value(request, 'work_count', 1, 1, 3)
    timeout = _float_value(request, 'timeout', 30, 1, 1000)
    stock_provider = _normalize_stock_provider(request.get('stock_provider') or config.settings("Spider", "stock_provider"))
    result = {
        "started": False,
        "login": False,
        "running": False,
        "message": "库存监控任务未启动"
    }
    if not skuids or not area:
        result["message"] = "商品ID/链接和地区ID不能为空，商品ID必须是5到20位数字。"
        return result

    if mode == '1':
        glo.waiter = Waiter(skuids=skuids, area=area, eid=eid, fp=fp, count=count, submit_order=submit_order,
                    retry=retry, work_count=work_count, timeout=timeout, stock_provider=stock_provider)
        if glo.spider_session:
            glo.waiter.spider_session = glo.spider_session
            glo.waiter.session = glo.spider_session.get_session()
            glo.waiter.qrlogin = glo.qrlogin
        glo.waiter.status = "starting"
        glo.waiter.last_message = "有货自动下单正在启动"
        glo.thread = Thread(target=_run_waiter, args=("waitAndBuy_by_proc_pool",), daemon=True)
        glo.thread.start()
        result["started"] = True
        result["message"] = "有货自动下单已启动。程序检测到可购买状态后会自动尝试提交订单。"
    elif mode == '2':
        date = date.replace("T", " ")
        date = date.replace("Z", "")
        glo.waiter = Waiter(skuids=skuids, area=area, eid=eid, fp=fp, count=count, submit_order=submit_order,
                    retry=retry, work_count=work_count, timeout=timeout, stock_provider=stock_provider, date=date)
        if glo.spider_session:
            glo.waiter.spider_session = glo.spider_session
            glo.waiter.session = glo.spider_session.get_session()
            glo.waiter.qrlogin = glo.qrlogin
        glo.waiter.status = "starting"
        glo.waiter.last_message = "定时下单正在启动"
        glo.thread = Thread(target=_run_waiter, args=("waitTimeAndBuy",), daemon=True)
        glo.thread.start()
        result["started"] = True
        result["message"] = "定时下单已启动。到点后会自动尝试提交订单。"
    else:
        result["message"] = "未知监控模式。"
        return result
    glo.update()
    result["login"] = glo.login
    result["running"] = glo.is_running()
    result["task"] = glo.snapshot()
    return result


def taskStatus(request):
    glo.update()
    return glo.snapshot()


def browserReport(request):
    sku = _normalize_sku(request.get('sku') or request.get('url') or '')
    report = {
        "sku": sku,
        "url": str(request.get('url', '')).strip(),
        "title": str(request.get('title', '')).strip(),
        "status_text": str(request.get('status_text', '')).strip(),
        "button_text": str(request.get('button_text', '')).strip(),
        "in_stock": _bool_value(request.get('in_stock', False)),
        "reported_at": time_string(),
    }
    glo.browser_report = report
    if glo.waiter and (not sku or sku == glo.waiter.skuids):
        glo.waiter.last_check_time = report["reported_at"]
        glo.waiter.last_stock_state = report["status_text"] or report["button_text"] or "浏览器已上报"
        glo.waiter.last_error = None
        if report["in_stock"]:
            glo.waiter.status = "found"
            glo.waiter.last_message = "浏览器页面显示可能可购买"
        else:
            glo.waiter.status = "browser"
            glo.waiter.last_message = "浏览器页面已上报，暂未发现可购买入口"
    return {
        "ok": True,
        "report": report,
    }


def time_string():
    import time
    return time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())


def checkStock(request):
    skuids = _normalize_sku(request.get('skuid') or (glo.waiter.skuids if glo.waiter else ''))
    area = str(request.get('area') or (glo.waiter.area if glo.waiter else '')).strip()
    timeout = _float_value(request, 'timeout', 10, 1, 100)
    stock_provider = _normalize_stock_provider(request.get('stock_provider') or config.settings("Spider", "stock_provider"))
    if not skuids or not area:
        return {
            "checked": False,
            "message": "商品ID/链接和地区ID不能为空，商品ID必须是5到20位数字。"
        }
    waiter = Waiter(skuids=skuids, area=area, timeout=timeout, stock_provider=stock_provider)
    in_stock = waiter.get_single_item_stock(skuids, area)
    return {
        "checked": True,
        "in_stock": in_stock,
        "task": waiter.snapshot(),
        "message": "发现可能有货，请手动打开商品页。" if in_stock else "当前未检测到可购买库存。"
    }


def stopTask(request):
    if glo.waiter:
        glo.waiter.stop()
    if glo.thread and glo.thread.is_alive():
        glo.thread.join(timeout=2)
    return {
        "stopped": True,
        "running": glo.is_running(),
        "message": "已请求停止监控任务。",
        "task": glo.snapshot()
    }


def loginStatus(request):
    try:
        glo.update()
    except Exception:
        pass
    return glo.login

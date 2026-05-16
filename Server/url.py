from Server.api import log, serverConfig, jdShopper, loginStatus, taskStatus, stopTask, checkStock, startQrLogin, pollQrLogin, browserReport, importBrowserLogin, openBrowserLogin, managedBrowserStatus

def urls(url, request):
    if (url == "/log"): return log(request)
    elif (url == "/config"): return serverConfig(request)
    elif (url == "/jd-shopper"): return jdShopper(request)
    elif (url == "/task-status"): return taskStatus(request)
    elif (url == "/stop-task"): return stopTask(request)
    elif (url == "/check-stock"): return checkStock(request)
    elif (url == "/login-qrcode"): return startQrLogin(request)
    elif (url == "/login-poll"): return pollQrLogin(request)
    elif (url == "/open-browser-login"): return openBrowserLogin(request)
    elif (url == "/managed-browser-status"): return managedBrowserStatus(request)
    elif (url == "/import-browser-login"): return importBrowserLogin(request)
    elif (url == "/browser-report"): return browserReport(request)
    elif (url == "/jd-login-status"): return loginStatus(request)
    else: return "No Response"

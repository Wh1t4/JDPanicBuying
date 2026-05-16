import os, json, time, mimetypes
from urllib.parse import urlparse, parse_qsl

from Logger.logger import logger
from http.server import BaseHTTPRequestHandler
from Config.settings import config
from Server.url import urls


# Document https://docs.python.org/3.9/library/http.server.html

class RequestHandler(BaseHTTPRequestHandler):
    """处理请求并返回页面"""

    def static_root(self):
        frontend_dist = os.path.join(config.path(), "frontend", "dist")
        if os.path.exists(os.path.join(frontend_dist, "index.html")):
            return frontend_dist
        return os.path.join(config.path(), "Static")

    # 处理一个GET请求
    def do_GET(self):
        self.rootPath = self.static_root()
        parsed_url = urlparse(self.path)
        url = parsed_url.path
        request_data = dict(parse_qsl(parsed_url.query))  # 存放GET请求数据
        if (url.startswith("/api")):
            self.api(url[4:], request_data)
        elif (url == "/" or url == ""):
            self.home()
        else:
            self.file(url)

    def do_POST(self):
        self.rootPath = self.static_root()
        url = urlparse(self.path).path
        content_length = int(self.headers.get('content-length', 0))
        if content_length:
            try:
                request_data = json.loads(self.rfile.read(content_length).decode())
            except json.JSONDecodeError:
                logger.error("JSON Format Error")
                self.json_response({"data": None, "error": "JSON Format Error"}, status=400)
                return
        else:
            request_data = {}
        if (url.startswith("/api")):
            self.api(url[4:], request_data)
        elif (url == "/" or url == ""):
            self.home()
        else:
            self.file(url)

    def log_message(self, format, *args):
        SERVER_LOGGER = config.settings("Logger", "SERVER_LOGGER")
        if SERVER_LOGGER:
            logger.info(format % args)
        else:
            pass

    def home(self):
        self.send_static_file(os.path.join(self.rootPath, "index.html"))

    def file(self, url):
        safe_url = os.path.normpath(url.lstrip("/"))
        if safe_url.startswith(".."):
            self.noFound()
            return
        file_path = os.path.join(self.rootPath, safe_url)
        if os.path.isdir(file_path):
            file_path = os.path.join(file_path, "index.html")
        if not os.path.exists(file_path):
            legacy_path = os.path.join(config.path(), "Static", safe_url)
            if os.path.exists(legacy_path):
                file_path = legacy_path
            else:
                self.noFound()
                return
        self.send_static_file(file_path)

    def send_static_file(self, file_path):
        content_type = mimetypes.guess_type(file_path)[0] or "application/octet-stream"
        with open(file_path, "rb") as file_page_file:
            body = file_page_file.read()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def api(self, url, request_data):
        # ----------------------------------------------------------------
        # 此处写API
        try:
            content = urls(url, request_data)
            error = None
        except Exception as e:
            logger.exception("API Error")
            content = None
            error = str(e)
        # ----------------------------------------------------------------
        localtime = time.localtime(time.time())
        date = \
            localtime.tm_year.__str__() + '-' + \
            localtime.tm_mon.__str__() + '-' + \
            localtime.tm_mday.__str__() + ' ' + \
            localtime.tm_hour.__str__() + ':' + \
            localtime.tm_min.__str__() + ':' + \
            localtime.tm_sec.__str__()
        jsondict = {}
        jsondict["data"] = content
        jsondict["time"] = date
        if error:
            jsondict["error"] = error
        self.json_response(jsondict, status=500 if error else 200)

    def json_response(self, jsondict, status=200):
        res = json.dumps(jsondict, ensure_ascii=False)
        body = res.encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def noFound(self):
        fallback = os.path.join(self.rootPath, "404.html")
        if os.path.exists(fallback):
            self.send_static_file(fallback)
            return
        self.send_response(404)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        body = "Not Found".encode()
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

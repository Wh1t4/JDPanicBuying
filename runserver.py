from Logger.logger import logger
from Config.settings import config
from Server.server import server

SERVER = config.settings("Server", "START_USING")


def running():
    if SERVER:
        server()
    else:
        logger.warning("本地客户端服务已在 Config/config.ini 中关闭。")


if __name__ == "__main__":
    DEBUG = config.settings("Debug", "DEBUG")
    if DEBUG:
        logger.info("\n===== DEBUG MODE =====")
    running()

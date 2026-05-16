import json
import random
import requests
import os
import time

from Config.settings import config

def parse_json(s):
    begin = s.find('{')
    end = s.rfind('}') + 1
    return json.loads(s[begin:end])

def wait_some_time():
    time.sleep(random.randint(100, 300) / 1000)


def send_wechat(message):
    """推送信息到微信"""
    url = 'http://sc.ftqq.com/{}.send'.format(config.settings('messenger', 'sckey'))
    payload = {
        "text": '库存监控提醒',
        "desp": message
    }
    headers = {
        'User-Agent':config.settings('config', 'DEFAULT_USER_AGENT')
    }
    requests.get(url, params=payload, headers=headers)


def response_status(resp):
    if resp.status_code != requests.codes.OK:
        print('Status: %u, Url: %s' % (resp.status_code, resp.url))
        return False
    return True


def open_image(image_file):
    if os.name == "nt":
        os.system('start ' + config.path() + '/Static/img/'+ image_file)  # for Windows
    else:
        if os.uname()[0] == "Linux":
            if "deepin" in os.uname()[2]:
                os.system("deepin-image-viewer " + image_file)  # for deepin
            else:
                os.system("eog " + image_file)  # for Linux
        else:
            os.system("open " + image_file)  # for Mac


def save_image(resp, image_file):
    with open(config.path() + '/Static/img/' + image_file, 'wb') as f:
        for chunk in resp.iter_content(chunk_size=1024):
            f.write(chunk)

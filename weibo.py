# 微博超话 API 请求模块

import urllib.request
import json
import ssl
from config import WEIBO_COOKIE, WEIBO_CONTAINERID

API_URL = f"https://m.weibo.cn/api/container/getIndex?containerid={WEIBO_CONTAINERID}_-_live"

def fetch_desc1():
    """请求超话 API 获取 desc1 字段（在线状态）"""
    req = urllib.request.Request(API_URL)
    req.add_header("User-Agent",
        "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1")
    req.add_header("Cookie", WEIBO_COOKIE)
    req.add_header("Referer", "https://m.weibo.cn/")
    req.add_header("Accept", "application/json, text/plain, */*")
    ctx = ssl.create_default_context()

    resp = urllib.request.urlopen(req, timeout=15)
    data = json.loads(resp.read())

    cards = data.get("data", {}).get("cards", [])
    for card in cards:
        cg = card.get("card_group", [])
        for g in cg:
            if "desc1" in g:
                return g["desc1"]
    return None

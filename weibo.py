"""微博超话 API 请求模块 - 带重试、指数退避和 Cookie 过期检测"""

import time
import ssl
import json
import urllib.request
import urllib.error
from config import WEIBO_COOKIE, WEIBO_CONTAINERID, REQUEST_TIMEOUT, RETRY_COUNT

API_URL = f"https://m.weibo.cn/api/container/getIndex?containerid={WEIBO_CONTAINERID}_-_live"

class CookieExpiredError(Exception):
    """Cookie 已过期或无效（API 返回登录页）"""
    pass

def _build_request():
    req = urllib.request.Request(API_URL)
    req.add_header("User-Agent",
        "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1")
    req.add_header("Cookie", WEIBO_COOKIE)
    req.add_header("Referer", "https://m.weibo.cn/")
    req.add_header("Accept", "application/json, text/plain, */*")
    return req

def _is_login_page(body_bytes):
    """检测响应是否为微博登录页（Cookie 过期）"""
    text = body_bytes[:500].decode(errors='replace')
    return text.strip().startswith('<!') or 'login' in text.lower()

def fetch_desc1(log_fn=None):
    """请求超话 API 获取 desc1 字段（带指数退避重试和 Cookie 过期检测）"""
    last_err = None
    for attempt in range(max(1, RETRY_COUNT)):
        try:
            ctx = ssl.create_default_context()
            req = _build_request()
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT, context=ctx) as resp:
                body = resp.read()
            # Cookie 过期检测：响应是 HTML 而非 JSON
            if _is_login_page(body):
                raise CookieExpiredError("Cookie 已过期，API 返回登录页面")
            data = json.loads(body)
            cards = data.get("data", {}).get("cards", [])
            for card in cards:
                for g in card.get("card_group", []):
                    if "desc1" in g:
                        return g["desc1"]
            return None
        except CookieExpiredError:
            raise  # 不重试，直接上抛
        except (urllib.error.URLError, urllib.error.HTTPError,
                json.JSONDecodeError, ssl.SSLError, OSError) as e:
            last_err = e
            if log_fn:
                log_fn(f"微博请求失败 (attempt {attempt+1}/{RETRY_COUNT}): {e}")
            if attempt < RETRY_COUNT - 1:
                time.sleep(min(2 ** attempt, 30))
    if last_err:
        raise last_err
    return None

"""微博超话 API 请求模块 - 带重试、指数退避和 Cookie 过期检测"""

import time
import ssl
import json
import urllib.request
import urllib.error
import config
from config import WEIBO_CONTAINERID, REQUEST_TIMEOUT, RETRY_COUNT, WEIBO_PROXY

API_URL = f"https://m.weibo.cn/api/container/getIndex?containerid={WEIBO_CONTAINERID}_-_live"

class CookieExpiredError(Exception):
    """Cookie 已过期或无效（API 返回登录页）"""
    pass

class RateLimitedError(Exception):
    """触发微博风控（HTTP 432）。

    与网络类错误不同：432 是服务器主动拒绝，重试无意义且会加重风控，
    故抛出此异常让上层进入退避（拉长轮询间隔），而非原地重试。
    """
    def __init__(self, message="HTTP 432 风控", code=432):
        super().__init__(message)
        self.code = code

def _build_request():
    req = urllib.request.Request(API_URL)
    req.add_header("User-Agent",
        "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1")
    # 动态读取 config，支持 .env 热重载（换 cookie 后无需重启进程）
    req.add_header("Cookie", config.WEIBO_COOKIE)
    req.add_header("Referer", "https://m.weibo.cn/")
    req.add_header("Accept", "application/json, text/plain, */*")
    return req

def _make_opener(proxy, ctx):
    """构造 urllib opener：proxy 非空时走代理，否则直连（兼容原行为）。
    SSL 上下文必须在创建 opener 时通过 HTTPSHandler(context=ctx) 传入，
    因为 OpenerDirector.open() 不接受 context 关键字参数（只有 urlopen 接受）。"""
    handlers = []
    if proxy:
        handlers.append(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
    handlers.append(urllib.request.HTTPSHandler(context=ctx))
    return urllib.request.build_opener(*handlers)

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
            # 支持代理：WEIBO_PROXY 非空时微博请求走指定出口（绕过被限流的 IP）；
            # 为空则保持原 urlopen 直连路径（兼容既有 mock 与默认行为）
            if config.WEIBO_PROXY:
                opener = _make_opener(config.WEIBO_PROXY, ctx)
                with opener.open(req, timeout=REQUEST_TIMEOUT) as resp:
                    body = resp.read()
            else:
                with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT, context=ctx) as resp:
                    body = resp.read()
            # Cookie 过期检测：响应是 HTML 而非 JSON
            if _is_login_page(body):
                raise CookieExpiredError("Cookie 已过期，API 返回登录页面")
            data = json.loads(body)
            # 真实失效检测增强：返回 JSON 但 ok != 1 且明确登录失效，也判为过期
            # （原逻辑只看登录页 HTML；若微博返回「JSON 但空数据/未登录」会被静默吞掉，永不报警）
            ok = data.get("ok")
            if ok not in (1, None):
                msg = data.get("msg") or (data.get("data", {}).get("msg")
                                          if isinstance(data.get("data"), dict) else None)
                txt = f"{msg}".lower()
                if any(k in txt for k in ("登录", "未登录", "login", "请先登录", "请登录", "授权", "signin")):
                    raise CookieExpiredError("Cookie 已过期（API 返回未登录）")
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
            # 432 = 微博风控：服务器主动拒绝，重试只会加重风控，直接上抛进入退避
            if getattr(e, "code", None) == 432:
                if log_fn:
                    log_fn("微博风控 (HTTP 432)，停止重试并进入退避")
                raise RateLimitedError(str(e))
            last_err = e
            if log_fn:
                log_fn(f"微博请求失败 (attempt {attempt+1}/{RETRY_COUNT}): {e}")
            if attempt < RETRY_COUNT - 1:
                time.sleep(min(2 ** attempt, 30))
    if last_err:
        raise last_err
    return None


# ---- 真实登录态探测（判定 Cookie 是否可用的权威依据）----
CONFIG_URL = "https://m.weibo.cn/api/config"


def _build_config_request():
    req = urllib.request.Request(CONFIG_URL)
    req.add_header("User-Agent",
        "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1")
    req.add_header("Cookie", config.WEIBO_COOKIE)
    req.add_header("Referer", "https://m.weibo.cn/")
    req.add_header("Accept", "application/json, text/plain, */*")
    req.add_header("X-Requested-With", "XMLHttpRequest")
    req.add_header("MWeibo-Pwa", "1")
    return req


def check_login(log_fn=None):
    """用 /api/config 探测 Cookie 的**真实登录态**。

    返回 True=已登录 / False=未登录(会话已失效) / None=无法判断(网络错误)。
    这是判定 Cookie 是否可用的权威依据：ALF 理论到期时间不可信，
    而 432 既可能来自 IP 限流、也可能来自会话失效，必须靠此接口区分。
    """
    ctx = ssl.create_default_context()
    req = _build_config_request()
    try:
        if config.WEIBO_PROXY:
            opener = _make_opener(config.WEIBO_PROXY, ctx)
            with opener.open(req, timeout=REQUEST_TIMEOUT) as resp:
                body = resp.read()
        else:
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT, context=ctx) as resp:
                body = resp.read()
        data = json.loads(body)
        return bool((data.get("data") or {}).get("login"))
    except Exception as e:
        if log_fn:
            log_fn(f"登录态探测失败（按未知处理）: {e}")
        return None

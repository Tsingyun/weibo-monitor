"""微博监控一键诊断：判断故障到底在哪一层（IP / Cookie / 账号接口限制）

用法：
    python diag.py

判定逻辑（实测依据，见 README 故障排查）：
    1. 带 Cookie 打 getIndex 正常            -> 一切正常
    2. 带 Cookie 打 getIndex 返回 432        -> 出口 IP 被限流（换节点/关代理）
    3. 带 Cookie 打 getIndex 返回 403        -> 账号被单独限制该接口（换号/重新登录/等解除）
    4. 不带 Cookie 打 getIndex 返回 432      -> 正常现象（该接口强制要求登录），不作证据
    5. /api/config 的 login=false            -> Cookie 会话已失效（需重新登录）

注意：ALF 里的过期时间只是「理论有效期」，不代表 Cookie 真实可用，必须看接口真实响应。
"""

import os
import ssl
import sys
import json
import urllib.request
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 先清掉代理环境变量，避免系统级 HTTPS_PROXY 干扰判定
for _k in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
           "http_proxy", "https_proxy", "all_proxy"):
    os.environ.pop(_k, None)

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import config  # noqa: E402

UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
      "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1")

CTX = ssl.create_default_context()


def _request(url, cookie=None, referer="https://m.weibo.cn/", jar=None):
    req = urllib.request.Request(url)
    req.add_header("User-Agent", UA)
    req.add_header("Referer", referer)
    req.add_header("Accept", "application/json, text/plain, */*")
    req.add_header("X-Requested-With", "XMLHttpRequest")
    req.add_header("MWeibo-Pwa", "1")
    if cookie:
        req.add_header("Cookie", cookie)
    handler = urllib.request.urlopen
    if jar is not None:
        opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(jar),
            urllib.request.HTTPSHandler(context=CTX))
        handler = opener.open
        try:
            with handler(req, timeout=20) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()
        except Exception as e:  # noqa: BLE001
            return type(e).__name__, str(e).encode()
    try:
        with handler(req, timeout=20, context=CTX) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except Exception as e:  # noqa: BLE001
        return type(e).__name__, str(e).encode()


def _brief(body, n=110):
    try:
        return body[:n].decode(errors="replace").replace("\n", " ")
    except Exception:  # noqa: BLE001
        return str(body)[:n]


def main():
    cid = config.WEIBO_CONTAINERID
    cookie = config.WEIBO_COOKIE
    live = f"https://m.weibo.cn/api/container/getIndex?containerid={cid}_-_live"

    print("=" * 62)
    print("微博监控诊断")
    print("=" * 62)
    print(f"containerid : {cid}")
    print(f"cookie 字段 : {', '.join(p.split('=', 1)[0] for p in cookie.split('; ') if '=' in p)}")
    print(f"WEIBO_PROXY : {config.WEIBO_PROXY!r}")
    print()

    rows = []
    verdicts = []

    # 1) 登录态（权威）
    from weibo import check_login
    login = check_login()
    rows.append(("登录态 /api/config", {True: "login=true", False: "login=false",
                                        None: "无法判断"}[login]))
    if login is False:
        verdicts.append("Cookie 会话已失效：/api/config 返回 login=false，必须重新登录后重新抓 Cookie")
    elif login is None:
        verdicts.append("登录态探测失败：可能是网络或证书问题，先确认能否访问 m.weibo.cn")

    # 2) 目标接口（带 Cookie）
    st, body = _request(live, cookie=cookie)
    rows.append(("getIndex _live（带 Cookie）", f"HTTP {st} {_brief(body, 70)}"))

    # 3) 目标接口（不带 Cookie）
    st2, body2 = _request(live, cookie=None)
    rows.append(("getIndex _live（无 Cookie）", f"HTTP {st2} {_brief(body2, 50)}"))

    # 4) 游客会话（新 _T_WM）
    import http.cookiejar
    jar = http.cookiejar.CookieJar()
    _request("https://m.weibo.cn/", cookie=None, jar=jar)
    st3, body3 = _request(live, cookie=None, jar=jar)
    rows.append(("getIndex _live（游客会话）", f"HTTP {st3} {_brief(body3, 50)}"))

    # 5) 旁路接口（验证账号本身是否正常）
    st4, body4 = _request("https://m.weibo.cn/api/users/show?uid=7785772638", cookie=cookie)
    rows.append(("users/show（对照）", f"HTTP {st4} {_brief(body4, 60)}"))

    for name, val in rows:
        print(f"  {name:26s} {val}")

    # 判定
    if st == 200:
        try:
            data = json.loads(body)
        except Exception:  # noqa: BLE001
            data = {}
        if data.get("ok") == 1:
            verdicts.append("接口正常")
        else:
            verdicts.append("接口返回 200 但 ok!=1（可能是数据为空或限制文案，需人工看响应体）")
    elif st == 432:
        verdicts.append("432 风控：出口 IP 被限流 → 换节点 / 关代理直连 / 加大轮询间隔")
        if st2 == 403:
            verdicts.append("但无 Cookie 时为 403，说明限制是按账号走的，优先考虑换号")
    elif st == 403:
        verdicts.append("403 接口级拒绝：**该账号被单独限制 container/getIndex**")
        verdicts.append("  实测排除项：换 IP（含关代理直连）、换 UA、改 Cookie 子集、换参数形式 —— 均无效")
        verdicts.append("  → 解决方向：① 换另一个小号 Cookie（最快）② 浏览器真正退出重登后重抓 Cookie ③ 等风控自然解除（24-72h）")

    print()
    print("-" * 62)
    if verdicts:
        for v in verdicts:
            print("  * " + v)
    else:
        print("  * 未发现异常")
    print("-" * 62)
    return 0 if st == 200 else 1


if __name__ == "__main__":
    sys.exit(main())

"""weibo.py 真实失效检测增强的单元测试（mock 网络，不依赖真实请求）。"""
import sys, os, json, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + '/..')
import weibo
import urllib.error


class _Resp:
    def __init__(self, body):
        self._b = body.encode('utf-8')
    def read(self):
        return self._b
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False


# 保存原始 urlopen，便于每个用例结束后还原，避免 monkey-patch 泄漏污染后续用例
_ORIG_URLOPEN = weibo.urllib.request.urlopen


class TestWeiboCookieReal(unittest.TestCase):
    def tearDown(self):
        weibo.urllib.request.urlopen = _ORIG_URLOPEN

    def _patch_body(self, body):
        weibo.urllib.request.urlopen = lambda req, **kw: _Resp(body)

    def test_ok1_returns_desc1(self):
        body = json.dumps({"ok": 1, "data": {"cards": [{"card_group": [{"desc1": "在播"}]}]}})
        self._patch_body(body)
        self.assertEqual(weibo.fetch_desc1(), "在播")

    def test_login_json_expired(self):
        # 返回 JSON 但 ok=0 且明确"请先登录" —— 新增的识别逻辑应判过期
        body = json.dumps({"ok": 0, "msg": "请先登录"})
        self._patch_body(body)
        self.assertRaises(weibo.CookieExpiredError, weibo.fetch_desc1)

    def test_432_raises_rate_limited(self):
        def f(req, **kw):
            raise urllib.error.HTTPError('http://x', 432, 'x', {}, None)
        weibo.urllib.request.urlopen = f
        self.assertRaises(weibo.RateLimitedError, weibo.fetch_desc1)

    def test_ok0_no_login_silent_none(self):
        # ok=0 但无登录关键词（如"系统繁忙"）—— 不误判过期，保留原行为返回 None
        body = json.dumps({"ok": 0, "msg": "系统繁忙"})
        self._patch_body(body)
        self.assertIsNone(weibo.fetch_desc1())


if __name__ == '__main__':
    unittest.main()

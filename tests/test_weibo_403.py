"""403「请求被拒绝」应立即上抛 AccessDeniedError，且不重试（避免加重风控）。"""
import sys, os, io, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + '/..')
import weibo

_ORIG_URLOPEN = weibo.urllib.request.urlopen
_ORIG_PROXY = weibo.config.WEIBO_PROXY


class TestAccessDenied(unittest.TestCase):
    def setUp(self):
        # 强制直连路径，否则会走 opener.open 而命中不到 urlopen 桩
        weibo.config.WEIBO_PROXY = ""

    def tearDown(self):
        weibo.urllib.request.urlopen = _ORIG_URLOPEN
        weibo.config.WEIBO_PROXY = _ORIG_PROXY

    def test_403_raises_access_denied_without_retry(self):
        calls = {"n": 0}

        def fake(req, **kw):
            calls["n"] += 1
            raise weibo.urllib.error.HTTPError(
                req.full_url, 403, "Forbidden", {},
                io.BytesIO(b'{"ok":0,"errno":"403","msg":"\xe8\xaf\xb7\xe6\xb1\x82\xe8\xa2\xab\xe6\x8b\x92\xe7\xbb\x9d"}'))

        weibo.urllib.request.urlopen = fake
        with self.assertRaises(weibo.AccessDeniedError):
            weibo.fetch_desc1()
        self.assertEqual(calls["n"], 1, "403 不应重试（重试只会加重账号限制）")

    def test_432_still_raises_rate_limited(self):
        def fake(req, **kw):
            raise weibo.urllib.error.HTTPError(req.full_url, 432, "Limited", {}, io.BytesIO(b""))

        weibo.urllib.request.urlopen = fake
        with self.assertRaises(weibo.RateLimitedError):
            weibo.fetch_desc1()


if __name__ == '__main__':
    unittest.main()

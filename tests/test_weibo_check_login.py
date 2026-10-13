"""weibo.check_login（/api/config 真实登录态探测）单元测试。"""
import sys, os, json, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + '/..')
import weibo
import config

_ORIG_URLOPEN = weibo.urllib.request.urlopen
_ORIG_PROXY = config.WEIBO_PROXY


class _Resp:
    def __init__(self, body):
        self._b = body.encode("utf-8")

    def read(self):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class TestCheckLogin(unittest.TestCase):
    def setUp(self):
        # 强制走直连分支，使 mock urlopen 生效
        weibo.config.WEIBO_PROXY = ""

    def tearDown(self):
        weibo.urllib.request.urlopen = _ORIG_URLOPEN
        config.WEIBO_PROXY = _ORIG_PROXY
        weibo.config.WEIBO_PROXY = _ORIG_PROXY

    def _patch(self, body):
        weibo.urllib.request.urlopen = lambda req, **kw: _Resp(body)

    def test_login_true(self):
        self._patch(json.dumps({"data": {"login": True, "uid": "123"}}))
        self.assertTrue(weibo.check_login())

    def test_login_false(self):
        self._patch(json.dumps({"data": {"login": False, "loginUrl": "https://x"}}))
        self.assertFalse(weibo.check_login())

    def test_network_error_returns_none(self):
        def _boom(req, **kw):
            raise OSError("network down")
        weibo.urllib.request.urlopen = _boom
        self.assertIsNone(weibo.check_login())

    def test_non_json_returns_none(self):
        self._patch("<html>login shell</html>")
        self.assertIsNone(weibo.check_login())


if __name__ == '__main__':
    unittest.main()

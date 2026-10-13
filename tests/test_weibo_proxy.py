"""微博请求代理开关的单元测试（mock build_opener，隔离环境代理变量）。"""
import sys, os, unittest
from unittest import mock
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + '/..')
import weibo
import urllib.request


def _proxy_map(h):
    # ProxyHandler 在不同 Python 版本内部属性名不同（proxies / _proxy_dict）
    return getattr(h, "proxies", None) or getattr(h, "_proxy_dict", {}) or {}


class TestMakeOpener(unittest.TestCase):
    def test_proxy_nonempty_passes_proxy_handler(self):
        with mock.patch("urllib.request.build_opener") as mb:
            weibo._make_opener("http://127.0.0.1:7897")
            args = mb.call_args[0]
            phs = [a for a in args if isinstance(a, urllib.request.ProxyHandler)]
            self.assertTrue(
                any("127.0.0.1:7897" in str(_proxy_map(a)) for a in phs),
                "设置代理时应向 build_opener 传入指向 127.0.0.1:7897 的 ProxyHandler",
            )

    def test_proxy_empty_passes_no_proxy_handler(self):
        with mock.patch("urllib.request.build_opener") as mb:
            weibo._make_opener("")
            args = mb.call_args[0]
            phs = [a for a in args if isinstance(a, urllib.request.ProxyHandler)]
            self.assertEqual(len(phs), 0, "直连（空代理）时不应向 build_opener 传入 ProxyHandler")

    def test_proxy_socks_passes_proxy_handler(self):
        with mock.patch("urllib.request.build_opener") as mb:
            weibo._make_opener("socks5://127.0.0.1:1080")
            args = mb.call_args[0]
            phs = [a for a in args if isinstance(a, urllib.request.ProxyHandler)]
            self.assertTrue(
                any("1080" in str(_proxy_map(a)) for a in phs),
                "socks5 代理也应被 ProxyHandler 保存并传入 build_opener",
            )


if __name__ == "__main__":
    unittest.main()

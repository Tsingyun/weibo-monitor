"""monitor.py Cookie 真实状态追踪 + 432 归因（会话失效 vs IP 限流）单元测试。"""
import sys, os, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + '/..')
import weibo
import monitor


def _raiser(exc):
    def f(**k):
        raise exc
    return f


# 保存原始函数，避免测试桩泄漏污染后续用例
_ORIG_FETCH = weibo.fetch_desc1
_ORIG_CHECK_LOGIN = weibo.check_login


class TestMonitorCookieAlert(unittest.TestCase):
    def tearDown(self):
        weibo.fetch_desc1 = _ORIG_FETCH
        weibo.check_login = _ORIG_CHECK_LOGIN

    def _monitor(self):
        return monitor.Monitor(log_fn=lambda *a, **k: None)

    def test_success_sets_valid_and_resets(self):
        import notifier
        notifier.send = lambda msg, **k: None
        weibo.fetch_desc1 = lambda **k: "在播"
        m = self._monitor()
        m.check_and_log()
        self.assertEqual(m.cookie_real_status, "valid")
        self.assertEqual(m.consecutive_432, 0)
        self.assertTrue(m.cookie_login)

    def test_432_with_valid_login_is_ip_ratelimit(self):
        """432 但登录态正常 → 判为出口 IP 限流，退避并告警。"""
        import notifier
        alerts = []
        notifier.send = lambda msg, **k: alerts.append((msg, k))
        weibo.fetch_desc1 = _raiser(weibo.RateLimitedError())
        weibo.check_login = lambda **k: True
        m = self._monitor()
        for _ in range(5):
            m.check_and_log()
        self.assertGreaterEqual(m.consecutive_432, 5)
        self.assertEqual(m.cookie_real_status, "rate_limited")
        self.assertTrue(any("出口IP" in (a[1].get("bark_title") or "") for a in alerts))

    def test_432_with_dead_session_is_cookie_invalid(self):
        """432 且 /api/config 显示未登录 → 判为 Cookie 失效（而非 IP 限流）。"""
        import notifier
        alerts = []
        notifier.send = lambda msg, **k: alerts.append((msg, k))
        weibo.fetch_desc1 = _raiser(weibo.RateLimitedError())
        weibo.check_login = lambda **k: False
        m = self._monitor()
        m.check_and_log()
        self.assertEqual(m.cookie_real_status, "invalid")
        self.assertFalse(m.cookie_login)
        self.assertTrue(any("Cookie 已失效" in (a[1].get("bark_title") or "") for a in alerts))
        # 只告警一次
        m.check_and_log()
        self.assertEqual(
            len([a for a in alerts if "Cookie 已失效" in (a[1].get("bark_title") or "")]), 1)

    def test_cookie_expired_sets_invalid(self):
        import notifier
        notifier.send = lambda msg, **k: None
        weibo.fetch_desc1 = _raiser(weibo.CookieExpiredError("x"))
        m = self._monitor()
        m.check_and_log()
        self.assertEqual(m.cookie_real_status, "invalid")
        self.assertFalse(m.cookie_login)


if __name__ == '__main__':
    unittest.main()

"""monitor.py Cookie 真实状态追踪 + 连续432主动告警 的单元测试（mock 请求与推送）。"""
import sys, os, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + '/..')
import weibo
import monitor


def _raiser(exc):
    def f(**k):
        raise exc
    return f


class TestMonitorCookieAlert(unittest.TestCase):
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

    def test_432_consecutive_alert(self):
        import notifier
        alerts = []
        def _send(msg, **k):
            alerts.append((msg, k))
        notifier.send = _send
        weibo.fetch_desc1 = _raiser(weibo.RateLimitedError())
        m = self._monitor()
        for _ in range(5):
            m.check_and_log()
        self.assertGreaterEqual(m.consecutive_432, 5)
        self.assertTrue(m.cookie_432_alerted)
        self.assertTrue(any("Cookie 可能已失效" in (a[1].get("bark_title") or "") for a in alerts))

    def test_cookie_expired_sets_invalid(self):
        import notifier
        notifier.send = lambda msg, **k: None
        weibo.fetch_desc1 = _raiser(weibo.CookieExpiredError("x"))
        m = self._monitor()
        m.check_and_log()
        self.assertEqual(m.cookie_real_status, "invalid")


if __name__ == '__main__':
    unittest.main()

"""核心逻辑单元测试（防回归）

覆盖 8 月以来实际踩过的坑：
- 逻辑日界归属（0:00~boundary 归前一天）
- 在线文案白名单判定
- 跨日界会话拆分（无损）
- 进行中会话必须纳入统计（8/27 bug）
- 432 风控退避逐级递增并封顶（A3）
- 事件写入失败入队不丢（B1）

运行:
  python -m pytest tests/ -v
  # 或不用 pytest 时直接跑：
  python tests/test_core.py
"""

import os
import sys
import unittest.mock as mock
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils import beijing_now, logical_date, is_online, format_duration, cookie_expire_info
from monitor import Monitor
from config import DAY_BOUNDARY_HOUR, BACKOFF_STEPS


def test_logical_date_boundary():
    """凌晨 0 点~日界之间归前一天，日界及之后归当天"""
    b = DAY_BOUNDARY_HOUR
    assert logical_date(datetime(2026, 8, 28, b, 0, 0), b) == "2026-08-28"
    assert logical_date(datetime(2026, 8, 28, b - 1, 59, 59), b) == "2026-08-27"
    assert logical_date(datetime(2026, 8, 28, 0, 0, 0), b) == "2026-08-27"


def test_is_online_whitelist():
    """白名单模式：只认确定在线文案，其余一律离线"""
    assert is_online("微博在线了") is True
    assert is_online("微博在线") is True
    assert is_online("刚刚在线了") is False
    assert is_online("5分钟前在线了") is False
    assert is_online("昨天 22:00 在线了") is False
    assert is_online("") is False
    assert is_online(None) is False


def test_format_duration():
    assert format_duration(30) == "30秒"
    assert format_duration(60) == "1分钟"
    assert format_duration(3600) == "1小时"
    assert format_duration(86400 + 3600 * 2 + 60 * 3) == "1天2小时3分钟"


def test_cookie_expire_info():
    assert cookie_expire_info(None) is None
    assert cookie_expire_info("") is None
    assert cookie_expire_info("SUB=abc") is None          # 无 ALF 字段
    info = cookie_expire_info("ALF=1790429871; SUB=x")
    assert info is not None
    _expire, days = info
    assert days > 0


def test_append_session_same_day():
    """同一逻辑日不拆分"""
    m = Monitor(log_fn=lambda s: None)
    s = []
    m._append_session(s, datetime(2026, 8, 28, 10, 0), datetime(2026, 8, 28, 10, 30))
    assert len(s) == 1
    assert s[0]["date"] == "2026-08-28"
    assert s[0]["duration_minutes"] == 30.0


def test_append_session_cross_day_no_loss():
    """跨逻辑日界拆两段，且总时长无损"""
    m = Monitor(log_fn=lambda s: None)
    s = []
    start = datetime(2026, 8, 28, 18, 42, 49)
    end = datetime(2026, 8, 29, 20, 49, 0)
    m._append_session(s, start, end)
    assert len(s) == 2
    assert s[0]["date"] == "2026-08-28"
    assert s[1]["date"] == "2026-08-29"
    total = round(sum(x["duration_minutes"] for x in s), 1)
    origin = round((end - start).total_seconds() / 60, 1)
    assert abs(total - origin) < 0.2, f"拆分后有损: {total} vs {origin}"


def test_ongoing_session_always_counted():
    """进行中会话必须能计入统计（8/27 '在线时长被遗漏' bug 的回归测试）"""
    m = Monitor(log_fn=lambda s: None)
    sessions = []
    # 末尾 online 无配对 offline 时，配对阶段产不出会话
    m._build_sessions_from(
        [{"time": "2026-08-28 10:00:00", "status": "online", "desc1": "微博在线了"}],
        sessions)
    assert len(sessions) == 0
    # compute_stats 会额外补一个 ongoing 会话，确保它被统计接纳
    m._append_session(sessions, datetime(2026, 8, 28, 10, 0), beijing_now(), ongoing=True)
    assert len(sessions) == 1
    assert sessions[0].get("ongoing") is True


def test_backoff_steps_increase_and_cap():
    """432 退避逐级递增并封顶，复位后归零"""
    m = Monitor(log_fn=lambda s: None)
    m.rate_limited_alerted = True   # 跳过真实推送
    for _ in range(len(BACKOFF_STEPS)):
        m._enter_backoff(beijing_now())
    assert m.backoff_level == len(BACKOFF_STEPS)
    m._enter_backoff(beijing_now())     # 继续触发应封顶不越界
    assert m.backoff_level == len(BACKOFF_STEPS)
    m._reset_backoff()
    assert m.backoff_level == 0
    assert m.backoff_until is None


def test_pending_events_not_lost():
    """写入失败入队；成功后清空；持续失败则保留（事件绝不丢）"""
    m = Monitor(log_fn=lambda s: None)
    m._pending_events = [{"time": "2026-08-28 10:00:00", "status": "online", "desc1": "x"}]
    with mock.patch("monitor.write_json"):
        m._flush_pending_events()
    assert len(m._pending_events) == 0, "成功后应清空队列"

    m._pending_events = [{"time": "2026-08-28 10:00:00", "status": "online", "desc1": "x"}]
    with mock.patch("monitor.write_json", side_effect=PermissionError("locked")):
        m._flush_pending_events()
    assert len(m._pending_events) == 1, "持续失败时必须保留在队列，不能丢"


def test_432_not_retried_but_timeout_is():
    """432 风控不重试（只请求1次）；网络超时仍保留重试"""

    import urllib.error
    import weibo

    with mock.patch("urllib.request.urlopen") as mu:
        mu.side_effect = urllib.error.HTTPError("http://x", 432, "rate", {}, None)
        try:
            weibo.fetch_desc1(log_fn=lambda s: None)
            raise AssertionError("432 应抛出 RateLimitedError")
        except weibo.RateLimitedError:
            pass
        assert mu.call_count == 1, f"432 不应重试，实际请求 {mu.call_count} 次"

    with mock.patch("urllib.request.urlopen") as mu:
        mu.side_effect = TimeoutError("timed out")
        try:
            weibo.fetch_desc1(log_fn=lambda s: None)
        except Exception:
            pass
        assert mu.call_count > 1, "网络超时应保留重试"


if __name__ == "__main__":
    """无 pytest 时的简易运行器"""
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  PASS  {name}")
            except Exception as e:
                fails += 1
                print(f"  FAIL  {name}: {type(e).__name__}: {e}")
    print(f"\n{'全部通过' if fails == 0 else str(fails) + ' 个失败'}")
    sys.exit(1 if fails else 0)

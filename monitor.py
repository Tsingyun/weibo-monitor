"""微博监控核心逻辑"""

import time
from datetime import datetime, timedelta
from collections import defaultdict
from config import (
    EVENT_PATH, STATS_PATH, HISTORY_PATH,
    POLL_INTERVAL, REQUEST_TIMEOUT, RETRY_COUNT,
    DAY_BOUNDARY_HOUR, HEARTBEAT_ENABLED, HEARTBEAT_HOUR,
)
from utils import beijing_now, beijing_str, logical_date, is_online, read_json, write_json, format_duration

class Monitor:
    """微博超话在线状态监控器"""

    def __init__(self, log_fn=None):
        self.log = log_fn or print
        self.last_status = None
        self.last_desc1 = None
        self.consecutive_errors = 0
        self.error_alert_sent = False
        self.error_start_time = None
        self.last_heartbeat = None
        self.start_time = beijing_now()
        self.total_checks = 0
        self.total_notifications = 0

    # ---- 日志读写 ----
    def read_log(self):
        return read_json(EVENT_PATH, [])

    def write_log(self, arr):
        write_json(EVENT_PATH, arr)

    # ---- 统计 ----
    def compute_stats(self):
        logs = self.read_log()
        if not logs:
            return {"empty": True}

        now = beijing_now()
        today_logical = logical_date(now, DAY_BOUNDARY_HOUR)
        stats = {
            "empty": False,
            "generated_at": beijing_str(now),
            "total_events": len(logs),
            "current_status": logs[-1]["status"],
            "current_desc1": logs[-1].get("desc1", ""),
            "last_event_time": logs[-1]["time"],
        }

        # 在线会话
        sessions = []
        i = 0
        while i < len(logs) - 1:
            if logs[i]["status"] == "online":
                try:
                    start = datetime.strptime(logs[i]["time"], "%Y-%m-%d %H:%M:%S")
                    end = None
                    for j in range(i + 1, len(logs)):
                        if logs[j]["status"] == "offline":
                            end = datetime.strptime(logs[j]["time"], "%Y-%m-%d %H:%M:%S")
                            i = j + 1
                            break
                    if end is None:
                        i += 1
                        continue
                    duration = (end - start).total_seconds()
                    if duration > 0:
                        sessions.append({
                            "start": start.strftime("%Y-%m-%d %H:%M:%S"),
                            "end": end.strftime("%Y-%m-%d %H:%M:%S"),
                            "date": logical_date(start, DAY_BOUNDARY_HOUR),
                            "hour": start.hour,
                            "duration_minutes": round(duration / 60, 1),
                        })
                except Exception:
                    i += 1
            else:
                i += 1

        stats["sessions"] = sessions
        stats["total_sessions"] = len(sessions)
        stats["total_online_minutes"] = round(sum(s["duration_minutes"] for s in sessions), 1)

        # 每日统计
        daily = defaultdict(lambda: {"online_count": 0, "sessions": 0, "minutes": 0})
        for log in logs:
            try:
                dt = datetime.strptime(log["time"], "%Y-%m-%d %H:%M:%S")
                day = logical_date(dt, DAY_BOUNDARY_HOUR)
                if log["status"] == "online":
                    daily[day]["online_count"] += 1
            except Exception:
                pass
        for s in sessions:
            daily[s["date"]]["sessions"] += 1
            daily[s["date"]]["minutes"] += s["duration_minutes"]

        daily_list = [{"date": d, **daily[d]} for d in sorted(daily)]
        for d in daily_list:
            d["minutes"] = round(d["minutes"], 1)
        stats["daily"] = daily_list
        stats["today"] = dict(daily.get(today_logical, {"online_count": 0, "sessions": 0, "minutes": 0}))
        stats["today"]["date"] = today_logical

        # 时段分布
        hourly = defaultdict(int)
        for s in sessions:
            hourly[s["hour"]] += 1
        stats["hourly_distribution"] = [{"hour": h, "count": hourly[h]} for h in range(24)]

        stats["recent_logs"] = logs[-10:]
        stats["total_active_days"] = len({s["date"] for s in sessions if s["duration_minutes"] > 0})
        if sessions:
            stats["longest_session"] = max(sessions, key=lambda s: s["duration_minutes"])

        # 合并历史数据
        history = read_json(HISTORY_PATH, [])
        merged = {}
        for h in history:
            merged[h["date"]] = h["count"]
        for d in daily_list:
            if d["date"] not in merged:
                merged[d["date"]] = d["online_count"]
        stats["merged_daily"] = [{"date": d, "count": merged[d]} for d in sorted(merged)]

        return stats

    def save_stats(self):
        write_json(STATS_PATH, self.compute_stats())

    # ---- 状态管理 ----
    def restore_state(self):
        logs = self.read_log()
        if logs:
            last = logs[-1]
            self.last_status = last["status"]
            self.last_desc1 = last.get("desc1")

    # ---- 主巡检 ----
    def check_and_log(self):
        from weibo import fetch_desc1
        from notifier import notify as tg_notify, send as tg_send

        try:
            desc1 = fetch_desc1(log_fn=self.log)
            if not desc1:
                return

            # 恢复后清除错误计数
            if self.consecutive_errors > 0:
                duration = (beijing_now() - self.error_start_time).total_seconds()
                tg_send(f"✅ 微博连接恢复\n中断时间: {beijing_str(self.error_start_time)}\n恢复时间: {beijing_str()}\n中断时长: {format_duration(duration)}", log_fn=self.log)
                self.consecutive_errors = 0
                self.error_alert_sent = False

            self.total_checks += 1
            now = beijing_now()
            now_status = "online" if is_online(desc1) else "offline"

            # 仅在状态真正变化时通知
            if now_status == self.last_status:
                return  # 状态未变，跳过

            log_item = {"time": beijing_str(now), "status": now_status, "desc1": desc1}
            logs = self.read_log()
            logs.append(log_item)
            self.write_log(logs)
            self.save_stats()

            # 找到最近一次上线的时间，计算在线时长
            online_at = None
            for entry in reversed(logs[:-1]):  # 排除刚写入的
                if entry["status"] == "online":
                    online_at = datetime.strptime(entry["time"], "%Y-%m-%d %H:%M:%S")
                    break

            self.total_notifications += 1
            label = "🟢 上线" if now_status == "online" else "🔴 下线"
            msg = f"岁己SUI {label}\n{log_item['time']}\n{desc1}"
            if now_status == "offline" and online_at:
                dur = (now - online_at).total_seconds()
                msg += f"\n持续在线: {format_duration(dur)}"

            self.log(msg)
            tg_notify(msg, log_fn=self.log)

            self.last_status = now_status
            self.last_desc1 = desc1

        except Exception as e:
            self.consecutive_errors += 1
            if self.consecutive_errors == 1:
                self.error_start_time = beijing_now()
            self.log(f"[ERROR] 微博请求失败 (#{self.consecutive_errors}): {e}")
            if self.consecutive_errors >= 5 and not self.error_alert_sent:
                tg_send(f"⚠️ 微博请求连续失败 ({self.consecutive_errors}次)\n开始时间: {beijing_str(self.error_start_time)}\n请检查 Cookie 是否过期", log_fn=self.log)
                self.error_alert_sent = True

    # ---- 心跳 ----
    def heartbeat(self):
        now = beijing_now()
        if self.last_heartbeat is None or (now - self.last_heartbeat).total_seconds() >= 300:
            self.last_heartbeat = now
            self.log(f"[心跳] 运行中... checks={self.total_checks} notifications={self.total_notifications} status={self.last_status}")

    def daily_heartbeat(self):
        """每日 08:00 发送运行摘要"""
        from notifier import send as tg_send
        if not HEARTBEAT_ENABLED:
            return
        now = beijing_now()
        today8 = now.replace(hour=HEARTBEAT_HOUR, minute=0, second=0, microsecond=0)
        if now < today8:
            today8 -= timedelta(days=1)
        if hasattr(self, '_last_daily_hb') and (now - self._last_daily_hb).total_seconds() < 3600:
            return
        if abs((now - today8).total_seconds()) < POLL_INTERVAL + 5:
            elapsed = format_duration((now - self.start_time).total_seconds())
            status = "在线" if self.last_status == "online" else "离线"
            msg = (
                "————————\n"
                f"微博监控正常运行\n"
                f"运行时间: {elapsed}\n"
                f"累计检查: {self.total_checks}次\n"
                f"累计通知: {self.total_notifications}次\n"
                f"当前状态: {status}\n"
                f"服务器: Google Cloud e2-micro\n"
                "————————"
            )
            tg_send(msg, log_fn=self.log)
            self._last_daily_hb = now

    # ---- 主循环 ----
    def run(self):
        self.restore_state()
        self.log(f"[启动] 岁己SUI 微博监控")
        self.log(f"[配置] 轮询: {POLL_INTERVAL}s 超时: {REQUEST_TIMEOUT}s 重试: {RETRY_COUNT}次")
        self.log(f"[状态] {'在线' if self.last_status == 'online' else '离线'}")

        # 初始化 Telegram 命令模块
        import tg_commands
        import os
        tg_commands.init(os.path.join(os.path.dirname(os.path.abspath(__file__)), "data"))

        from notifier import send as tg_send
        tg_send(f"岁己SUI 微博监控已启动\n当前状态: {'在线' if self.last_status == 'online' else '离线'}\n命令: /status /today /stats /log /help", log_fn=self.log)

        try:
            while True:
                self.check_and_log()
                self.heartbeat()
                self.daily_heartbeat()
                tg_commands.check_updates(self)
                time.sleep(POLL_INTERVAL)
        except KeyboardInterrupt:
            self.log("[退出] 收到中断信号，正在关闭...")
        finally:
            self.log("[退出] 监控已停止")

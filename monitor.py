"""微博监控核心逻辑"""

import os
import time
from datetime import datetime, timedelta
from collections import defaultdict
from config import (
    EVENT_PATH, STATS_PATH, HISTORY_PATH, COVERAGE_PATH,
    POLL_INTERVAL, REQUEST_TIMEOUT, RETRY_COUNT,
    DAY_BOUNDARY_HOUR, HEARTBEAT_ENABLED, HEARTBEAT_HOUR,
    COVERAGE_BUCKET_MINUTES, MISSING_EVENT_THRESHOLD,
    BACKOFF_STEPS, COOKIE_EXPIRE_WARN_DAYS, STATS_REFRESH_SECONDS,
    MIN_SESSION_SECONDS, ARCHIVE_DAILY_PATH,
)
from utils import (beijing_now, beijing_str, logical_date, is_online,
                   read_json, write_json, format_duration, cookie_expire_info)

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
        self._first_poll = True  # 跳过恢复状态后的首次通知
        self._last_cov_bucket = None  # 上次写入的覆盖率分桶（避免重复写盘）
        self.session_start = None  # 本次上线的起点（推送"持续在线"用内存值，不依赖 events.json）
        # ---- A3 风控退避 / A5 暂停态 ----
        self.backoff_level = 0            # 当前退避等级（0 = 正常轮询）
        self.backoff_until = None         # 退避截止时间（在此之前不巡检）
        self.rate_limited_alerted = False # 本轮退避是否已推送过告警
        self.paused = False               # Cookie 过期暂停态（进程存活等待热重载）
        self._env_mtime = None            # .env 修改时间（热重载检测）
        # ---- B1 事件补写队列 / B2 统计定时刷新 / B3 今日计数 ----
        self._pending_events = []         # 写入失败待补写的事件
        self._last_stats_save = None      # 上次 stats 落盘时间
        self._today_online_date = None    # 今日上线计数所属逻辑日
        self._today_online_count = 0      # 今日上线次数（内存计数，不依赖 events.json）
        # ---- C1 抖动去重 / C4 推送增强 ----
        self._last_status_change = None   # 上次状态变化时刻（用于去抖判断）
        self._last_offline_at = None      # 上次下线时刻（用于"距上次下线"）

    # ---- 日志读写 ----
    def read_log(self):
        return read_json(EVENT_PATH, [])

    def write_log(self, arr):
        write_json(EVENT_PATH, arr)

    def _append_session(self, sessions, start_dt, end_dt, ongoing=False):
        """将会话加入列表；跨越逻辑日界时自动拆成两段，各自归属对应日期（B4）

        例：昨晚 23:00 上线、次日 10:00 下线，日界 08:00 时
            → 拆为 [23:00, 08:00) 归昨天 + [08:00, 10:00) 归今天
        这样"今日在线时长"才不会漏掉跨凌晨的那一段。
        """
        start_ld = logical_date(start_dt, DAY_BOUNDARY_HOUR)
        end_ld = logical_date(end_dt, DAY_BOUNDARY_HOUR)
        if start_ld == end_ld:
            dur = (end_dt - start_dt).total_seconds()
            if dur <= 0:
                return
            item = {
                "start": start_dt.strftime("%Y-%m-%d %H:%M:%S"),
                "end": end_dt.strftime("%Y-%m-%d %H:%M:%S"),
                "date": start_ld,
                "hour": start_dt.hour,
                "duration_minutes": round(dur / 60, 1),
            }
            if ongoing:
                item["ongoing"] = True
            sessions.append(item)
            return
        # 跨日界：以 end_ld 当天的日界时刻为分界，拆成两段
        boundary = datetime.strptime(end_ld, "%Y-%m-%d") + timedelta(hours=DAY_BOUNDARY_HOUR)
        first_secs = (boundary - start_dt).total_seconds()
        second_secs = (end_dt - boundary).total_seconds()
        if first_secs > 0:
            sessions.append({
                "start": start_dt.strftime("%Y-%m-%d %H:%M:%S"),
                "end": boundary.strftime("%Y-%m-%d %H:%M:%S"),
                "date": start_ld,
                "hour": start_dt.hour,
                "duration_minutes": round(first_secs / 60, 1),
            })
        if second_secs > 0:
            item = {
                "start": boundary.strftime("%Y-%m-%d %H:%M:%S"),
                "end": end_dt.strftime("%Y-%m-%d %H:%M:%S"),
                "date": end_ld,
                "hour": boundary.hour,
                "duration_minutes": round(second_secs / 60, 1),
            }
            if ongoing:
                item["ongoing"] = True
            sessions.append(item)

    def _build_sessions_from(self, logs, sessions):
        """从事件列表构建会话（配对 online→offline），供 compute_stats 与归档工具复用"""
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
                        # B4: 跨逻辑日界的会话自动拆分归属
                        self._append_session(sessions, start, end)
                except Exception:
                    i += 1
            else:
                i += 1

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
        self._build_sessions_from(logs, sessions)

        # 当前正在进行中的会话（尚未下线）: 纳入统计, 避免实时在线时长被遗漏
        # 若 events 末尾是 online 且无对应 offline, 补一个 end=now 的 ongoing session,
        # 下游 daily/today/total_online_minutes/longest_session 都会自然包含这段
        if logs and logs[-1]["status"] == "online":
            try:
                last_time = datetime.strptime(logs[-1]["time"], "%Y-%m-%d %H:%M:%S")
                duration = (now - last_time).total_seconds()
                if duration > 0:
                    # B4: 同样走拆分逻辑，跨天在线时长会分给对应两天
                    self._append_session(sessions, last_time, now, ongoing=True)
            except Exception:
                pass

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

        # B5: 合并已归档事件的每日聚合（旧事件移入 archive/ 后，历史统计依然完整）
        arch = read_json(ARCHIVE_DAILY_PATH, {})
        if arch:
            for d, v in arch.items():
                if d in daily:
                    daily[d]["online_count"] += v.get("online_count", 0)
                    daily[d]["sessions"] += v.get("sessions", 0)
                    daily[d]["minutes"] += v.get("minutes", 0)
                else:
                    daily[d] = {"online_count": v.get("online_count", 0),
                                "sessions": v.get("sessions", 0),
                                "minutes": v.get("minutes", 0)}

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

        # 合并历史数据 → 连续化序列，明确标记「因故未统计」的缺口
        history = read_json(HISTORY_PATH, [])
        cov = read_json(COVERAGE_PATH, {})
        merged = {}
        source = {}
        for h in history:
            merged[h["date"]] = h.get("count")
            source[h["date"]] = "history"   # 2025 年归档（来自历史整合）
        for d in daily_list:
            merged[d["date"]] = d["online_count"]
            source[d["date"]] = "current"   # 当前监控期（events.json 实时计算）
        if merged:
            start = min(merged)
            end = now.strftime("%Y-%m-%d")
            cur = datetime.strptime(start, "%Y-%m-%d")
            end_d = datetime.strptime(end, "%Y-%m-%d")
            seq = []
            while cur <= end_d:
                ds = cur.strftime("%Y-%m-%d")
                has_data = ds in source                 # history 或 current 有记录
                has_cov = ds in cov and bool(cov[ds])   # 监控在跑（coverage 文件有记录）
                if has_data:
                    # 历史归档或当前监控期，按实计数
                    seq.append({"date": ds, "count": merged[ds], "missing": False, "source": source[ds]})
                elif has_cov:
                    # 监控在跑但当天 0 次上线（已统计，不算缺口）
                    seq.append({"date": ds, "count": 0, "missing": False, "source": "monitored"})
                else:
                    # 区间内但完全无数据 → 缺口（未监控 / 数据缺失）
                    seq.append({"date": ds, "count": None, "missing": True, "source": "gap"})
                cur += timedelta(days=1)
            stats["merged_daily"] = seq
            stats["gap_days"] = [x["date"] for x in seq if x["missing"]]
        else:
            stats["merged_daily"] = []
            stats["gap_days"] = []

        return stats

    def save_stats(self):
        write_json(STATS_PATH, self.compute_stats())

    # ---- 覆盖率追踪 ----
    def mark_coverage(self):
        """记录一次成功轮询到覆盖率文件（按 COVERAGE_BUCKET_MINUTES 分桶）"""
        now = beijing_now()
        date_str = now.strftime("%Y-%m-%d")
        minutes = now.hour * 60 + now.minute
        bucket = minutes // COVERAGE_BUCKET_MINUTES
        # 同一分桶不重复写盘
        if self._last_cov_bucket == (date_str, bucket):
            return
        self._last_cov_bucket = (date_str, bucket)
        cov = read_json(COVERAGE_PATH, {})
        day = cov.get(date_str, [])
        if bucket not in day:
            day.append(bucket)
            day.sort()
            cov[date_str] = day
            write_json(COVERAGE_PATH, cov)

    def compute_coverage(self):
        """计算覆盖率与缺失时段（兼容无 coverage.json 的历史数据）"""
        logs = self.read_log()
        buckets_per_day = 24 * 60 // COVERAGE_BUCKET_MINUTES
        cov = read_json(COVERAGE_PATH, {})

        if logs:
            first_date = logs[0]["time"][:10]
        else:
            first_date = beijing_now().strftime("%Y-%m-%d")
        today = beijing_now().strftime("%Y-%m-%d")

        # 逐日遍历
        days = []
        d = datetime.strptime(first_date, "%Y-%m-%d")
        end = datetime.strptime(today, "%Y-%m-%d")
        total_buckets = 0
        covered_buckets = 0
        while d <= end:
            ds = d.strftime("%Y-%m-%d")
            # 优先用覆盖率文件
            if ds in cov and cov[ds]:
                covered = set(cov[ds])
                pct = round(len(covered) / buckets_per_day * 100, 1)
                # 计算日内缺失时段（连续未覆盖分桶 → 时间范围）
                missing = []
                i = 0
                while i < buckets_per_day:
                    if i not in covered:
                        j = i
                        while j < buckets_per_day and j not in covered:
                            j += 1
                        start_min = i * COVERAGE_BUCKET_MINUTES
                        end_min = j * COVERAGE_BUCKET_MINUTES
                        missing.append([start_min, min(end_min, 1440)])
                        i = j
                    else:
                        i += 1
                status = "full" if pct >= 99 else ("partial" if pct > 0 else "missing")
            else:
                # 回退：以当日是否有事件判断
                day_events = [e for e in logs if e["time"][:10] == ds]
                if day_events:
                    pct = 100.0
                    missing = []
                    status = "full"
                else:
                    pct = 0.0
                    missing = [[0, 1440]]
                    status = "missing"
            total_buckets += buckets_per_day
            covered_buckets += int(round(pct / 100 * buckets_per_day))
            days.append({
                "date": ds,
                "pct": pct,
                "status": status,
                "missing_ranges": missing,
                "event_count": len([e for e in logs if e["time"][:10] == ds]),
            })
            d += timedelta(days=1)

        # 缺失天数与跨天缺失时段
        missing_days = [x["date"] for x in days if x["status"] == "missing"]
        # 合并连续缺失天为区间
        missing_spans = []
        if missing_days:
            span_start = missing_days[0]
            prev = missing_days[0]
            for md in missing_days[1:]:
                if (datetime.strptime(md, "%Y-%m-%d") - datetime.strptime(prev, "%Y-%m-%d")).days == 1:
                    prev = md
                else:
                    missing_spans.append([span_start, prev])
                    span_start = md
                    prev = md
            missing_spans.append([span_start, prev])

        # 疑似不完整天（有数据但事件数极少，可能漏采）
        suspicious_days = [x["date"] for x in days
                           if x["status"] != "missing"
                           and 0 < x["event_count"] < MISSING_EVENT_THRESHOLD]

        overall_pct = round(covered_buckets / total_buckets * 100, 1) if total_buckets else 0

        return {
            "days": days,
            "missing_days": missing_days,
            "missing_spans": missing_spans,
            "suspicious_days": suspicious_days,
            "overall_pct": overall_pct,
            "bucket_minutes": COVERAGE_BUCKET_MINUTES,
        }

    # ---- 状态管理 ----
    def restore_state(self):
        logs = self.read_log()
        if logs:
            last = logs[-1]
            self.last_status = last["status"]
            self.last_desc1 = last.get("desc1")

    # ---- A3 风控退避 / A5 暂停态 / Cookie 热重载 ----
    def _env_path(self):
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")

    def _reset_backoff(self, reason=""):
        """解除退避，恢复正常轮询"""
        if self.backoff_level or self.backoff_until:
            suffix = f"（{reason}）" if reason else ""
            self.log(f"[恢复] 轮询已复位为 {POLL_INTERVAL}s{suffix}")
        self.backoff_level = 0
        self.backoff_until = None
        self.rate_limited_alerted = False

    def _enter_backoff(self, now):
        """遭遇 432 风控：提升退避等级并设定恢复时间（首次推送一次告警）"""
        self.backoff_level = min(self.backoff_level + 1, len(BACKOFF_STEPS))
        secs = BACKOFF_STEPS[self.backoff_level - 1]
        self.backoff_until = now + timedelta(seconds=secs)
        self.log(f"[退避] 触发 432 风控，等级 {self.backoff_level}/{len(BACKOFF_STEPS)}，"
                 f"{secs}s 后重试（{beijing_str(self.backoff_until)}）")
        if not self.rate_limited_alerted:
            self.rate_limited_alerted = True
            try:
                from notifier import send as tg_send
                tg_send(
                    "⚠️ 微博风控 (HTTP 432)\n已自动降频轮询（避免高频请求加速 Cookie 失效）\n"
                    f"下次重试: {beijing_str(self.backoff_until)}\n"
                    "若长时间未恢复，请更换 Cookie 更新到 .env（会自动热重载，无需重启）",
                    log_fn=self.log,
                    bark_title="⚠️ 微博风控降频", bark_level="passive", bark_sound="")
            except Exception as e:
                self.log(f"[WARN] 风控告警推送失败: {e}")

    def _env_changed(self):
        """检测 .env 是否被修改（更换 Cookie）"""
        try:
            mtime = os.path.getmtime(self._env_path())
        except Exception:
            return False
        if self._env_mtime is None:
            self._env_mtime = mtime
            return False
        if mtime != self._env_mtime:
            self._env_mtime = mtime
            return True
        return False

    def _reload_env(self):
        """热重载 .env（换 Cookie 后无需重启进程）"""
        try:
            import importlib
            import config
            importlib.reload(config)
            self.log("[Cookie] 检测到 .env 变更，已热重载配置")
            self._reset_backoff(reason="Cookie 已更新")
            if self.paused:
                self.paused = False
                self.log("[Cookie] 已解除暂停态，恢复巡检")
            return True
        except Exception as e:
            self.log(f"[WARN] .env 热重载失败: {e}")
            return False

    def check_cookie_expiry(self):
        """A2: Cookie 临近到期提醒（每天最多一次）"""
        try:
            import config
            info = cookie_expire_info(config.WEIBO_COOKIE)
            if not info:
                return
            expire, days_left = info
            if days_left <= COOKIE_EXPIRE_WARN_DAYS:
                today = beijing_now().strftime("%Y-%m-%d")
                if getattr(self, "_cookie_warn_date", None) != today:
                    self._cookie_warn_date = today
                    from notifier import send as tg_send
                    tg_send(
                        f"⚠️ Cookie 即将过期\n剩余: {days_left:.1f} 天\n"
                        f"过期时间: {beijing_str(expire)}\n"
                        "请及时更新 .env 中的 WEIBO_COOKIE（更新后自动热重载，无需重启）",
                        log_fn=self.log,
                        bark_title="⚠️ Cookie 即将过期", bark_level="active", bark_sound="alarm")
        except Exception as e:
            self.log(f"[WARN] Cookie 到期检查失败: {e}")

    # ---- B1 事件补写 / B2 统计定时刷新 ----
    def _flush_pending_events(self):
        """B1: 补写此前写入失败的事件（按时间有序合并回 events.json）

        根治事件丢失：events.json 被锁导致写入失败时，事件进内存队列，
        后续轮次自动补写并按时间排序，保证事件流完整、统计不丢。
        """
        if not self._pending_events:
            return
        try:
            logs = self.read_log()
            merged = logs + self._pending_events
            merged.sort(key=lambda e: e.get("time", ""))
            self.write_log(merged)
            self.save_stats()
            self.log(f"[补写] 已补写 {len(self._pending_events)} 条此前写入失败的事件")
            self._pending_events = []
            self._last_stats_save = beijing_now()
        except Exception as fe:
            self.log(f"[WARN] 补写事件失败，继续保留在队列（当前 {len(self._pending_events)} 条）: {fe}")

    def _stats_due(self):
        """B2: 是否到了定时刷新 stats 的时间（让 ongoing 会话时长持续增长）"""
        if STATS_REFRESH_SECONDS <= 0:
            return False
        now = beijing_now()
        if self._last_stats_save is None:
            self._last_stats_save = now
            return True
        if (now - self._last_stats_save).total_seconds() >= STATS_REFRESH_SECONDS:
            self._last_stats_save = now
            return True
        return False

    # ---- 主巡检 ----
    def check_and_log(self):
        from weibo import fetch_desc1, CookieExpiredError, RateLimitedError
        from notifier import notify as tg_notify, send as tg_send

        try:
            desc1 = fetch_desc1(log_fn=self.log)
            if not desc1:
                return
            # 请求成功 → 解除风控退避
            if self.backoff_level or self.backoff_until:
                self._reset_backoff(reason="接口已恢复")

            # 覆盖率追踪（本地写入，失败仅记日志，不计为连接错误）
            try:
                self.mark_coverage()
            except Exception as fe:
                self.log(f"[WARN] 覆盖率记录失败（忽略）: {fe}")

            # 恢复后清除错误计数（consecutive_errors 仅由真实网络/API 错误累积）
            if self.consecutive_errors > 0:
                duration = (beijing_now() - self.error_start_time).total_seconds()
                # 仅在确实发生过持续中断（已发过严重告警）时才推送"连接恢复"，
                # 避免瞬时抖动产生的无意义推送
                if self.error_alert_sent:
                    tg_send(f"✅ 微博连接恢复\n中断时间: {beijing_str(self.error_start_time)}\n恢复时间: {beijing_str()}\n中断时长: {format_duration(duration)}", log_fn=self.log,
                            bark_title="微博连接恢复 ✅", bark_level="active", bark_sound="bobibo")
                self.consecutive_errors = 0
                self.error_alert_sent = False

            self.total_checks += 1
            now = beijing_now()
            now_status = "online" if is_online(desc1) else "offline"

            # 首次轮询：只同步状态，不发送通知（避免启动时发送过往消息）
            if self._first_poll:
                self._first_poll = False
                self.last_status = now_status
                self.last_desc1 = desc1
                self._last_status_change = now   # C1: 初始化去抖基准，避免首轮被误判为抖动
                # 同步本次会话起点, 避免 events 写入失败时推送 dur 错位
                if now_status == "online":
                    try:
                        _logs = self.read_log()
                        # events 末条可能是 offline, 找最近一条 online 作为延续起点
                        _t = None
                        for _e in reversed(_logs):
                            if _e.get("status") == "online":
                                _t = _e["time"]
                                break
                        self.session_start = datetime.strptime(_t, "%Y-%m-%d %H:%M:%S") if _t else now
                    except Exception:
                        self.session_start = now
                else:
                    self.session_start = None
                self.log(f"[就绪] 首次轮询完成，当前状态: {'在线' if now_status == 'online' else '离线'}")
                return

            # 仅在状态真正变化时通知
            if now_status == self.last_status:
                return  # 状态未变，跳过

            today_logical = logical_date(now, DAY_BOUNDARY_HOUR)
            # 状态真变化: online 时记本次上线起点(内存) + 今日次数(内存计数)
            if now_status == "online":
                self.session_start = now
                # B3: 今日上线次数用内存计数（不依赖 events.json，写入失败也不会少算）
                if self._today_online_date != today_logical:
                    self._today_online_date = today_logical
                    self._today_online_count = 0
                self._today_online_count += 1

            log_item = {"time": beijing_str(now), "status": now_status, "desc1": desc1}
            # B1: 先补写此前写入失败的事件，再写本轮事件
            self._flush_pending_events()
            # 本地文件写入与连接逻辑解耦：写入失败只记日志，不计为"连接错误"，
            # 也不影响本轮推送与状态判断（utils.write_json 已做原子写+重试）
            try:
                logs = self.read_log()
                logs.append(log_item)
                self.write_log(logs)
                self.save_stats()
                self._last_stats_save = now
            except Exception as fe:
                # B1: 写入失败 → 入队，后续轮次自动补写（不再永久丢失事件）
                self.log(f"[WARN] 本地状态写入失败（不影响本轮推送，已入队待补写）: {fe}")
                self._pending_events.append(log_item)

            # 本次上线起点优先用内存 session_start, 不依赖 events.json 完整性
            # (兜底: 若 session_start 缺失才从 logs 反查, 兼容异常重启场景)
            online_at = self.session_start
            if online_at is None:
                for entry in reversed(logs[:-1]):
                    try:
                        if entry["status"] == "online":
                            online_at = datetime.strptime(entry["time"], "%Y-%m-%d %H:%M:%S")
                            break
                    except Exception:
                        continue

            # C1: 抖动去重 —— 上一状态持续过短（多为接口抖动/误判）时抑制本次推送
            suppress_push = False
            if self._last_status_change is not None and MIN_SESSION_SECONDS > 0:
                held = (now - self._last_status_change).total_seconds()
                if held < MIN_SESSION_SECONDS:
                    suppress_push = True
                    self.log(f"[去抖] 上次状态仅持续 {held:.0f}s（< {MIN_SESSION_SECONDS}s），"
                             f"抑制本次推送（事件仍已记录到 events.json）")
            self._last_status_change = now
            if suppress_push:
                # 事件已写入，仅跳过推送与计数，保证数据不丢
                self.last_status = now_status
                if now_status == "offline":
                    self._last_offline_at = now
                    self.session_start = None
                return

            self.total_notifications += 1
            label = "🟢 上线" if now_status == "online" else "🔴 下线"
            msg = f"岁己SUI {label}\n{log_item['time']}\n{desc1}"
            if now_status == "offline" and online_at:
                dur = (now - online_at).total_seconds()
                msg += f"\n持续在线: {format_duration(dur)}"
            # C4: 上线时补充"距上次下线"间隔，便于判断隔了多久才再来
            if now_status == "online" and self._last_offline_at:
                gap = (now - self._last_offline_at).total_seconds()
                msg += f"\n距上次下线: {format_duration(gap)}"

            self.log(msg)
            bark_title = "岁己SUI 上线啦 🟢" if now_status == "online" else "岁己SUI 下线了 🔴"
            # 副标题: 上线显示今日次数, 下线显示本次持续时长 (信息分层)
            # B3: 今日次数改用内存计数（不依赖 events.json，即便写入失败也不会少算）
            today_online = self._today_online_count
            if now_status == "online":
                bark_subtitle = f"今日第 {today_online} 次上线"
            else:
                bark_subtitle = f"持续在线 {format_duration(dur)}" if online_at else "已离线"
            tg_notify(msg, log_fn=self.log,
                      bark_title=bark_title, bark_level="active", bark_sound="bobibo",
                      bark_subtitle=bark_subtitle)

            self.last_status = now_status
            self.last_desc1 = desc1
            # 下线后清空 session_start, 下次真上线时重设
            if now_status == "offline":
                self._last_offline_at = now
                self.session_start = None

        except CookieExpiredError:
            # A5: 改为暂停态存活（不再 raise 终止进程），更新 .env 后自动热重载恢复
            if not self.paused:
                self.paused = True
                self.log("[FATAL] Cookie 已过期，进入暂停态（更新 .env 后自动恢复，无需重启）")
                tg_send("🚨 Cookie 已过期！\n请更新 .env 中的 WEIBO_COOKIE\n"
                        "（更新后进程会自动热重载恢复，无需重启）", log_fn=self.log,
                        bark_title="⚠️ Cookie 已过期", bark_level="critical", bark_sound="alarm",
                        bark_call="1", bark_volume=10, bark_fallback=True)
            return

        except RateLimitedError:
            # A3: 432 风控 → 进入退避（不重试、不刷接口）
            self._enter_backoff(beijing_now())
            return

        except Exception as e:
            self.consecutive_errors += 1
            if self.consecutive_errors == 1:
                self.error_start_time = beijing_now()
            self.log(f"[ERROR] 微博请求失败 (#{self.consecutive_errors}): {e}")
            if self.consecutive_errors >= 5 and not self.error_alert_sent:
                tg_send(f"⚠️ 微博请求连续失败 ({self.consecutive_errors}次)\n开始时间: {beijing_str(self.error_start_time)}\n请检查 Cookie 是否过期", log_fn=self.log,
                        bark_title="⚠️ 微博请求连续失败", bark_level="critical", bark_sound="alarm",
                        bark_call="1", bark_volume=10, bark_fallback=True)
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
        # C3: 正常时间窗内发送；若 08:00 时进程未运行（错过窗口），
        #     今天已过该时点且当天还没发过 → 启动后补发一次，避免整天漏掉摘要
        in_window = abs((now - today8).total_seconds()) < POLL_INTERVAL + 5
        already_today = (hasattr(self, '_last_daily_hb')
                         and self._last_daily_hb.strftime("%Y-%m-%d") == now.strftime("%Y-%m-%d"))
        missed_today = (now.hour >= HEARTBEAT_HOUR) and not already_today
        if in_window or missed_today:
            elapsed = format_duration((now - self.start_time).total_seconds())
            status = "在线" if self.last_status == "online" else "离线"
            msg = (
                "————————\n"
                f"微博监控正常运行\n"
                f"运行时间: {elapsed}\n"
                f"累计检查: {self.total_checks}次\n"
                f"累计通知: {self.total_notifications}次\n"
                f"当前状态: {status}\n"
                "————————"
            )
            tg_send(msg, log_fn=self.log,
                    bark_title="微博监控运行摘要", bark_level="passive", bark_sound="")
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
        tg_send(f"岁己SUI 微博监控已启动\n命令: /status /today /stats /log /help", log_fn=self.log,
                bark_title="监控已启动", bark_level="passive", bark_sound="")

        try:
            while True:
                # A3/A5: .env 变更（换 Cookie）→ 热重载并立即恢复正常轮询
                if self._env_changed():
                    self._reload_env()
                # A5: 暂停态（Cookie 过期）只等待，不巡检
                if self.paused:
                    time.sleep(min(60, max(POLL_INTERVAL, 15)))
                    continue
                # A3: 退避期内跳过巡检（不重试、不刷接口）
                now = beijing_now()
                if self.backoff_until and now < self.backoff_until:
                    wait = (self.backoff_until - now).total_seconds()
                    time.sleep(max(1, min(wait, POLL_INTERVAL)))
                    continue
                self.check_and_log()
                # B2: 定时刷新 stats（让 ongoing 会话时长持续增长，WebUI 数据不再陈旧）
                if self._stats_due():
                    try:
                        self.save_stats()
                    except Exception as fe:
                        self.log(f"[WARN] 定时刷新 stats 失败: {fe}")
                self.heartbeat()
                self.daily_heartbeat()
                self.check_cookie_expiry()   # A2: Cookie 到期预警（内部每天一次）
                tg_commands.check_updates(self)
                time.sleep(POLL_INTERVAL)
        except KeyboardInterrupt:
            self.log("[退出] 收到中断信号，正在关闭...")
        finally:
            self.log("[退出] 监控已停止")

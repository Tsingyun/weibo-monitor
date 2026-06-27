#!/usr/bin/env python3
"""
岁己SUI 微博在线状态监控系统
- 轮询微博超话 API，检测上下线状态
- Telegram 通知
- 本地 WebUI 数据面板
- 数据统计 & 留档
"""

import os, sys, json, re, time
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from config import *
from weibo import fetch_desc1
from notifier import notify, send as tg_send

# ===== 工具函数 =====
def beijing_now():
    return datetime.utcnow() + timedelta(hours=8)

def beijing_str(dt=None):
    if dt is None:
        dt = beijing_now()
    return dt.strftime("%Y-%m-%d %H:%M:%S")

def logical_date(dt):
    """按岁己作息计算逻辑日期：凌晨 0:00~3:59 归属前一天"""
    if dt.hour < DAY_BOUNDARY_HOUR:
        return (dt - timedelta(days=1)).strftime("%Y-%m-%d")
    return dt.strftime("%Y-%m-%d")

def read_json(path, default=None):
    try:
        if not os.path.exists(path):
            return default if default is not None else []
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default if default is not None else []

def write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def is_online(desc1):
    return desc1 and desc1.strip() == "微博在线了"

def parse_desc1_time(desc1, now):
    if not desc1:
        return None
    desc1 = desc1.strip()
    m = re.match(r"(\d+)分钟前在线了", desc1)
    if m:
        return now - timedelta(minutes=int(m.group(1)))
    m = re.match(r"(\d+)小时前在线了", desc1)
    if m:
        return now - timedelta(hours=int(m.group(1)))
    m = re.match(r"昨天 (\d{2}):(\d{2})在线了", desc1)
    if m:
        yesterday = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
        return yesterday.replace(hour=int(m.group(1)), minute=int(m.group(2)))
    return None

# ===== 日志操作 =====
def read_log():
    return read_json(LOG_PATH, [])

def write_log(log_arr):
    write_json(LOG_PATH, log_arr)

# ===== 统计计算 =====
def compute_stats():
    logs = read_log()
    if not logs:
        return {"empty": True, "message": "暂无数据"}

    now = beijing_now()
    today_logical = logical_date(now)
    stats = {
        "empty": False,
        "generated_at": beijing_str(now),
        "total_events": len(logs),
        "current_status": None,
        "current_desc1": None,
        "last_event_time": None,
    }

    last = logs[-1]
    stats["current_status"] = last["status"]
    stats["current_desc1"] = last.get("desc1", "")
    stats["last_event_time"] = last["time"]

    # 在线会话（online → offline 为一个会话）
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
                        "date": logical_date(start),
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

    # 每日统计（按逻辑日期）
    from collections import defaultdict
    daily = defaultdict(lambda: {"online_count": 0, "sessions": 0, "minutes": 0})
    for log in logs:
        try:
            dt = datetime.strptime(log["time"], "%Y-%m-%d %H:%M:%S")
            day = logical_date(dt)
            if log["status"] == "online":
                daily[day]["online_count"] += 1
        except Exception:
            pass
    for s in sessions:
        daily[s["date"]]["sessions"] += 1
        daily[s["date"]]["minutes"] += s["duration_minutes"]

    daily_list = []
    for day in sorted(daily.keys()):
        d = daily[day]
        d["date"] = day
        d["minutes"] = round(d["minutes"], 1)
        daily_list.append(d)
    stats["daily"] = daily_list

    # 今日
    stats["today"] = dict(daily.get(today_logical, {"online_count": 0, "sessions": 0, "minutes": 0}))
    stats["today"]["date"] = today_logical

    # 时段分布（按小时）
    hourly = defaultdict(int)
    for s in sessions:
        hourly[s["hour"]] += 1
    stats["hourly_distribution"] = [{"hour": h, "count": hourly[h]} for h in range(24)]

    # 最近10条
    stats["recent_logs"] = logs[-10:]

    # 活跃天数
    active_days = {s["date"] for s in sessions if s["duration_minutes"] > 0}
    stats["total_active_days"] = len(active_days)

    if sessions:
        stats["longest_session"] = max(sessions, key=lambda s: s["duration_minutes"])

    # 加载历史数据
    history = read_json(HISTORY_PATH, [])
    stats["history"] = history

    # 合并历史 + 新数据的每日上线次数（按逻辑日期）
    merged_daily = {}
    for h in history:
        merged_daily[h["date"]] = h["count"]
    for d in daily_list:
        key = d["date"]
        if key not in merged_daily:
            merged_daily[key] = d["online_count"]
        else:
            # 历史已有，保持不变（历史数据已经过手动调整）
            pass
    stats["merged_daily"] = [{"date": d, "count": merged_daily[d]} for d in sorted(merged_daily.keys())]

    return stats

def save_stats():
    write_json(STATS_PATH, compute_stats())

def get_stats():
    return read_json(STATS_PATH, {"empty": True}) or compute_stats()

# ===== 监控主逻辑 =====
last_status = None
consecutive_errors = 0
error_alert_sent = False
last_heartbeat = None

def check_and_log():
    global last_status, consecutive_errors, error_alert_sent
    try:
        desc1 = fetch_desc1()
        if not desc1:
            return
        consecutive_errors = 0
        error_alert_sent = False
        now_status = "online" if is_online(desc1) else "offline"
        now = beijing_now()
        desc_time = parse_desc1_time(desc1, now)
        log_arr = read_log()
        last_log = log_arr[-1] if log_arr else None
        should_record = True
        if desc_time and last_log:
            try:
                last_time = datetime.strptime(last_log["time"], "%Y-%m-%d %H:%M:%S")
                if abs((desc_time - last_time).total_seconds()) <= 120:
                    should_record = False
            except Exception:
                pass
        if last_log and now_status == last_log["status"]:
            should_record = False
        if should_record:
            log_item = {"time": beijing_str(now), "status": now_status, "desc1": desc1}
            log_arr.append(log_item)
            write_log(log_arr)
            save_stats()
            label = "🟢 上线" if now_status == "online" else "🔴 下线"
            notify(f"岁己SUI {label}\n{log_item['time']}\n{desc1}")
            last_status = now_status
    except Exception as e:
        consecutive_errors += 1
        ns = beijing_str()
        print(f"[{ns}] API 请求失败 (#{consecutive_errors}): {e}")
        if consecutive_errors >= 5 and not error_alert_sent:
            tg_send(f"⚠️ 微博监控异常\n连续 {consecutive_errors} 次 API 请求失败\n{ns}\n请检查 Cookie 是否过期")
            error_alert_sent = True

def heartbeat():
    global last_heartbeat
    now = beijing_now()
    if last_heartbeat is None or (now - last_heartbeat).total_seconds() >= 300:
        last_heartbeat = now
        print(f"[心跳] 监控运行中... {beijing_str(now)}  lastStatus={last_status}")

def monitor_loop():
    global last_status
    log_arr = read_log()
    if log_arr:
        last_status = log_arr[-1]["status"]
    print(f"[启动] 岁己SUI 微博在线状态监控")
    print(f"[配置] 轮询间隔: {POLL_INTERVAL}秒")
    print(f"[通知] Telegram: {'已配置' if notifier.enabled() else '未配置'}")
    print(f"[日志] {LOG_PATH}")
    print()
    notify(f"岁己SUI 微博监控已启动\n当前状态: {'在线' if last_status == 'online' else '离线'}")
    while True:
        check_and_log()
        heartbeat()
        time.sleep(POLL_INTERVAL)

# ===== WebUI =====
HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>岁己SUI · 微博在线监控</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Calistoga&family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
:root {
  --bg: #FAFAFA; --fg: #0F172A; --muted: #F1F5F9; --muted-fg: #64748B;
  --accent: #0052FF; --accent2: #4D7CFF; --accent-fg: #FFFFFF;
  --border: #E2E8F0; --card: #FFFFFF; --radius: 16px; --radius-sm: 12px;
  --green: #16a34a; --red: #dc2626;
}
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family:'Inter',system-ui,sans-serif; background:var(--bg); color:var(--fg); min-height:100vh; line-height:1.6; -webkit-font-smoothing:antialiased; }
.gradient-text { background:linear-gradient(135deg,var(--accent),var(--accent2)); -webkit-background-clip:text; background-clip:text; color:transparent; }
.container { max-width:1200px; margin:0 auto; padding:2rem 1.5rem; }
header { display:flex; justify-content:space-between; align-items:flex-start; padding:3rem 0 2rem; flex-wrap:wrap; gap:1rem; }
.header-left h1 { font-family:'Calistoga',Georgia,serif; font-size:2.5rem; font-weight:normal; letter-spacing:-0.02em; line-height:1.15; }
.header-left p { color:var(--muted-fg); font-size:0.95rem; }
.badge { display:inline-flex; align-items:center; gap:0.5rem; padding:0.4rem 1rem; border-radius:9999px; font-family:'JetBrains Mono',monospace; font-size:0.7rem; text-transform:uppercase; letter-spacing:0.15em; border:1px solid rgba(0,82,255,0.3); background:rgba(0,82,255,0.04); color:var(--accent); }
.badge .dot { width:8px; height:8px; border-radius:50%; background:var(--accent); }
.badge .dot.pulse { animation:pulse-dot 2s ease-in-out infinite; }
@keyframes pulse-dot { 0%,100%{transform:scale(1);opacity:1} 50%{transform:scale(1.4);opacity:0.5} }
.status-card { background:var(--card); border:1px solid var(--border); border-radius:var(--radius); padding:1.5rem 2rem; margin-bottom:2rem; display:flex; align-items:center; gap:1.5rem; box-shadow:0 4px 6px rgba(0,0,0,0.04); }
.status-indicator { width:56px; height:56px; border-radius:50%; flex-shrink:0; display:flex; align-items:center; justify-content:center; font-size:1.8rem; }
.status-indicator.online { background:rgba(34,197,94,0.12); box-shadow:0 0 0 8px rgba(34,197,94,0.06); }
.status-indicator.offline { background:rgba(100,116,139,0.12); box-shadow:0 0 0 8px rgba(100,116,139,0.06); }
.status-text .label { font-family:'JetBrains Mono',monospace; font-size:0.7rem; text-transform:uppercase; letter-spacing:0.15em; color:var(--muted-fg); }
.status-text .value { font-size:1.35rem; font-weight:600; }
.status-text .value.online-text { color:var(--green); }
.status-text .value.offline-text { color:var(--muted-fg); }
.status-time { text-align:right; font-size:0.85rem; color:var(--muted-fg); }
.stats-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(170px,1fr)); gap:1rem; margin-bottom:2rem; }
.stat-card { background:var(--card); border:1px solid var(--border); border-radius:var(--radius-sm); padding:1.25rem 1.5rem; box-shadow:0 2px 4px rgba(0,0,0,0.03); transition:all 0.3s ease; }
.stat-card:hover { box-shadow:0 4px 12px rgba(0,0,0,0.06); transform:translateY(-1px); }
.stat-card .stat-label { font-family:'JetBrains Mono',monospace; font-size:0.7rem; text-transform:uppercase; letter-spacing:0.15em; color:var(--muted-fg); margin-bottom:0.5rem; }
.stat-card .stat-value { font-family:'Calistoga',Georgia,serif; font-size:2rem; line-height:1; font-weight:normal; }
.stat-card .stat-value.accent { color:var(--accent); }
.stat-card .stat-sub { font-size:0.8rem; color:var(--muted-fg); margin-top:0.25rem; }
.section-header { display:flex; align-items:center; gap:0.75rem; margin-bottom:1.25rem; margin-top:2rem; }
.section-header h2 { font-family:'Calistoga',Georgia,serif; font-size:1.5rem; font-weight:normal; }
.table-wrap { background:var(--card); border:1px solid var(--border); border-radius:var(--radius-sm); overflow-x:auto; box-shadow:0 2px 4px rgba(0,0,0,0.03); margin-bottom:2rem; }
table { width:100%; border-collapse:collapse; font-size:0.9rem; }
thead th { background:var(--muted); padding:0.75rem 1rem; text-align:left; font-family:'JetBrains Mono',monospace; font-size:0.7rem; text-transform:uppercase; letter-spacing:0.15em; color:var(--muted-fg); font-weight:500; border-bottom:1px solid var(--border); }
tbody td { padding:0.7rem 1rem; border-bottom:1px solid var(--border); }
tbody tr:last-child td { border-bottom:none; }
tbody tr:hover { background:rgba(0,82,255,0.02); }
.s-badge { display:inline-flex; align-items:center; gap:0.35rem; padding:0.2rem 0.65rem; border-radius:9999px; font-size:0.75rem; font-weight:500; }
.s-badge.online { background:rgba(34,197,94,0.1); color:var(--green); }
.s-badge.offline { background:rgba(100,116,139,0.1); color:var(--muted-fg); }
.chart-wrap { background:var(--card); border:1px solid var(--border); border-radius:var(--radius-sm); padding:1.5rem; margin-bottom:2rem; box-shadow:0 2px 4px rgba(0,0,0,0.03); }
.chart-title { font-family:'JetBrains Mono',monospace; font-size:0.7rem; text-transform:uppercase; letter-spacing:0.15em; color:var(--muted-fg); margin-bottom:1rem; }
.bar-chart { display:flex; align-items:flex-end; gap:2px; height:120px; }
.bar-col { flex:1; display:flex; flex-direction:column; align-items:center; gap:4px; min-width:0; }
.bar-col .bar { width:100%; border-radius:3px 3px 0 0; min-height:2px; background:linear-gradient(to top,var(--accent),var(--accent2)); transition:all 0.3s ease; }
.bar-col .bar:hover { opacity:0.75; }
.bar-col .bar-label { font-size:0.55rem; color:var(--muted-fg); font-family:'JetBrains Mono',monospace; white-space:nowrap; }
.daily-chart { position:relative; height:320px; }
.daily-chart canvas { width:100%; height:100%; }
footer { text-align:center; padding:2rem 0; color:var(--muted-fg); font-size:0.8rem; }
.refresh-hint { display:flex; align-items:center; gap:0.5rem; justify-content:center; margin-top:0.5rem; }
.refresh-dot { width:6px; height:6px; border-radius:50%; background:#22c55e; animation:pulse-dot 2s ease-in-out infinite; }
.loading { text-align:center; padding:3rem; color:var(--muted-fg); }
@media (max-width:768px) {
  .container { padding:1rem; }
  .header-left h1 { font-size:1.75rem; }
  .stats-grid { grid-template-columns:repeat(2,1fr); }
  .status-card { flex-direction:column; align-items:flex-start; gap:0.75rem; }
  .status-time { text-align:left; }
  .bar-chart { height:80px; }
  .daily-chart { height:250px; }
}
</style>
</head>
<body>
<div class="container">
<header>
  <div class="header-left">
    <div class="badge"><span class="dot pulse"></span>微博超话监控</div>
    <h1>岁己<span class="gradient-text">SUI</span></h1>
    <p>在线状态追踪 · 数据面板</p>
  </div>
  <div style="text-align:right;color:var(--muted-fg);font-size:0.8rem;" id="update-time"></div>
</header>

<div id="status-card" class="status-card"><div class="loading">加载中...</div></div>

<div class="section-header"><div class="badge"><span class="dot"></span>今日统计</div></div>
<div id="stats-grid" class="stats-grid"><div class="loading">加载中...</div></div>

<div class="section-header"><div class="badge"><span class="dot"></span>每日上线次数</div></div>
<div class="chart-wrap">
  <div class="daily-chart"><canvas id="dailyCanvas"></canvas></div>
</div>

<div class="section-header"><div class="badge"><span class="dot"></span>在线时段分布 · 24H</div></div>
<div class="chart-wrap">
  <div class="bar-chart" id="bar-chart"><div class="loading">加载中...</div></div>
</div>

<div class="section-header"><div class="badge"><span class="dot"></span>最近日志</div></div>
<div id="log-table" class="table-wrap"><div class="loading">加载中...</div></div>

<footer>
  <div class="refresh-hint"><span class="refresh-dot"></span><span>自动刷新 · 30秒</span></div>
  <div style="margin-top:0.35rem;font-size:0.7rem;">日界限: 凌晨4:00（匹配岁己作息 ~11:00起 ~03:00睡）</div>
</footer>
</div>

<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<script>
const API = '/api/stats';
async function fetchData() { try { const r=await fetch(API); return await r.json(); } catch(e){ return null; } }
function fmtDur(m) { if(m<60) return m+' 分钟'; const h=Math.floor(m/60); const r=Math.round(m%60); return r>0?h+'h '+r+'m':h+' 小时'; }

function renderStatus(d) {
  const on = d.current_status === 'online';
  document.getElementById('status-card').innerHTML = `
    <div class="status-indicator ${on?'online':'offline'}">${on?'🟢':'🔴'}</div>
    <div class="status-text">
      <div class="label">当前状态</div>
      <div class="value ${on?'online-text':'offline-text'}">${on?'在线':'离线'}</div>
      <div style="font-size:0.85rem;color:var(--muted-fg);margin-top:0.15rem;">${d.current_desc1||''}</div>
    </div>
    <div class="status-time"><div class="label">最后事件</div><div>${d.last_event_time||'暂无'}</div><div style="margin-top:0.25rem;">共 ${d.total_events||0} 条记录</div></div>`;
  document.getElementById('update-time').textContent = '更新于 ' + (d.generated_at||'');
}

function renderStats(d) {
  const t = d.today || {};
  document.getElementById('stats-grid').innerHTML = `
    <div class="stat-card"><div class="stat-label">今日上线</div><div class="stat-value accent">${t.online_count||0}</div><div class="stat-sub">次</div></div>
    <div class="stat-card"><div class="stat-label">今日在线</div><div class="stat-value">${fmtDur(t.minutes||0)}</div><div class="stat-sub">${t.sessions||0} 次会话</div></div>
    <div class="stat-card"><div class="stat-label">累计在线</div><div class="stat-value">${fmtDur(d.total_online_minutes||0)}</div><div class="stat-sub">${d.total_sessions||0} 次会话</div></div>
    <div class="stat-card"><div class="stat-label">活跃天数</div><div class="stat-value">${d.total_active_days||0}</div><div class="stat-sub">日</div></div>`;
}

function renderHourly(d) {
  const h = d.hourly_distribution||[];
  const max = Math.max(1,...h.map(x=>x.count));
  document.getElementById('bar-chart').innerHTML = h.map(x=>{
    const p = Math.max(2,Math.round(x.count/max*100));
    return `<div class="bar-col"><div class="bar" style="height:${p}%" title="${x.count}次"></div><div class="bar-label">${String(x.hour).padStart(2,'0')}</div></div>`;
  }).join('');
}

let dailyChart = null;

function renderDaily(d) {
  let data = d.merged_daily || [];
  if (!data.length) return;
  const canvas = document.getElementById('dailyCanvas');
  const ctx = canvas.getContext('2d');
  const labels = data.map(x => x.date);
  const values = data.map(x => x.count);

  // 颜色根据值动态调整
  const bgColors = values.map(v => v >= 20 ? 'rgba(0,82,255,0.7)' : v >= 10 ? 'rgba(0,82,255,0.4)' : 'rgba(0,82,255,0.15)');
  const borderColors = values.map(v => v >= 20 ? '#0052FF' : '#4D7CFF');

  if (dailyChart) dailyChart.destroy();
  dailyChart = new Chart(ctx, {
    type: 'bar',
    data: { labels, datasets: [{ data: values, backgroundColor: bgColors, borderColor: borderColors, borderWidth: 0.5, borderRadius: 2 }] },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { intersect: false, mode: 'index' },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: '#0F172A',
          titleFont: { family: 'JetBrains Mono', size: 11 },
          bodyFont: { family: 'Inter', size: 13 },
          callbacks: { label: ctx => `${ctx.parsed.y} 次上线` }
        }
      },
      scales: {
        x: {
          ticks: { font: { family: 'JetBrains Mono', size: 8 }, maxTicksLimit: 60, autoSkip: true, color: '#64748B' },
          grid: { display: false }
        },
        y: {
          beginAtZero: true,
          ticks: { font: { family: 'Inter', size: 11 }, color: '#64748B', stepSize: 10 },
          grid: { color: '#E2E8F0' }
        }
      }
    }
  });
}

function renderLogs(d) {
  const logs = d.recent_logs||[];
  const el = document.getElementById('log-table');
  if(!logs.length){ el.innerHTML='<div style="text-align:center;padding:2rem;color:var(--muted-fg)">暂无记录</div>'; return; }
  el.innerHTML = `<table><thead><tr><th>时间</th><th>状态</th><th>详情</th></tr></thead><tbody>${[...logs].reverse().map(l=>`
    <tr><td>${l.time}</td><td><span class="s-badge ${l.status}">${l.status==='online'?'🟢 上线':'🔴 下线'}</span></td><td>${l.desc1||''}</td></tr>
  `).join('')}</tbody></table>`;
}

async function refresh() {
  const d = await fetchData();
  if(!d||d.empty){ document.getElementById('status-card').innerHTML='<div class="loading">暂无数据，请先运行监控脚本</div>'; return; }
  renderStatus(d); renderStats(d); renderHourly(d); renderDaily(d); renderLogs(d);
}
refresh(); setInterval(refresh,30000);
</script>
</body>
</html>"""

# ===== Flask 集成 =====
try:
    from flask import Flask, jsonify
    HAS_FLASK = True
except ImportError:
    HAS_FLASK = False

def start_webui():
    if not HAS_FLASK:
        print("[WebUI] Flask 未安装，跳过 WebUI 启动")
        return
    print(f"[WebUI] 启动 http://{WEBUI_HOST}:{WEBUI_PORT}")
    app = Flask(__name__)
    @app.route('/')
    def index():
        return HTML_TEMPLATE
    @app.route('/api/stats')
    def api_stats():
        return jsonify(compute_stats())
    @app.route('/api/logs')
    def api_logs():
        return jsonify(read_log())
    app.run(host=WEBUI_HOST, port=WEBUI_PORT, debug=False)

# ===== 多线程启动 =====
import threading

def main():
    # 确保历史数据文件存在
    if not os.path.exists(HISTORY_PATH):
        write_json(HISTORY_PATH, [])
    if not os.path.exists(LOG_PATH):
        write_json(LOG_PATH, [])

    if HAS_FLASK:
        t = threading.Thread(target=start_webui, daemon=True)
        t.start()
        time.sleep(1)
    monitor_loop()

if __name__ == '__main__':
    main()

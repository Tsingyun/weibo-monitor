#!/usr/bin/env python3
"""本地 WebUI 面板（可选）— 浏览器打开 http://localhost:8765"""

import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import STATS_PATH, BASE_DIR

try:
    from flask import Flask, jsonify
except ImportError:
    print("需要 Flask: pip install flask")
    sys.exit(1)

# 直接导入监控模块获取统计
from utils import read_json, write_json
from config import EVENT_PATH, STATS_PATH, DAY_BOUNDARY_HOUR, HISTORY_PATH

app = Flask(__name__)

@app.route('/')
def index():
    return r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>岁己SUI · 微博监控</title>
<link href="https://fonts.googleapis.com/css2?family=Calistoga&family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
:root{--bg:#FAFAFA;--fg:#0F172A;--muted:#F1F5F9;--muted-fg:#64748B;--accent:#0052FF;--accent2:#4D7CFF;--border:#E2E8F0;--card:#FFF;--radius:16px;--radius-sm:12px;--green:#16a34a}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Inter',sans-serif;background:var(--bg);color:var(--fg);min-height:100vh;line-height:1.6;-webkit-font-smoothing:antialiased}
.gradient-text{background:linear-gradient(135deg,var(--accent),var(--accent2));-webkit-background-clip:text;background-clip:text;color:transparent}
.container{max-width:1200px;margin:0 auto;padding:2rem 1.5rem}
header{display:flex;justify-content:space-between;align-items:flex-start;padding:2rem 0 1.5rem;flex-wrap:wrap;gap:1rem}
.header-left h1{font-family:'Calistoga',Georgia,serif;font-size:2.2rem;font-weight:normal;letter-spacing:-0.02em;line-height:1.15}
.header-left p{color:var(--muted-fg);font-size:0.9rem}
.badge{display:inline-flex;align-items:center;gap:0.5rem;padding:0.35rem 1rem;border-radius:9999px;font-family:'JetBrains Mono',monospace;font-size:0.7rem;text-transform:uppercase;letter-spacing:0.15em;border:1px solid rgba(0,82,255,0.3);background:rgba(0,82,255,0.04);color:var(--accent)}
.badge .dot{width:8px;height:8px;border-radius:50%;background:var(--accent)}
.badge .dot.pulse{animation:pulse-dot 2s ease-in-out infinite}
@keyframes pulse-dot{0%,100%{transform:scale(1);opacity:1}50%{transform:scale(1.4);opacity:0.5}}
.status-card{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);padding:1.5rem 2rem;margin-bottom:2rem;display:flex;align-items:center;gap:1.5rem;box-shadow:0 4px 6px rgba(0,0,0,0.04)}
.status-indicator{width:56px;height:56px;border-radius:50%;flex-shrink:0;display:flex;align-items:center;justify-content:center;font-size:1.8rem}
.status-indicator.online{background:rgba(34,197,94,0.12);box-shadow:0 0 0 8px rgba(34,197,94,0.06)}
.status-indicator.offline{background:rgba(100,116,139,0.12);box-shadow:0 0 0 8px rgba(100,116,139,0.06)}
.status-text .label{font-family:'JetBrains Mono',monospace;font-size:0.7rem;text-transform:uppercase;letter-spacing:0.15em;color:var(--muted-fg)}
.status-text .value{font-size:1.35rem;font-weight:600}
.status-text .value.online{color:var(--green)}.status-text .value.offline{color:var(--muted-fg)}
.status-time{text-align:right;font-size:0.85rem;color:var(--muted-fg)}
.stats-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:1rem;margin-bottom:2rem}
.stat-card{background:var(--card);border:1px solid var(--border);border-radius:var(--radius-sm);padding:1.25rem 1.5rem;box-shadow:0 2px 4px rgba(0,0,0,0.03);transition:all 0.3s ease}
.stat-card:hover{box-shadow:0 4px 12px rgba(0,0,0,0.06);transform:translateY(-1px)}
.stat-card .sl{font-family:'JetBrains Mono',monospace;font-size:0.7rem;text-transform:uppercase;letter-spacing:0.15em;color:var(--muted-fg);margin-bottom:0.5rem}
.stat-card .sv{font-family:'Calistoga',Georgia,serif;font-size:2rem;line-height:1}.stat-card .sv.accent{color:var(--accent)}.stat-card .ss{font-size:0.8rem;color:var(--muted-fg);margin-top:0.25rem}
.sh{display:flex;align-items:center;gap:0.75rem;margin-bottom:1.25rem;margin-top:2rem}
.sh h2{font-family:'Calistoga',Georgia,serif;font-size:1.5rem;font-weight:normal}
.tw{background:var(--card);border:1px solid var(--border);border-radius:var(--radius-sm);overflow-x:auto;box-shadow:0 2px 4px rgba(0,0,0,0.03);margin-bottom:2rem}
table{width:100%;border-collapse:collapse;font-size:0.9rem}
thead th{background:var(--muted);padding:0.7rem 1rem;text-align:left;font-family:'JetBrains Mono',monospace;font-size:0.7rem;text-transform:uppercase;letter-spacing:0.15em;color:var(--muted-fg);font-weight:500;border-bottom:1px solid var(--border)}
tbody td{padding:0.7rem 1rem;border-bottom:1px solid var(--border)}tbody tr:last-child td{border-bottom:none}tbody tr:hover{background:rgba(0,82,255,0.02)}
.s-badge{display:inline-flex;align-items:center;gap:0.35rem;padding:0.2rem 0.65rem;border-radius:9999px;font-size:0.75rem;font-weight:500}
.s-badge.online{background:rgba(34,197,94,0.1);color:var(--green)}.s-badge.offline{background:rgba(100,116,139,0.1);color:var(--muted-fg)}
.cw{background:var(--card);border:1px solid var(--border);border-radius:var(--radius-sm);padding:1.5rem;margin-bottom:2rem;box-shadow:0 2px 4px rgba(0,0,0,0.03)}
.ct{font-family:'JetBrains Mono',monospace;font-size:0.7rem;text-transform:uppercase;letter-spacing:0.15em;color:var(--muted-fg);margin-bottom:1rem}
.bc{display:flex;align-items:flex-end;gap:2px;height:120px}
.bc .col{flex:1;display:flex;flex-direction:column;align-items:center;gap:4px;min-width:0}
.bc .bar{width:100%;border-radius:3px 3px 0 0;min-height:2px;background:linear-gradient(to top,var(--accent),var(--accent2));transition:all 0.3s ease}
.bc .lbl{font-size:0.55rem;color:var(--muted-fg);font-family:'JetBrains Mono',monospace}
.dc{height:340px}.dc canvas{width:100%;height:100%}
footer{text-align:center;padding:2rem 0;color:var(--muted-fg);font-size:0.8rem}
.refresh-hint{display:flex;align-items:center;gap:0.5rem;justify-content:center;margin-top:0.5rem}
.rd{width:6px;height:6px;border-radius:50%;background:#22c55e;animation:pulse-dot 2s ease-in-out infinite}
.loading{text-align:center;padding:3rem;color:var(--muted-fg)}
@media(max-width:768px){.container{padding:1rem}.header-left h1{font-size:1.75rem}.stats-grid{grid-template-columns:repeat(2,1fr)}.status-card{flex-direction:column;align-items:flex-start}.bc{height:80px}.dc{height:260px}}
</style>
</head>
<body><div class="container">
<header><div><div class="badge"><span class="dot pulse"></span>微博超话监控</div><h1>岁己<span class="gradient-text">SUI</span></h1><p>在线状态追踪</p></div><div style="text-align:right;color:var(--muted-fg);font-size:0.8rem" id="ut"></div></header>
<div id="sc" class="status-card"><div class="loading">加载中...</div></div>
<div class="sh"><div class="badge"><span class="dot"></span>今日统计</div></div>
<div id="sg" class="stats-grid"><div class="loading">加载中...</div></div>
<div class="sh"><div class="badge"><span class="dot"></span>每日上线</div></div>
<div class="cw"><div class="dc"><canvas id="dailyCanvas"></canvas></div></div>
<div class="sh"><div class="badge"><span class="dot"></span>24H分布</div></div>
<div class="cw"><div class="bc" id="bc"><div class="loading">加载中...</div></div></div>
<div class="sh"><div class="badge"><span class="dot"></span>最近日志</div></div>
<div id="lt" class="tw"><div class="loading">加载中...</div></div>
<footer><div class="refresh-hint"><span class="rd"></span><span>自动刷新 · 30秒</span></div><div style="margin-top:0.35rem;font-size:0.7rem">日界限: 凌晨4:00</div></footer>
</div>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<script>
const API='/api/stats'
async function fd(){try{const r=await fetch(API);return await r.json()}catch(e){return null}}
function fm(m){if(m<60)return m+' 分钟';const h=Math.floor(m/60);const r=Math.round(m%60);return r>0?h+'h '+r+'m':h+' 小时'}
function rs(d){const on=d.current_status==='online'
document.getElementById('sc').innerHTML=`<div class="status-indicator ${on?'online':'offline'}">${on?'🟢':'🔴'}</div>
<div class="status-text"><div class="label">当前状态</div><div class="value ${on?'online':'offline'}">${on?'在线':'离线'}</div>
<div style="font-size:0.85rem;color:var(--muted-fg);margin-top:0.15rem">${d.current_desc1||''}</div></div>
<div class="status-time"><div class="label">最后事件</div><div>${d.last_event_time||'暂无'}</div><div style="margin-top:0.25rem">共 ${d.total_events||0} 条记录</div></div>`
document.getElementById('ut').textContent='更新于 '+(d.generated_at||'')}
function rss(d){const t=d.today||{}
document.getElementById('sg').innerHTML=`<div class="stat-card"><div class="sl">今日上线</div><div class="sv accent">${t.online_count||0}</div><div class="ss">次</div></div>
<div class="stat-card"><div class="sl">今日在线</div><div class="sv">${fm(t.minutes||0)}</div><div class="ss">${t.sessions||0} 次会话</div></div>
<div class="stat-card"><div class="sl">累计在线</div><div class="sv">${fm(d.total_online_minutes||0)}</div><div class="ss">${d.total_sessions||0} 次会话</div></div>
<div class="stat-card"><div class="sl">活跃天数</div><div class="sv">${d.total_active_days||0}</div><div class="ss">天</div></div>`}
function rh(d){const h=d.hourly_distribution||[];const mx=Math.max(1,...h.map(x=>x.count))
document.getElementById('bc').innerHTML=h.map(x=>{const p=Math.max(2,Math.round(x.count/mx*100))
return`<div class="col"><div class="bar" style="height:${p}%" title="${x.count}次"></div><div class="lbl">${String(x.hour).padStart(2,'0')}</div></div>`}).join('')}
let dc=null
function rdly(d){const data=d.merged_daily||[];if(!data.length)return
const labs=data.map(x=>x.date);const vals=data.map(x=>x.count)
const bg=vals.map(v=>v>=20?'rgba(0,82,255,0.7)':v>=10?'rgba(0,82,255,0.4)':'rgba(0,82,255,0.15)')
if(dc)dc.destroy()
dc=new Chart(document.getElementById('dailyCanvas'),{type:'bar',
data:{labels:labs,datasets:[{data:vals,backgroundColor:bg,borderRadius:2}]},
options:{responsive:true,maintainAspectRatio:false,interaction:{intersect:false,mode:'index'},
plugins:{legend:{display:false},tooltip:{backgroundColor:'#0F172A',callbacks:{label:ctx=>ctx.parsed.y+' 次上线'}}},
scales:{x:{ticks:{font:{family:'JetBrains Mono',size:8},maxTicksLimit:60,autoSkip:true,color:'#64748B'},grid:{display:false}},
y:{beginAtZero:true,ticks:{font:{family:'Inter',size:10},color:'#64748B',stepSize:8},grid:{color:'#E2E8F0'}}}}})}
function rl(d){const l=d.recent_logs||[];const el=document.getElementById('lt')
if(!l.length){el.innerHTML='<div style="text-align:center;padding:2rem;color:var(--muted-fg)">暂无记录</div>';return}
el.innerHTML=`<table><thead><tr><th>时间</th><th>状态</th><th>详情</th></tr></thead><tbody>${[...l].reverse().map(l=>`<tr><td>${l.time}</td><td><span class="s-badge ${l.status}">${l.status==='online'?'🟢 上线':'🔴 下线'}</span></td><td>${l.desc1||''}</td></tr>`).join('')}</tbody></table>`}
async function rf(){const d=await fd();if(!d||d.empty){document.getElementById('sc').innerHTML='<div class="loading">暂无数据</div>';return}
rs(d);rss(d);rh(d);rdly(d);rl(d)}rf();setInterval(rf,30000)
</script></body></html>"""

@app.route('/api/stats')
def api_stats():
    from monitor import Monitor
    m = Monitor()  # 仅用于计算统计，不启动监控
    stats = m.compute_stats()
    return jsonify(stats)

@app.route('/api/logs')
def api_logs():
    logs = read_json(EVENT_PATH, [])
    return jsonify(logs)

if __name__ == '__main__':
    print("岁己SUI WebUI → http://localhost:8765")
    app.run(host='127.0.0.1', port=8765, debug=False)

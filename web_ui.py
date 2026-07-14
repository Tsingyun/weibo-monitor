#!/usr/bin/env python3
"""本地 WebUI 面板（可选）— 浏览器打开 http://localhost:8765

设计: 深色优先 + 玻璃拟态 + 渐变强调色 + Chart.js 多图表
功能: 实时状态 / KPI / 每日上线 / 在线时长趋势 / 24h 分布 / 在线占比 /
      覆盖率热力图(数据缺失标注) / 最近日志
"""

import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import STATS_PATH, BASE_DIR

try:
    from flask import Flask, jsonify
except ImportError:
    print("需要 Flask: pip install flask")
    sys.exit(1)

from utils import read_json
from config import EVENT_PATH, STATS_PATH, DAY_BOUNDARY_HOUR, HISTORY_PATH

app = Flask(__name__)

PAGE = r"""<!DOCTYPE html>
<html lang="zh-CN" data-theme="dark">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>岁己SUI · 微博监控</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Calistoga&family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;700&display=swap" rel="stylesheet">
<style>
:root{--bg:#0B0F1A;--bg2:#0E1322;--fg:#E8EEF7;--muted:#8A97AD;--muted2:#5C6880;
--card:rgba(255,255,255,0.045);--card-bd:rgba(255,255,255,0.09);--card-hi:rgba(255,255,255,0.075);
--accent:#3B82F6;--accent2:#8B5CF6;--accent3:#22D3EE;
--green:#34D399;--green-d:rgba(52,211,153,0.14);--red:#F87171;--red-d:rgba(248,113,113,0.14);
--amber:#FBBF24;--amber-d:rgba(251,191,36,0.14);--grid:rgba(255,255,255,0.06);
--shadow:0 18px 50px -20px rgba(0,0,0,0.6);--radius:22px;--radius-sm:16px}
[data-theme="light"]{--bg:#F4F6FB;--bg2:#EAEEF6;--fg:#0F172A;--muted:#5B6880;--muted2:#94A3B8;
--card:rgba(255,255,255,0.72);--card-bd:rgba(15,23,42,0.08);--card-hi:rgba(255,255,255,0.95);
--grid:rgba(15,23,42,0.07);--shadow:0 18px 40px -22px rgba(15,23,42,0.25)}
*{margin:0;padding:0;box-sizing:border-box}
html,body{height:100%}
body{font-family:'Inter',system-ui,sans-serif;background:
  radial-gradient(1200px 600px at 12% -8%,rgba(59,130,246,0.16),transparent 60%),
  radial-gradient(1000px 540px at 100% 0%,rgba(139,92,246,0.14),transparent 55%),
  var(--bg);color:var(--fg);min-height:100vh;line-height:1.6;-webkit-font-smoothing:antialiased;
  background-attachment:fixed;transition:background .4s ease,color .4s ease}
.gradient-text{background:linear-gradient(120deg,var(--accent),var(--accent3) 55%,var(--accent2));-webkit-background-clip:text;background-clip:text;color:transparent}
.app{max-width:1180px;margin:0 auto;padding:1.4rem 1.4rem 3rem}
/* 顶栏 */
.topnav{display:flex;align-items:center;justify-content:space-between;gap:1rem;padding:1rem 0 .4rem;flex-wrap:wrap}
.brand{display:flex;align-items:center;gap:.7rem}
.brand .logo{width:42px;height:42px;border-radius:13px;display:grid;place-items:center;font-size:1.3rem;
  background:linear-gradient(135deg,var(--accent),var(--accent2));box-shadow:0 8px 22px -8px var(--accent)}
.brand h1{font-family:'Calistoga',serif;font-size:1.5rem;font-weight:400;letter-spacing:-.01em;line-height:1}
.brand p{font-size:.72rem;color:var(--muted);margin-top:2px;letter-spacing:.04em}
.nav-right{display:flex;align-items:center;gap:.6rem}
.pill{display:inline-flex;align-items:center;gap:.5rem;padding:.4rem .85rem;border-radius:999px;
  font-family:'JetBrains Mono',monospace;font-size:.7rem;letter-spacing:.08em;border:1px solid var(--card-bd);
  background:var(--card);color:var(--muted);backdrop-filter:blur(12px)}
.pill .dot{width:8px;height:8px;border-radius:50%;background:var(--green);box-shadow:0 0 0 4px var(--green-d);animation:pulse 2.2s ease-in-out infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.35}}
.theme-btn{cursor:pointer;width:42px;height:42px;border-radius:13px;border:1px solid var(--card-bd);
  background:var(--card);color:var(--fg);font-size:1.1rem;display:grid;place-items:center;backdrop-filter:blur(12px);transition:.25s}
.theme-btn:hover{background:var(--card-hi);transform:translateY(-1px)}
/* Hero */
.hero{margin:1rem 0 1.3rem;padding:1.6rem 1.9rem;border-radius:var(--radius);border:1px solid var(--card-bd);
  background:linear-gradient(135deg,var(--card-hi),var(--card));backdrop-filter:blur(16px);box-shadow:var(--shadow);
  display:flex;align-items:center;gap:1.6rem;flex-wrap:wrap}
.hero .ring{width:84px;height:84px;border-radius:50%;flex:none;display:grid;place-items:center;font-size:2.4rem;position:relative}
.hero .ring.online{background:radial-gradient(circle at 30% 30%,rgba(52,211,153,.35),rgba(52,211,153,.08));box-shadow:0 0 0 10px var(--green-d)}
.hero .ring.offline{background:radial-gradient(circle at 30% 30%,rgba(138,151,173,.35),rgba(138,151,173,.08));box-shadow:0 0 0 10px rgba(138,151,173,.12)}
.hero .ring::after{content:'';position:absolute;inset:-6px;border-radius:50%;border:2px solid transparent;border-top-color:var(--green);animation:spin 3.5s linear infinite;opacity:.6}
.hero .ring.offline::after{border-top-color:var(--muted2)}
@keyframes spin{to{transform:rotate(360deg)}}
.hero .h-main{flex:1;min-width:200px}
.hero .h-label{font-family:'JetBrains Mono',monospace;font-size:.68rem;letter-spacing:.16em;text-transform:uppercase;color:var(--muted)}
.hero .h-status{font-size:2rem;font-weight:700;margin:.15rem 0}
.hero .h-status.online{color:var(--green)}.hero .h-status.offline{color:var(--muted)}
.hero .h-desc{font-size:.92rem;color:var(--muted)}
.hero .h-meta{text-align:right;font-size:.82rem;color:var(--muted);min-width:150px}
.hero .h-meta b{color:var(--fg);font-family:'JetBrains Mono',monospace;font-weight:500}
/* KPI */
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(165px,1fr));gap:1rem;margin-bottom:1.4rem}
.kpi{padding:1.2rem 1.3rem;border-radius:var(--radius-sm);border:1px solid var(--card-bd);background:var(--card);
  backdrop-filter:blur(14px);box-shadow:var(--shadow);transition:.28s;position:relative;overflow:hidden}
.kpi:hover{transform:translateY(-3px);background:var(--card-hi)}
.kpi::before{content:'';position:absolute;left:0;top:0;bottom:0;width:3px;background:linear-gradient(var(--accent),var(--accent2))}
.kpi .k-l{font-family:'JetBrains Mono',monospace;font-size:.66rem;letter-spacing:.14em;text-transform:uppercase;color:var(--muted)}
.kpi .k-v{font-family:'Calistoga',serif;font-size:1.85rem;line-height:1.1;margin:.35rem 0 .1rem}
.kpi .k-v.accent{background:linear-gradient(120deg,var(--accent),var(--accent3));-webkit-background-clip:text;background-clip:text;color:transparent}
.kpi .k-s{font-size:.74rem;color:var(--muted)}
/* 图表栅格 */
.grid{display:grid;grid-template-columns:repeat(2,1fr);gap:1rem;margin-bottom:1.4rem}
.card{padding:1.3rem 1.4rem 1.4rem;border-radius:var(--radius-sm);border:1px solid var(--card-bd);background:var(--card);
  backdrop-filter:blur(14px);box-shadow:var(--shadow);margin-bottom:1rem}
.card.span2{grid-column:1/-1}
.card .c-head{display:flex;align-items:center;justify-content:space-between;margin-bottom:.9rem;gap:.6rem;flex-wrap:wrap}
.card .c-title{font-family:'Calistoga',serif;font-size:1.12rem;font-weight:400}
.card .c-sub{font-size:.72rem;color:var(--muted);font-family:'JetBrains Mono',monospace}
.chart-box{position:relative;height:230px}
.chart-box.tall{height:300px}
.legend{display:flex;gap:1.1rem;flex-wrap:wrap;margin-top:.7rem;font-size:.72rem;color:var(--muted)}
.legend i{display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:.35rem;vertical-align:middle}
.range-btns{display:flex;gap:.35rem}
.range-btns button{font-family:'JetBrains Mono',monospace;font-size:.64rem;letter-spacing:.04em;padding:.3rem .6rem;border-radius:9px;cursor:pointer;border:1px solid var(--card-bd);background:var(--card);color:var(--muted);transition:.2s}
.range-btns button:hover{color:var(--fg);background:var(--card-hi)}
.range-btns button.active{color:#fff;background:linear-gradient(135deg,var(--accent),var(--accent2));border-color:transparent}
/* 覆盖率热力图 */
.cov-summary{display:flex;align-items:center;gap:1.3rem;flex-wrap:wrap;margin-bottom:1rem}
.cov-big{font-family:'Calistoga',serif;font-size:2.4rem;line-height:1;
  background:linear-gradient(120deg,var(--green),var(--accent3));-webkit-background-clip:text;background-clip:text;color:transparent}
.heatmap{overflow-x:auto;padding-bottom:.4rem}
.heat-row{display:grid;grid-template-columns:64px 1fr;align-items:center;gap:.6rem;margin-bottom:3px}
.heat-row .hd{font-family:'JetBrains Mono',monospace;font-size:.62rem;color:var(--muted);text-align:right;white-space:nowrap}
.heat-cells{display:grid;grid-template-columns:repeat(24,1fr);gap:2px}
.heat-cells .hc{height:15px;border-radius:3px;background:var(--red-d);transition:.2s;cursor:default}
.heat-cells .hc.cov{background:linear-gradient(135deg,var(--accent),var(--accent3))}
.heat-cells .hc.part{background:linear-gradient(135deg,var(--amber),#F59E0B)}
.heat-cells .hc:hover{outline:1.5px solid #fff;outline-offset:1px}
.heat-axis{display:grid;grid-template-columns:64px 1fr;gap:.6rem;margin-top:.4rem}
.heat-axis .ticks{display:grid;grid-template-columns:repeat(12,1fr);font-family:'JetBrains Mono',monospace;font-size:.56rem;color:var(--muted2)}
.missing-list{display:flex;flex-direction:column;gap:.6rem;margin-top:1rem}
.miss-item{display:flex;align-items:center;gap:.7rem;padding:.7rem .9rem;border-radius:12px;background:var(--red-d);
  border:1px solid rgba(248,113,113,.25);font-size:.85rem}
.miss-item .ic{font-size:1.05rem}
.miss-item.warn{background:var(--amber-d);border-color:rgba(251,191,36,.25)}
.miss-item b{font-family:'JetBrains Mono',monospace;color:var(--fg)}
.empty-note{color:var(--muted);font-size:.85rem;padding:.6rem 0}
/* 日志表 */
.tbl-wrap{overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:.85rem}
thead th{text-align:left;padding:.6rem .8rem;font-family:'JetBrains Mono',monospace;font-size:.64rem;letter-spacing:.1em;
  text-transform:uppercase;color:var(--muted);border-bottom:1px solid var(--card-bd)}
tbody td{padding:.6rem .8rem;border-bottom:1px solid var(--grid)}
tbody tr:hover{background:var(--card-hi)}
.s-badge{display:inline-flex;align-items:center;gap:.35rem;padding:.2rem .6rem;border-radius:999px;font-size:.74rem;font-weight:500}
.s-badge.online{background:var(--green-d);color:var(--green)}
.s-badge.offline{background:rgba(138,151,173,.16);color:var(--muted)}
footer{text-align:center;color:var(--muted2);font-size:.74rem;margin-top:1.5rem;line-height:1.8}
.refresh-dot{width:7px;height:7px;border-radius:50%;background:var(--green);display:inline-block;margin-right:.4rem;animation:pulse 2.2s infinite}
.skeleton{color:var(--muted2);text-align:center;padding:2.5rem}
@media(max-width:760px){.grid{grid-template-columns:1fr}.hero{flex-direction:column;align-items:flex-start}.heat-cells .hc{height:11px}.heat-row{grid-template-columns:52px 1fr}.app{padding:.9rem}}
</style>
</head>
<body>
<div class="app">
  <nav class="topnav">
    <div class="brand">
      <div class="logo">🐰</div>
      <div><h1>岁己<span class="gradient-text">SUI</span></h1><p>微博超话在线监控 · WebUI</p></div>
    </div>
    <div class="nav-right">
      <span class="pill"><span class="dot"></span><span id="liveText">实时</span></span>
      <span class="pill" id="ut">--</span>
      <button class="theme-btn" id="themeBtn" title="切换主题">🌙</button>
    </div>
  </nav>

  <section class="hero" id="hero"><div class="skeleton">加载中…</div></section>

  <section class="kpis" id="kpis"><div class="skeleton">加载中…</div></section>

  <div class="grid">
    <div class="card span2">
      <div class="c-head">
        <div class="c-title">每日上线次数 · 上线趋势</div>
        <div class="range-btns" id="rangeBtns">
          <button data-r="30">30天</button>
          <button data-r="60">60天</button>
          <button data-r="90">90天</button>
          <button data-r="0" class="active">全部</button>
        </div>
      </div>
      <div class="chart-box tall"><canvas id="dailyChart"></canvas></div>
      <div class="legend">
        <span><i style="background:linear-gradient(135deg,var(--accent),var(--accent3))"></i>正常数据</span>
        <span><i style="background:var(--amber)"></i>疑似不完整</span>
        <span><i style="background:var(--red)"></i>缺失(未统计)</span>
      </div>
      <div class="c-sub" id="dailySub" style="margin-top:.6rem"></div>
    </div>
    <div class="card">
      <div class="c-head"><div class="c-title">在线时长趋势</div><div class="c-sub">分钟 / 天</div></div>
      <div class="chart-box"><canvas id="trendChart"></canvas></div>
    </div>
    <div class="card">
      <div class="c-head"><div class="c-title">今日在线占比</div><div class="c-sub" id="doughSub"></div></div>
      <div class="chart-box"><canvas id="doughChart"></canvas></div>
    </div>
    <div class="card span2">
      <div class="c-head"><div class="c-title">24 小时上线分布</div><div class="c-sub">按上线起始小时</div></div>
      <div class="chart-box"><canvas id="hourChart"></canvas></div>
    </div>
  </div>

  <div class="card span2">
    <div class="c-head"><div class="c-title">数据覆盖率 · 缺失标注</div>
      <div class="c-sub">每格 = 1 小时 · 蓝=有数据 黄=部分 红=缺失</div></div>
    <div class="cov-summary">
      <div><div class="c-sub">数据完整度</div><div class="cov-big" id="covBig">--%</div></div>
      <div class="legend" style="margin:0">
        <span><i style="background:linear-gradient(135deg,var(--accent),var(--accent3))"></i>完整覆盖</span>
        <span><i style="background:var(--amber)"></i>部分缺失</span>
        <span><i style="background:var(--red)"></i>全天缺失</span>
      </div>
    </div>
    <div class="heatmap" id="heatmap"><div class="skeleton">加载中…</div></div>
    <div class="heat-axis"><div></div><div class="ticks">
      <span>00</span><span>02</span><span>04</span><span>06</span><span>08</span><span>10</span>
      <span>12</span><span>14</span><span>16</span><span>18</span><span>20</span><span>22</span></div></div>
    <div class="missing-list" id="missingList"></div>
  </div>

  <div class="card span2">
    <div class="c-head"><div class="c-title">最近事件</div><div class="c-sub" id="logSub"></div></div>
    <div class="tbl-wrap" id="logs"><div class="skeleton">加载中…</div></div>
  </div>

  <footer>
    <div><span class="refresh-dot"></span>每 30 秒自动刷新 · 数据本地存储</div>
    <div id="footMeta">日界限 凌晨 --:00 · 监控间隔 15s</div>
  </footer>
</div>

<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<script>
const API='/api/stats';
let DATA=null, CHARTS={}, RANGE=0;
const THEME_KEY='sui_webui_theme';

function fmtMin(m){if(m==null)return'0';m=Math.round(m);if(m<60)return m+' 分';const h=Math.floor(m/60),r=m%60;return (h>0?(h+' 时'+(r?' '+r+' 分':'')):r+' 分')}
function themeColors(){const dark=document.documentElement.getAttribute('data-theme')!=='light';
  return{dark,fg:dark?'#E8EEF7':'#0F172A',muted:dark?'#8A97AD':'#5B6880',grid:dark?'rgba(255,255,255,.06)':'rgba(15,23,42,.07)',
  accent:dark?'#3B82F6':'#2563EB',accent2:dark?'#8B5CF6':'#7C3AED',accent3:dark?'#22D3EE':'#0891B2'}}

function grad(ctx,c1,c2){const g=ctx.createLinearGradient(0,0,0,ctx.canvas.height||300);g.addColorStop(0,c1);g.addColorStop(1,c2);return g}

async function fetchData(){try{const r=await fetch(API);return await r.json()}catch(e){return null}}

function renderHero(d){const on=d.current_status==='online';
  document.getElementById('hero').innerHTML=
  `<div class="ring ${on?'online':'offline'}">${on?'🟢':'⚪'}</div>
   <div class="h-main"><div class="h-label">当前状态</div>
     <div class="h-status ${on?'online':'offline'}">${on?'在线':'离线'}</div>
     <div class="h-desc">${d.current_desc1||'—'}</div></div>
   <div class="h-meta"><div class="h-label">最后事件</div><b>${d.last_event_time||'暂无'}</b>
     <div style="margin-top:.5rem">共 <b>${d.total_events||0}</b> 条记录</div></div>`;
  document.getElementById('ut').textContent='更新 '+ (d.generated_at||'').slice(5);
  document.getElementById('footMeta').textContent='日界限 凌晨 '+ (d.day_boundary||5) +':00 · 监控间隔 '+ (d.poll_interval||15) +'s'}

function renderKPIs(d){const t=d.today||{}, cov=(d.coverage&&d.coverage.overall_pct);
  document.getElementById('kpis').innerHTML=
  [['今日上线',(t.online_count||0),'次','accent'],
   ['今日在线',fmtMin(t.minutes||0),(t.sessions||0)+' 次会话',''],
   ['累计会话',(d.total_sessions||0),fmtMin(d.total_online_minutes||0),'accent'],
   ['活跃天数',(d.total_active_days||0),'天',''],
   ['数据完整度',(cov!=null?cov+'%':'—'),'覆盖率','accent'],
   ['最长在线',fmtMin((d.longest_session&&d.longest_session.duration_minutes)||0),'单次','']
  ].map(x=>`<div class="kpi"><div class="k-l">${x[0]}</div>
     <div class="k-v ${x[3]}">${x[1]}</div><div class="k-s">${x[2]}</div></div>`).join('')}

function renderDaily(d){
  const full=d.merged_daily||[];if(!full.length)return;
  const R=(typeof RANGE==='undefined')?0:RANGE;       // 0=全部
  const data=R>0?full.slice(-R):full;
  const susp=new Set((d.coverage&&d.coverage.suspicious_days)||[]);
  const labels=data.map(x=>x.date.slice(5));
  const vals=data.map(x=>x.count==null?0:x.count);
  const bg=labels.map((_,i)=>{
    if(data[i].missing)return 'rgba(248,113,113,.85)';
    if(susp.has(data[i].date))return 'rgba(251,191,36,.85)';
    return null;});
  const c=themeColors();const ctx=document.getElementById('dailyChart');
  if(CHARTS.daily)CHARTS.daily.destroy();
  CHARTS.daily=new Chart(ctx,{type:'bar',
    data:{labels,datasets:[{data:vals,
      backgroundColor:bg.map(b=>b||grad(ctx,c.accent,c.accent3)),
      borderRadius:4,maxBarThickness:26}]},
    options:{responsive:true,maintainAspectRatio:false,
      plugins:{legend:{display:false},
        tooltip:{callbacks:{label:ctx=>{const x=data[ctx.dataIndex];
          const note=x.missing?' · 缺失(未统计到)':(susp.has(x.date)?' · 疑似不完整':'');
          return (x.count==null?0:x.count)+' 次上线'+note;}}}},
      scales:{x:{ticks:{color:c.muted,font:{family:'JetBrains Mono',size:9},maxTicksLimit:30,autoSkip:true},grid:{display:false}},
        y:{beginAtZero:true,ticks:{color:c.muted,font:{size:10},stepSize:8},grid:{color:c.grid}}}}}});
  const gapN=data.filter(x=>x.missing).length;
  document.getElementById('dailySub').textContent=
    `${labels.length} 天显示 · 红=未统计(${gapN}) 黄=疑似不完整 · 点上方按钮切换区间`;
}

function renderTrend(d){const data=d.daily||[];if(!data.length)return;
  const labels=data.map(x=>x.date.slice(5)),vals=data.map(x=>x.minutes||0);
  const c=themeColors();const ctx=document.getElementById('trendChart');
  if(CHARTS.trend)CHARTS.trend.destroy();
  CHARTS.trend=new Chart(ctx,{type:'line',
    data:{labels,datasets:[{data:vals,fill:true,
      backgroundColor:grad(ctx,'rgba(34,211,238,.28)','rgba(34,211,238,0)'),
      borderColor:c.accent3,borderWidth:2,tension:.38,pointRadius:0,pointHoverRadius:4,pointHoverBackgroundColor:c.accent3}]},
    options:{responsive:true,maintainAspectRatio:false,
      plugins:{legend:{display:false},tooltip:{callbacks:{label:c=>fmtMin(c.parsed.y)}}},
      scales:{x:{ticks:{color:c.muted,font:{family:'JetBrains Mono',size:9},maxTicksLimit:14,autoSkip:true},grid:{display:false}},
        y:{beginAtZero:true,ticks:{color:c.muted,font:{size:10},callback:v=>v+'m'},grid:{color:c.grid}}}}}})

function renderDough(d){const t=d.today||{};const on=Math.round(t.minutes||0);const off=Math.max(0,1440-on);
  const c=themeColors();const ctx=document.getElementById('doughChart');
  if(CHARTS.dough)CHARTS.dough.destroy();
  CHARTS.dough=new Chart(ctx,{type:'doughnut',
    data:{labels:['在线','非在线'],datasets:[{data:[on,off],
      backgroundColor:[grad(ctx,c.green||'#34D399','#22D3EE'),'rgba(138,151,173,.22)'],
      borderColor:'transparent',borderWidth:0,hoverOffset:6}]},
    options:{responsive:true,maintainAspectRatio:false,cutout:'68%',
      plugins:{legend:{display:false},tooltip:{callbacks:{label:c=>c.label+': '+fmtMin(c.parsed)}}}}});
  const pct=off>0?Math.round(on/1440*100):0;
  document.getElementById('doughSub').textContent=pct+'% / 今日'}
// 注入 green 变量
Chart.defaults.green='#34D399';

function renderHour(d){const h=d.hourly_distribution||[];if(!h.length)return;
  const labels=h.map(x=>String(x.hour).padStart(2,'0')),vals=h.map(x=>x.count);
  const c=themeColors();const ctx=document.getElementById('hourChart');
  if(CHARTS.hour)CHARTS.hour.destroy();
  CHARTS.hour=new Chart(ctx,{type:'bar',
    data:{labels,datasets:[{data:vals,backgroundColor:grad(ctx,c.accent2,c.accent3),borderRadius:4,maxBarThickness:30}]},
    options:{responsive:true,maintainAspectRatio:false,
      plugins:{legend:{display:false},tooltip:{callbacks:{label:c=>c.parsed.y+' 次'}}},
      scales:{x:{ticks:{color:c.muted,font:{family:'JetBrains Mono',size:9}},grid:{display:false}},
        y:{beginAtZero:true,ticks:{color:c.muted,font:{size:10},stepSize:2},grid:{color:c.grid}}}}}})

function renderHeatmap(d){const cov=d.coverage;const el=document.getElementById('heatmap');
  if(!cov||cov.error){el.innerHTML='<div class="empty-note">覆盖率数据暂不可用（监控运行后生成）</div>';
    document.getElementById('covBig').textContent='—';return}
  document.getElementById('covBig').textContent=cov.overall_pct+'%';
  const days=(cov.days||[]).slice(-40).reverse(); // 最近40天
  el.innerHTML=days.map(day=>{
    let cells='';
    for(let h=0;h<24;h++){
      let cls='hc cov';
      if(day.status==='missing'){cls='hc';}
      else if(day.status==='partial'){
        // 根据 missing_ranges 判断该小时覆盖情况
        const cov_h=!day.missing_ranges.some(r=>{const s=r[0],e=r[1];return h*60>=s&&h*60<e;});
        const part=day.missing_ranges.some(r=>{const s=r[0],e=r[1];return h*60<s&&e>h*60&&e>s&&h*60<e;});
        cls=cov_h?'hc cov':(part?'hc part':'hc');
      }
      cells+=`<div class="${cls}" title="${day.date} ${String(h).padStart(2,'0')}:00"></div>`;
    }
    return `<div class="heat-row"><div class="hd">${day.date.slice(5)}</div><div class="heat-cells">${cells}</div></div>`;
  }).join('')}

function renderMissing(d){const cov=d.coverage;const el=document.getElementById('missingList');
  if(!cov||cov.error){el.innerHTML='';return}
  let html='';
  (cov.missing_spans||[]).forEach(s=>{
    const txt=(s[0]===s[1])?s[0]:(s[0]+' → '+s[1]);
    html+=`<div class="miss-item"><span class="ic">⛔</span><span>全天缺失：<b>${txt}</b></span></div>`});
  (cov.suspicious_days||[]).forEach(s=>{
    html+=`<div class="miss-item warn"><span class="ic">⚠️</span><span>疑似不完整（事件过少）：<b>${s}</b></span></div>`});
  const partial=(cov.days||[]).filter(x=>x.status==='partial');
  partial.forEach(x=>{const rs=(x.missing_ranges||[]).map(r=>`${String(Math.floor(r[0]/60)).padStart(2,'0')}:${String(r[0]%60).padStart(2,'0')}-${String(Math.floor(r[1]/60)).padStart(2,'0')}:${String(r[1]%60).padStart(2,'0')}`);
    if(rs.length)html+=`<div class="miss-item warn"><span class="ic">🕳️</span><span>部分缺失 <b>${x.date}</b>：${rs.join('，')}</span></div>`});
  el.innerHTML=html||'<div class="empty-note">✅ 未发现数据缺失，监控覆盖完整</div>'}

function renderLogs(d){const l=(d.recent_logs||[]).slice().reverse();const el=document.getElementById('logs');
  document.getElementById('logSub').textContent=(d.recent_logs||[]).length+' 条';
  if(!l.length){el.innerHTML='<div class="empty-note">暂无记录</div>';return}
  el.innerHTML=`<table><thead><tr><th>时间</th><th>状态</th><th>详情</th></tr></thead><tbody>
    ${l.map(x=>`<tr><td>${x.time}</td><td><span class="s-badge ${x.status}">${x.status==='online'?'🟢 上线':'🔴 下线'}</span></td><td>${x.desc1||''}</td></tr>`).join('')}
  </tbody></table>`}

function renderAll(d){DATA=d;renderHero(d);renderKPIs(d);renderDaily(d);renderTrend(d);renderDough(d);
  renderHour(d);renderHeatmap(d);renderMissing(d);renderLogs(d)}

function setRange(r,btn){RANGE=r;
  document.querySelectorAll('#rangeBtns button').forEach(b=>b.classList.remove('active'));
  if(btn)btn.classList.add('active');
  if(DATA)renderDaily(DATA);}

function applyTheme(t){document.documentElement.setAttribute('data-theme',t);
  document.getElementById('themeBtn').textContent=t==='light'?'☀️':'🌙';
  localStorage.setItem(THEME_KEY,t)}

async function refresh(){const d=await fetchData();if(!d||d.empty){return}
  if(!DATA)renderAll(d);else renderAll(d)}

document.getElementById('themeBtn').addEventListener('click',()=>{
  const cur=document.documentElement.getAttribute('data-theme');
  const next=cur==='light'?'dark':'light';applyTheme(next);if(DATA)renderAll(DATA)});

(function init(){const saved=localStorage.getItem(THEME_KEY)||'dark';applyTheme(saved);
  document.querySelectorAll('#rangeBtns button').forEach(b=>{
    b.addEventListener('click',()=>setRange(parseInt(b.dataset.r,10),b));});
  refresh();setInterval(refresh,30000)})();
</script>
</body></html>"""


@app.route('/')
def index():
    return PAGE

@app.route('/api/stats')
def api_stats():
    from monitor import Monitor
    m = Monitor()  # 仅用于计算统计，不启动监控
    stats = m.compute_stats()
    stats["day_boundary"] = DAY_BOUNDARY_HOUR
    try:
        stats["coverage"] = m.compute_coverage()
    except Exception as e:
        stats["coverage"] = {"error": str(e)}
    return jsonify(stats)

@app.route('/api/logs')
def api_logs():
    logs = read_json(EVENT_PATH, [])
    return jsonify(logs)

if __name__ == '__main__':
    print("岁己SUI WebUI → http://localhost:8765")
    app.run(host='127.0.0.1', port=8765, debug=False)

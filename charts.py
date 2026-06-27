"""图表生成模块 — matplotlib 非交互模式，适合服务器端"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, timedelta
from io import BytesIO
import os

# 中文字体支持
def _setup_font():
    """尝试设置中文字体，失败则用英文"""
    for font in ["SimHei", "Microsoft YaHei", "WenQuanYi Micro Hei", "Noto Sans CJK SC"]:
        try:
            plt.rcParams["font.sans-serif"] = [font]
            plt.rcParams["axes.unicode_minus"] = False
            return
        except Exception:
            continue
    # 回退：用英文标签
    global _USE_EN
    _USE_EN = True

_USE_EN = False
_setup_font()

ACCENT = "#0052FF"
ACCENT2 = "#4D7CFF"
BG = "#FAFAFA"
FG = "#0F172A"
MFG = "#64748B"
BORDER = "#E2E8F0"

def _style(ax, title=""):
    ax.set_facecolor(BG)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(BORDER)
    ax.spines["bottom"].set_color(BORDER)
    ax.tick_params(colors=MFG, labelsize=8)
    if title:
        ax.set_title(title, fontsize=12, fontweight=600, color=FG, pad=10)

def daily_chart(stats):
    """每日上线次数柱状图"""
    data = stats.get("merged_daily", [])
    if not data:
        return None

    # 取最近 60 天
    recent = data[-60:] if len(data) > 60 else data
    dates = [d["date"] for d in recent]
    counts = [d["count"] if d["count"] is not None else 0 for d in recent]
    # 短标签
    labels = [d[-5:] for d in dates]  # MM-DD

    fig, ax = plt.subplots(figsize=(12, 4))
    colors = [ACCENT if c >= 20 else ACCENT2 if c >= 10 else "#93B4F5" for c in counts]
    ax.bar(range(len(counts)), counts, color=colors, width=0.8, edgecolor="white", linewidth=0.3)
    ax.set_xticks(range(0, len(labels), max(1, len(labels) // 15)))
    ax.set_xticklabels([labels[i] for i in range(0, len(labels), max(1, len(labels) // 15))])
    _style(ax, "每日上线次数")
    ax.set_ylabel("次" if not _USE_EN else "count", color=MFG)
    ax.grid(axis="y", color=BORDER, linewidth=0.5)
    plt.tight_layout()

    buf = BytesIO()
    fig.savefig(buf, format="png", dpi=100, facecolor=BG, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf

def hourly_chart(stats):
    """24H 时段分布图"""
    hourly = stats.get("hourly_distribution", [])
    if not hourly:
        return None
    hours = [h["hour"] for h in hourly]
    counts = [h["count"] for h in hourly]
    max_val = max(counts) if counts else 1

    fig, ax = plt.subplots(figsize=(10, 3.5))
    colors = [ACCENT if c >= max_val * 0.5 else ACCENT2 for c in counts]
    ax.bar(hours, counts, color=colors, width=0.7, edgecolor="white", linewidth=0.3)
    ax.set_xticks(range(0, 24, 2))
    ax.set_xticklabels([f"{h:02d}:00" for h in range(0, 24, 2)])
    _style(ax, "在线时段分布" if not _USE_EN else "Hourly Distribution")
    ax.set_ylabel("次" if not _USE_EN else "count", color=MFG)
    ax.grid(axis="y", color=BORDER, linewidth=0.5)
    plt.tight_layout()

    buf = BytesIO()
    fig.savefig(buf, format="png", dpi=100, facecolor=BG, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf

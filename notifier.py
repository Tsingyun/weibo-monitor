"""通知模块 - 多通道支持: Telegram + Bark

设计:
- 事件通知 (notify / send) 会推送到【所有已启用】的通道 (Telegram + Bark)
- 命令回复走 tg_commands 自有 _send (Telegram 专用), 不经过本模块, 不会推到 Bark
- 每个通道独立启用: 配了对应 key 就发, 没配的不影响其它通道

Bark: iOS 原生推送 (Apple APNs), 比 Telegram Bot 在 iOS 上更可靠/更及时。
      仅需 BARK_KEY; 默认用公共服务器 api.day.app, 也可设 BARK_SERVER 自建。
"""

import time
import json
import urllib.request
import urllib.error
from config import (
    TG_BOT_TOKEN, TG_CHAT_ID, REQUEST_TIMEOUT,
    BARK_KEY, BARK_SERVER, BARK_ICON_URL, BARK_SOUND_URL, BARK_CLICK_URL,
    BARK_PROXY, TELEGRAM_PROXY, BARK_TIMEOUT,
)

TELEGRAM_MAX_LENGTH = 4096

# ===== 代理支持 =====
def _build_opener(proxy):
    """若有代理地址则返回带 ProxyHandler 的 opener, 否则返回默认 opener (均有 .open 方法)"""
    if proxy:
        handler = urllib.request.ProxyHandler({"http": proxy, "https": proxy})
        return urllib.request.build_opener(handler)
    return urllib.request.build_opener()


# ===== 启用检测 =====
def tg_enabled():
    return bool(TG_BOT_TOKEN and TG_CHAT_ID)

def bark_enabled():
    return bool(BARK_KEY)

def enabled():
    """任一通道启用即返回 True (供调用方判断是否发送)"""
    return tg_enabled() or bark_enabled()

# ===== 消息分段 (Telegram 4096 限制) =====
def _chunk_message(text, max_len=TELEGRAM_MAX_LENGTH):
    """将长消息按段落边界切成多段"""
    if len(text.encode('utf-8')) <= max_len:
        return [text]
    chunks = []
    lines = text.split('\n')
    current = ""
    for line in lines:
        test = current + ('\n' if current else '') + line
        if len(test.encode('utf-8')) > max_len:
            if current:
                chunks.append(current)
                current = line
            else:
                while len(line.encode('utf-8')) > max_len:
                    chunks.append(line[:max_len//2])
                    line = line[max_len//2:]
                current = line
        else:
            current = test
    if current:
        chunks.append(current)
    return chunks

# ===== Telegram 通道 =====
def _tg_send_one(message, log_fn=None):
    """发送单条 Telegram 消息 (带重试)"""
    opener = _build_opener(TELEGRAM_PROXY)
    for attempt in range(2):
        try:
            url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
            data = json.dumps({"chat_id": TG_CHAT_ID, "text": message}).encode("utf-8")
            req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
            with opener.open(req, timeout=REQUEST_TIMEOUT) as resp:
                result = json.loads(resp.read())
                if result.get("ok"):
                    return True
                if log_fn:
                    log_fn(f"Telegram API 返回错误: {result}")
        except (urllib.error.URLError, urllib.error.HTTPError,
                json.JSONDecodeError, OSError) as e:
            if log_fn:
                log_fn(f"Telegram 发送失败 (attempt {attempt+1}/2): {e}")
            if attempt < 1:
                time.sleep(1)
                continue
            return False
    return False

# ===== Bark 通道 (iOS 原生推送) =====
def _bark_send_one(message, log_fn=None, title=None, level=None, sound=None, icon=None,
                   subtitle=None, url=None, call=None, volume=None):
    """发送单条消息到 Bark (走 Apple 原生推送, iOS 秒到)

    参数:
      title: 推送标题 (默认 "岁己SUI 微博监控")
      level: active(横幅+声,默认) / passive(仅通知中心不响) / critical(紧急响铃) / timeSensitive
      sound: None=用默认"波比波"铃声(自定义URL); ""=不响铃;
             其它字符串=系统铃声名(如 alarm) 或 自定义铃声URL
      icon: 推送图标 URL (iOS15+, 默认用 BARK_ICON_URL 配置的鸽子图标)
      subtitle: 副标题 (信息分层, 如 "今日第3次上线")
      url: 点击推送跳转地址 (默认 BARK_CLICK_URL 岁己主页); 传 "" 则不跳转
      call: "1" 时通知铃声循环播放 (用于紧急事件确保注意到)
      volume: 紧急警告音量 0-10 (仅 critical 级别生效, 不传默认 5)
    """
    opener = _build_opener(BARK_PROXY)
    for attempt in range(2):
        try:
            api_url = f"{BARK_SERVER}/{BARK_KEY}"
            # sound: None->默认自定义铃声; ""->不响铃; 其它->原样(系统名或URL)
            effective_sound = BARK_SOUND_URL if sound is None else sound
            # url: 显式传 "" 表示不跳转; 否则用传入值或默认点击地址
            effective_url = url if url is not None else BARK_CLICK_URL
            payload = {
                "title": title or "岁己SUI 微博监控",
                "body": message,
                "level": level or "active",
                "group": "\u5c81\u5df1SUI\u5fae\u535a\u76d1\u63a7",   # 分组: 岁己SUI微博监控
                "isArchive": 1,               # 自动保存到历史, 方便回看
                "icon": icon or BARK_ICON_URL, # 推送图标 (鸽子🐦)
            }
            if effective_sound:
                payload["sound"] = effective_sound
            if subtitle:
                payload["subtitle"] = subtitle
            if effective_url:
                payload["url"] = effective_url
            if call:
                payload["call"] = call          # "1" 循环响铃
            if volume is not None:
                payload["volume"] = volume      # 0-10
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(api_url, data=data, headers={"Content-Type": "application/json"})
            with opener.open(req, timeout=BARK_TIMEOUT) as resp:
                result = json.loads(resp.read())
                if result.get("code") == 200:
                    return True
                if log_fn:
                    log_fn(f"Bark 返回错误: {result}")
        except (urllib.error.URLError, urllib.error.HTTPError,
                json.JSONDecodeError, OSError) as e:
            if log_fn:
                log_fn(f"Bark 发送失败 (attempt {attempt+1}/2): {e}")
            if attempt < 1:
                time.sleep(1)
                continue
            return False
    return False

# ===== 聚合发送 =====
def send(message, log_fn=None, bark_title=None, bark_level=None, bark_sound=None, bark_icon=None,
          bark_subtitle=None, bark_url=None, bark_call=None, bark_volume=None, bark_fallback=False):
    """发送消息到所有已启用通道 (Telegram + Bark), 带重试/分段。
    bark_* 参数仅作用于 Bark 通道 (title/level/sound/icon/subtitle/url/call/volume)。
    bark_fallback=True 时, 若 Bark 发送失败, 自动在 Telegram 补发一条 🔴 强调提醒,
    确保关键告警 (cookie过期/连续失败/监控暂停) 即便只看 Bark 也不会漏接。"""
    if not enabled():
        return False
    ok = True
    # Telegram 先发 (保证立即送达, 不等待 Bark 超时)
    if tg_enabled():
        chunks = _chunk_message(message)
        if len(chunks) > 1 and log_fn:
            log_fn(f"消息超长，分成 {len(chunks)} 段发送 (Telegram)")
        for i, chunk in enumerate(chunks):
            text = chunk if len(chunks) == 1 else f"[{i+1}/{len(chunks)}] {chunk}"
            if not _tg_send_one(text, log_fn=log_fn):
                ok = False
    # Bark 通道
    bark_ok = True
    if bark_enabled():
        if not _bark_send_one(message, log_fn=log_fn, title=bark_title, level=bark_level,
                              sound=bark_sound, icon=bark_icon, subtitle=bark_subtitle,
                              url=bark_url, call=bark_call, volume=bark_volume):
            bark_ok = False
            ok = False
    # 兜底: 关键告警 Bark 失败时, Telegram 补发强调提醒
    if bark_fallback and not bark_ok and tg_enabled():
        _tg_send_one("🔴 Bark 推送失败！上方关键通知仅通过 Telegram 送达，请以 Telegram 为准。",
                     log_fn=log_fn)
    return ok

def notify(message, log_fn=None, bark_title=None, bark_level=None, bark_sound=None, bark_icon=None,
           bark_subtitle=None, bark_url=None, bark_call=None, bark_volume=None, bark_fallback=False):
    """统一通知: 控制台 + 所有已启用通道。bark_* 仅作用于 Bark 通道。"""
    print(message)
    send(message, log_fn=log_fn, bark_title=bark_title, bark_level=bark_level, bark_sound=bark_sound,
         bark_icon=bark_icon, bark_subtitle=bark_subtitle, bark_url=bark_url,
         bark_call=bark_call, bark_volume=bark_volume, bark_fallback=bark_fallback)

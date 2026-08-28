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
import ssl
import socket
import http.client
import urllib.request
import urllib.error
from urllib.parse import urlparse
from config import (
    TG_BOT_TOKEN, TG_CHAT_ID, REQUEST_TIMEOUT,
    BARK_KEY, BARK_SERVER, BARK_ICON_URL, BARK_SOUND_URL, BARK_CLICK_URL,
    BARK_PROXY, TELEGRAM_PROXY, BARK_TIMEOUT,
)

TELEGRAM_MAX_LENGTH = 4096

# ===== Bark 直连修复 (绕开 Clash TUN + fake-ip 劫持) =====
# 根因: 本机 Clash 处于 TUN + fake-ip 模式, 会把 api.day.app 劫持成虚拟IP 198.18.0.x;
# 直连该虚拟IP、或经代理(海外节点)访问国内真实IP 43.155.109.24 都会失败(EOF/reset)。
# 修复: 发送时通过 DoH 解析出真实IP(已验证证书 CN=day.app), 并将 socket 绑定到物理网卡,
# 使流量直接从物理网卡出站、绕过 Clash TUN; 同时保留 api.day.app 作为 SNI/Host 以通过 TLS 校验,
# 并使用 h2 ALPN(服务器要求)。无需管理员权限, 无需改动/重启 Clash。
_BARK_REAL_IP = None
_BARK_LOCAL_IP = None  # 物理网卡 IP, 绑定后可绕过 Clash TUN

def _bark_host():
    return urlparse(BARK_SERVER).hostname or "api.day.app"

def _doh_resolve_a(hostname):
    """通过公共 DoH 解析 A 记录, 绕开 Clash fake-ip 劫持返回真实IP (doh.pub 走直连最稳)"""
    urls = [
        "https://doh.pub/dns-query?name=%s&type=A" % hostname,
        "https://119.29.29.29/dns-query?name=%s&type=A" % hostname,
        "https://dns.google/resolve?name=%s&type=A" % hostname,
    ]
    for u in urls:
        try:
            req = urllib.request.Request(u, headers={"Accept": "application/dns-json"})
            with urllib.request.urlopen(req, timeout=6) as r:
                data = json.loads(r.read().decode("utf-8"))
            for ans in data.get("Answer", []):
                if ans.get("type") == 1 and ans.get("data"):
                    return ans["data"]
        except Exception:
            continue
    return None

def _get_bark_real_ip():
    global _BARK_REAL_IP
    if _BARK_REAL_IP:
        return _BARK_REAL_IP
    ip = _doh_resolve_a(_bark_host())
    _BARK_REAL_IP = ip or "43.155.109.24"  # 兜底: 已验证证书的稳定真实IP(腾讯云)
    return _BARK_REAL_IP

def _physical_local_ip():
    """返回物理网卡 IPv4 (绑定后可绕过 Clash TUN)。失败返回 None(退化为不绑定)。"""
    global _BARK_LOCAL_IP
    if _BARK_LOCAL_IP is not None:
        return _BARK_LOCAL_IP
    try:
        import subprocess
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-NetIPAddress -AddressFamily IPv4 | "
             "Where-Object {$_.InterfaceAlias -notmatch 'Loopback'} | "
             "ForEach-Object { $_.IPAddress }"],
            capture_output=True, text=True, timeout=10)
        for line in out.stdout.split():
            ip = line.strip()
            if not ip or ip.count('.') != 3:
                continue
            a, b = int(ip.split('.')[0]), int(ip.split('.')[1])
            if a == 127:
                continue                      # loopback
            if a == 169 and b == 254:
                continue                    # APIPA (蓝牙/TAP)
            if a == 198 and b == 18:
                continue                    # Clash fake-ip TUN(198.18.0.0/15)
            if a == 10 or (a == 172 and 16 <= b <= 31) or (a == 192 and b == 168):
                _BARK_LOCAL_IP = ip
                return ip
        _BARK_LOCAL_IP = None
    except Exception:
        _BARK_LOCAL_IP = None
    return _BARK_LOCAL_IP

class _BarkDirectConnection(http.client.HTTPSConnection):
    """绑定物理网卡直连真实IP, 保留 host 作为 SNI, 使用 h2 ALPN。"""
    def __init__(self, host, real_ip, local_ip=None, port=443, **kwargs):
        super().__init__(host, port, **kwargs)
        self._real_ip = real_ip
        self._local_ip = local_ip
    def connect(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if self._local_ip:
            sock.bind((self._local_ip, 0))
        sock.settimeout(self.timeout)
        sock.connect((self._real_ip, self.port))
        ctx = ssl.create_default_context()
        ctx.set_alpn_protocols(["http/1.1"])  # urllib 只支持 HTTP/1.1
        self.sock = ctx.wrap_socket(sock, server_hostname=self.host)

class _BarkDirectHandler(urllib.request.HTTPSHandler):
    """直连处理器: 用真实IP建连(绑定物理网卡), host 仍作 SNI。"""
    def __init__(self, real_ip, local_ip):
        super().__init__()
        self._real_ip = real_ip
        self._local_ip = local_ip
    def https_open(self, req):
        def conn_factory(host=None, port=None, **kwargs):
            h = host or req.host
            p = port or urlparse(req.full_url).port or 443
            return _BarkDirectConnection(h, self._real_ip, self._local_ip, p, **kwargs)
        return self.do_open(conn_factory, req)

# ===== 代理自检 =====
# 场景: 重启电脑后 Clash 常未自动启动, Telegram 每轮发送都会卡满 REQUEST_TIMEOUT,
# 白白拖慢主轮询。自检可让代理不可用时快速失败并跳过, 恢复后自动继续。
_PROXY_CACHE = {}      # proxy -> (ok, ts)
_PROXY_TTL = 60.0      # 探测结果缓存秒数
_PROXY_LOG_TS = 0      # 代理不可用日志节流

def _probe_proxy(proxy, timeout=3):
    """探测代理端口是否可连，结果缓存 60s。无代理(直连)时返回 True。"""
    if not proxy:
        return True
    now = time.time()
    cached = _PROXY_CACHE.get(proxy)
    if cached and (now - cached[1]) < _PROXY_TTL:
        return cached[0]
    ok = False
    try:
        p = urlparse(proxy)
        host = p.hostname
        port = p.port or (8080 if p.scheme in ("http", "https") else 80)
        if host:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(timeout)
            try:
                s.connect((host, port))
                ok = True
            finally:
                try:
                    s.close()
                except Exception:
                    pass
    except Exception:
        ok = False
    _PROXY_CACHE[proxy] = (ok, now)
    return ok

def tg_proxy_available():
    """Telegram 代理是否可用（未配置代理时视为可用）。"""
    return _probe_proxy(TELEGRAM_PROXY)

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
    # A4: 代理不可用时快速跳过，避免每轮卡满 REQUEST_TIMEOUT 拖慢主轮询
    if not tg_proxy_available():
        global _PROXY_LOG_TS
        _now = time.time()
        if log_fn and (_now - _PROXY_LOG_TS) > 300:
            log_fn("Telegram 代理不可用，跳过本次发送（Clash 未启动？）")
            _PROXY_LOG_TS = _now
        return False
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
    if BARK_PROXY:
        opener = _build_opener(BARK_PROXY)
    else:
        # 直连修复: 解析真实IP并绑定物理网卡绕过 Clash TUN
        real_ip = _get_bark_real_ip()
        local_ip = _physical_local_ip()
        opener = urllib.request.build_opener(_BarkDirectHandler(real_ip, local_ip))
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
    # 环境 stdout 非 UTF-8 (如 GBK) 时, 含 emoji 的消息会导致 print 抛 UnicodeEncodeError,
    # 进而中断整条推送。这里兜底, 保证推送本身的发送不被调试输出拖垮。
    try:
        print(message)
    except UnicodeEncodeError:
        print(message.encode("utf-8", "replace").decode("utf-8", "replace"))
    send(message, log_fn=log_fn, bark_title=bark_title, bark_level=bark_level, bark_sound=bark_sound,
         bark_icon=bark_icon, bark_subtitle=bark_subtitle, bark_url=bark_url,
         bark_call=bark_call, bark_volume=bark_volume, bark_fallback=bark_fallback)

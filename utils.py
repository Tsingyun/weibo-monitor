"""工具函数模块"""

import os, json, time
from datetime import datetime, timedelta, timezone

def beijing_now():
    """返回北京时间（UTC+8）"""
    return datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=8)

def beijing_str(dt=None):
    if dt is None:
        dt = beijing_now()
    return dt.strftime("%Y-%m-%d %H:%M:%S")

def logical_date(dt, boundary_hour=4):
    """按岁己作息计算逻辑日期：凌晨 0:00 ~ boundary_hour:00 归属前一天"""
    if dt.hour < boundary_hour:
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

def write_json(path, data, retries=3, retry_delay=0.3):
    """原子写 + 重试：先写临时文件再 os.replace，避免文件被锁时半截写入或
    Permission denied 丢数据（events.json 被杀软/同步软件短暂锁住时不再误报连接错误）"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.{os.getpid()}.tmp"
    last_err = None
    for attempt in range(max(1, retries)):
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, path)  # 原子替换（Windows 上也覆盖目标）
            return
        except (OSError, PermissionError) as e:
            last_err = e
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
            except Exception:
                pass
            if attempt < retries - 1:
                time.sleep(retry_delay)
    if last_err:
        raise last_err

def is_online(desc1):
    """判断在线状态（白名单模式：只认确定'当前在线'文案，其余全部离线）

    微博超话 desc1 在线/离线文案汇总：
      当前在线: "微博在线了"
      离线(各种): "n分钟前在线了"/"昨天HH:MM在线了"/"前天..."/
                 "M-D在线了"/"YYYY-M-D在线了"/"n天前在线了"
    """
    if not desc1:
        return False
    desc1 = desc1.strip()
    # 白名单: 只有这两种文案表示当前真正在线
    if desc1 in ("微博在线了", "微博在线"):
        return True
    return False

def cookie_expire_info(cookie_str):
    """解析 Cookie 中的 ALF（过期 Unix 时间戳）→ (过期时间 datetime, 剩余天数)

    ALF 是微博下发的长效登录过期时间（UTC 时间戳）。
    返回 None 表示 cookie 中没有可解析的 ALF 字段。
    """
    import re
    if not cookie_str:
        return None
    m = re.search(r"ALF=(\d+)", cookie_str)
    if not m:
        return None
    try:
        ts = int(m.group(1))
        # ALF 为 UTC 时间戳，转成北京时间
        expire = datetime.fromtimestamp(ts, timezone.utc).replace(tzinfo=None) + timedelta(hours=8)
        days_left = (expire - beijing_now()).total_seconds() / 86400.0
        return expire, days_left
    except Exception:
        return None

def format_duration(seconds):
    """格式化时长：X天X小时X分钟"""
    if seconds < 60:
        return f"{int(seconds)}秒"
    mins = seconds // 60
    hrs = mins // 60
    days = hrs // 24
    parts = []
    if days > 0:
        parts.append(f"{int(days)}天")
    if hrs % 24 > 0:
        parts.append(f"{int(hrs % 24)}小时")
    if mins % 60 > 0:
        parts.append(f"{int(mins % 60)}分钟")
    return "".join(parts) if parts else "0分钟"


def kill_residual_monitors(self_pid=None, base_dir=None, app_filename="app.py"):
    """扫 tasklist 杀掉所有「命令行包含 app_filename 或 base_dir」的 python 进程。

    用于启动前的清场：之前存在「绕过单实例锁的孤儿 monitor」（换 cookie / 旧重启残留
    时因竞态窗口产生的），它们只写 health.json 的最后那个 PID，不被 watchdog restart() 杀掉，
    雪球越滚越大、每个都各自推 Bark，导致重复推送。

    工作原理：用 psutil 拿每个 python.exe 的完整命令行（无需 wmic/PowerShell，沙箱安全），
    匹配到「运行的是本项目的 app.py」就 taskkill 掉，self_pid 跳过。

    返回: [(pid, cmdline), ...] 被杀的进程列表（含命令行摘要）。
    """
    try:
        import psutil
    except ImportError:
        return []  # 缺 psutil 时静默跳过（不该发生，因为已在依赖里）

    # 规范化：把 base_dir 与 cmdline 都用统一斜杠（/）转小写后比较，
    # 避免启动时用 C:/Users/... 正斜杠而 BASE_DIR 是反斜杠导致的匹配失败（关键 bug: 41532 就是这样漏网的）
    import re
    def _norm(s):
        return re.sub(r"[/\\]+", "/", s.lower())

    def _script_arg(cmdline):
        """取出「作为脚本被执行的 .py 路径」；`-c`/`-m` 形式返回 None。

        不能靠「cmdline 里是否出现 app.py 字样」判断：任何
        `python -c "...'app.py'..."` 的诊断脚本都会命中字面量，
        此时若 cwd 又恰好在项目目录内，就会被当成僵尸 monitor 误杀
        （同类误判已在 watchdog 自查逻辑里真实踩到，2026-09-20）。
        """
        for a in cmdline[1:]:
            low = a.lower()
            if low in ("-c", "-m"):
                return None
            if low.endswith(".py"):
                return a
        return None

    base_dir_norm = _norm(base_dir or os.path.dirname(os.path.abspath(__file__)))
    app_norm = app_filename.lower()

    killed = []

    for p in psutil.process_iter(['pid', 'name']):
        try:
            info = p.info
            if not info.get('name') or info['name'].lower() != 'python.exe':
                continue
            pid = info['pid']
            if self_pid is not None and pid == self_pid:
                continue
            try:
                cmdline = psutil.Process(pid).cmdline()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
            script = _script_arg(cmdline)
            if not script:
                continue
            script_norm = _norm(script)
            # 必须是「本项目的 app.py」这个脚本本体本身（顺带排除 myapp.py 之类的近似名）
            if not (script_norm == app_norm or script_norm.endswith("/" + app_norm)):
                continue
            # 匹配策略（避免误杀用户的其它 python 脚本）：
            #  1) 脚本参数是绝对路径且落在项目目录内
            #  2) 退化：脚本参数是相对路径（`python -X utf8 app.py`）时，用 cwd 判断归属
            #     （这种相对路径启动的僵尸实例曾因只匹配绝对路径而漏网、造成双实例）
            matched = base_dir_norm in script_norm
            if not matched:
                try:
                    cwd_norm = _norm(psutil.Process(pid).cwd() or "")
                except Exception:
                    cwd_norm = ""
                if cwd_norm and (cwd_norm == base_dir_norm
                                 or cwd_norm.startswith(base_dir_norm.rstrip("/") + "/")):
                    matched = True
            if matched:
                import subprocess
                try:
                    subprocess.run(["taskkill", "/PID", str(pid), "/F"],
                                   capture_output=True, timeout=10)
                    killed.append((pid, " ".join(cmdline)[:200]))
                except Exception:
                    pass
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return killed

#!/usr/bin/env python3
"""监控看门狗（A1）— 检测监控进程是否存活，停滞则自动拉起

判定逻辑：
1. 读 data/health.json 的 updated_at，超过阈值（300s）视为停滞；PID 已不存在则立即判 dead
2. PID 存活检测用 psutil.pid_exists（权威、无子进程开销、无 GBK 解码风险）
3. 需要恢复时：扫进程清场残留 monitor → 清理 monitor.lock → 用 `python -X utf8 app.py` 重新拉起

自身互斥（防多个看门狗并发放大成多 monitor 雪球）：
  不再依赖锁文件，改为扫描「cmdline 含 watchdog.py 且归属本项目」的进程。
  锁文件方案踩过两次坑：① 残留锁 + PID 复用被误判成「看门狗仍在运行」，
  导致计划任务静默退出、自愈失效；② 本机环境 os.remove 会被劫持，释放锁不可靠。
  进程扫描不依赖删除操作、也不受 PID 复用影响；最坏情况（两实例同时冷启动）
  由 app.py 的 O_EXCL monitor 单实例锁兜底。

用法:
  python watchdog.py --check    # 只报告状态，不做任何动作（安全）
  python watchdog.py            # 检查一次，有问题才恢复（Windows 计划任务每 5 分钟调用）
  python watchdog.py --loop     # 常驻循环检查（每 60 秒），供开机自启使用
  python watchdog.py --restart  # 无条件清场并重新拉起 monitor（一键启动场景）
"""

import os
import sys
import time
import subprocess
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 无控制台运行时（pythonw / 计划任务托管）sys.stdout 会是 None，此时 print 抛
# AttributeError。看门狗是"最后一道防线"，绝不能因为打日志失败而瘫痪，
# 这里兜底成 devnull —— 真正的可观测性由 log() 落盘的 logs/watchdog.log 保证。
for _stream in ("stdout", "stderr"):
    if getattr(sys, _stream, None) is None:
        try:
            setattr(sys, _stream, open(os.devnull, "w", encoding="utf-8", buffering=1))
        except Exception:
            pass

from config import BASE_DIR, HEALTH_PATH, POLL_INTERVAL
from utils import read_json, beijing_now, beijing_str, kill_residual_monitors

# subprocess 模块未内置该常量，需自行定义（WinBase.h: CREATE_BREAKAWAY_FROM_JOB）
CREATE_BREAKAWAY_FROM_JOB = 0x01000000

LOCK_FILE = os.path.join(BASE_DIR, "data", "monitor.lock")
APP = os.path.join(BASE_DIR, "app.py")
# 历史遗留：旧版用 data/watchdog.lock 做看门狗互斥，现已改为扫进程判定。
# 常量仅用于启动时顺手清理残留锁文件（删不掉也无所谓，新版不读它）。
WATCHDOG_LOCK = os.path.join(BASE_DIR, "data", "watchdog.lock")
# 看门狗自身日志：由 Windows 计划任务（每 5 分钟）拉起的实例没有 stdout 去处，
# 必须在代码里落盘，否则任务跑没跑、判了什么状态全都看不见。
WLOG_FILE = os.path.join(BASE_DIR, "logs", "watchdog.log")
WLOG_MAX = 2 * 1024 * 1024  # 超过 2MB 轮转一次，避免无限增长
# 停滞阈值（仅对「进程存活但心跳停滞」生效；PID 不存在时会立即判 dead）：
# monitor 现有 60s 轻量心跳（HEALTH_REFRESH_SECONDS），正常 age 远小于此值。
# 取 20 倍轮询间隔（300s）＝心跳间隔的 5 倍余量：既不会重演「health 与阈值同频、
# age 冲到 307s 被误判 stale 而周期性重启好进程」，又能让真卡死场景及时恢复。
STALE_SECONDS = max(300, POLL_INTERVAL * 20)
LOOP_INTERVAL = 60


def log(msg):
    """输出到 stdout，同时落盘 logs/watchdog.log（计划任务模式下没有 stdout，靠文件留痕）"""
    line = f"[{beijing_str()}] {msg}"
    try:
        print(line, flush=True)
    except Exception:
        pass  # 无控制台时 stdout 可能不可写，绝不能因打日志而中断守护流程
    try:
        os.makedirs(os.path.dirname(WLOG_FILE), exist_ok=True)
        if os.path.exists(WLOG_FILE) and os.path.getsize(WLOG_FILE) > WLOG_MAX:
            try:
                os.replace(WLOG_FILE, WLOG_FILE + ".old")
            except OSError:
                pass
        with open(WLOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass  # 日志失败不能影响看门狗主流程


def _norm(path):
    """把路径/命令行统一成正斜杠小写，便于跨写法匹配（`/` vs `\\`）"""
    return path.replace("\\", "/").lower()


def _script_arg(parts):
    """从命令行里取出「作为脚本被执行的 .py 路径」。

    必须精确解析，不能只判断「cmdline 里出现 watchdog.py 字样」——
    任何 `python -c "...'watchdog.py'..."` 形式的诊断脚本都会命中字面量，
    曾被误判成「看门狗已在运行」而把所有实例挡在门外（2026-09-20 实测踩到）。
    """
    for a in parts[1:]:
        low = a.lower()
        if low in ("-c", "-m"):
            return None          # 内联代码/模块执行，没有脚本文件，直接放弃判定
        if low.endswith(".py"):
            return a
    return None


def _other_watchdog_running():
    """返回另一个本项目看门狗的 PID；没有则返回 None。

    扫进程而非读锁文件：不依赖删除操作（本机 os.remove 会被劫持），
    也不受「残留锁 + PID 复用」误判影响。
    """
    try:
        import psutil
    except ImportError:
        return None  # 无 psutil 时不阻塞自身（宁可多跑一个实例，也不让自愈瘫痪）
    me = os.getpid()
    base = _norm(BASE_DIR).rstrip("/")
    for p in psutil.process_iter(["pid", "name"]):
        try:
            name = (p.info.get("name") or "").lower()
            if name not in ("python.exe", "pythonw.exe", "python"):
                continue
            pid = p.info["pid"]
            if pid == me:
                continue
            proc = psutil.Process(pid)
            script = _script_arg(proc.cmdline())
            if not script:
                continue
            norm_script = _norm(script)
            # 必须是 watchdog.py 这个脚本本体（排除 my_watchdog.py 之类的近似名）
            if not (norm_script == "watchdog.py" or norm_script.endswith("/watchdog.py")):
                continue
            try:
                cwd = _norm(proc.cwd() or "").rstrip("/")
            except Exception:
                cwd = ""
            # 脚本路径或 cwd 落在本项目目录 → 认定为同一个看门狗
            if base in norm_script or cwd == base:
                return pid
        except Exception:
            continue
    return None


def _cleanup_legacy_lock():
    """顺手删掉旧版残留的 watchdog.lock（失败无所谓，新版不再读它）"""
    try:
        if os.path.exists(WATCHDOG_LOCK):
            os.remove(WATCHDOG_LOCK)
    except Exception:
        pass


def _pid_alive(pid):
    """判断 PID 是否存在。

    优先 psutil（权威、零子进程开销、无 GBK 解码问题）；缺 psutil 时退化为 os.kill(pid,0)。
    历史坑：旧实现用 `tasklist /FI "PID eq N"` + `str(pid) in stdout` 子串匹配，
    既依赖 PATH、又有子串误匹配与编码风险，已弃用。
    """
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    try:
        import psutil
        return psutil.pid_exists(pid)
    except Exception:
        pass
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError, SystemError, ValueError):
        return False


def check():
    """返回 (status, detail)，status ∈ running / stale / dead / unknown"""
    h = read_json(HEALTH_PATH, None)

    lock_pid = None
    try:
        with open(LOCK_FILE) as f:
            lock_pid = int(f.read().strip())
    except Exception:
        pass

    if not h:
        # 无健康快照时退化为看锁文件里的 PID（兼容旧版本进程）
        if lock_pid and _pid_alive(lock_pid):
            return "unknown", f"无 health.json，但锁中 PID {lock_pid} 存活（可能是旧版本进程）"
        return "dead", "无 health.json 且无存活进程"

    try:
        upd = datetime.strptime(h["updated_at"], "%Y-%m-%d %H:%M:%S")
        age = (beijing_now() - upd).total_seconds()
    except Exception:
        return "unknown", "health.json 时间字段解析失败"

    pid = h.get("pid")
    # 进程已不存在 → 立即判 dead，不必等心跳阈值（缩短真死场景的恢复延迟；
    # 否则调高阈值后会出现在"守护一个已死 PID"的盲区，最长要等满阈值才重启）
    if pid and not _pid_alive(pid):
        return "dead", f"health.json 中 PID {pid} 已不在运行（心跳 age {age:.0f}s）"
    if age > STALE_SECONDS:
        return "stale", f"心跳停滞 {age:.0f}s（阈值 {STALE_SECONDS}s），PID {pid} 存活=True"
    return "running", f"心跳正常（{age:.0f}s 前更新），PID {pid}"


def restart():
    """清理残留进程与锁，然后重新拉起监控"""
    # 1. 先扫描所有「命令行含 app.py 且 cwd 在本项目」的孤儿 monitor，全杀
    #    （之前 restart() 只杀 health.json 里的 PID，遇到绕过单实例锁的孤儿就没辙，
    #     会导致多实例雪球越滚越大）
    killed = kill_residual_monitors(base_dir=BASE_DIR)
    if killed:
        log(f"清场：杀掉 {len(killed)} 个残留 monitor 实例（绕过单实例锁的孤儿）:")
        for pid, cmd in killed:
            log(f"   - PID {pid}: {cmd}")

    # 2. 兜底：杀 health.json 和 monitor.lock 里记录的 PID（兼容 cmdline 读不到的情况）
    pids = set()
    h = read_json(HEALTH_PATH, None)
    if h and h.get("pid"):
        pids.add(int(h["pid"]))
    try:
        with open(LOCK_FILE) as f:
            pids.add(int(f.read().strip()))
    except Exception:
        pass

    for pid in pids:
        if _pid_alive(pid):
            log(f"终止残留进程 PID {pid}")
            try:
                subprocess.run(["taskkill", "/PID", str(pid), "/F"],
                               capture_output=True, timeout=15)
            except Exception as e:
                log(f"终止 PID {pid} 失败: {e}")

    try:
        if os.path.exists(LOCK_FILE):
            os.remove(LOCK_FILE)
            log("已清理 monitor.lock")
    except Exception as e:
        log(f"清锁失败: {e}")

    log("重新启动监控进程…")
    base_flags = (getattr(subprocess, "DETACHED_PROCESS", 0) |
                  getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
    # 三个标志各解决一类「被结束」问题：
    #   DETACHED_PROCESS —— 不分配/不继承控制台，免疫 CTRL_CLOSE_EVENT 连坐
    #                       （2026-09-19 两个进程同时静默消失的元凶）
    #   CREATE_NEW_PROCESS_GROUP —— 独立进程组，控制台事件不再波及
    #   CREATE_BREAKAWAY_FROM_JOB —— 脱离 Windows 计划任务的 Job Object。
    #     计划任务用 Job 托管工作进程，Job 一旦被终止（任务被手动停止、命中执行时限、
    #     Task Scheduler 服务重启）会连带杀掉 Job 内所有进程，包括这里拉起的 monitor。
    #     ⚠️ 仅靠 DETACHED_PROCESS 并不能脱离 Job，必须显式 breakaway。
    #     若外层 Job 未开启 JOB_OBJECT_LIMIT_BREAKAWAY_OK，带此标志会创建失败，
    #     故失败后降级重试：「拉得起」优先于「拉得干净」。
    for flags in (base_flags | CREATE_BREAKAWAY_FROM_JOB, base_flags):
        try:
            proc = subprocess.Popen([sys.executable, "-X", "utf8", APP],
                                    cwd=BASE_DIR,
                                    stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL,
                                    creationflags=flags)
            if flags & CREATE_BREAKAWAY_FROM_JOB:
                log(f"监控进程已拉起 PID {proc.pid}（已脱离计划任务 Job）")
            else:
                log(f"监控进程已拉起 PID {proc.pid}（降级：未能脱离 Job）")
            return True
        except OSError as e:
            log(f"拉起失败（flags=0x{flags:x}）: {e}")
    return False


def main():
    args = sys.argv[1:]
    loop = "--loop" in args
    only_check = "--check" in args
    force_restart = "--restart" in args

    # 手动强制重启（供一键启动脚本使用）：优先于自身互斥检查 ——
    # 用户显式要求重启时，不该被「看门狗已在运行」挡回去。
    if force_restart:
        log("收到 --restart：强制清场并重新拉起监控")
        return 0 if restart() else 1

    # 看门狗自身互斥：多个看门狗会并发拉起多个 monitor，必须互斥（扫进程判定，不依赖锁文件）
    other = _other_watchdog_running()
    if other:
        log(f"看门狗已在运行中 (PID {other})，本实例退出")
        return 0
    _cleanup_legacy_lock()

    while True:
        status, detail = check()
        log(f"状态={status} · {detail}")
        if only_check:
            break
        if status in ("stale", "dead"):
            log("检测到监控未运行，尝试自动恢复…")
            restart()
        if not loop:
            break
        time.sleep(LOOP_INTERVAL)
    return 0


if __name__ == "__main__":
    sys.exit(main())

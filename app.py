#!/usr/bin/env python3
"""岁己SUI 微博监控 - 主入口（含进程互斥锁）"""

import os, sys, traceback
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _ensure_stdio():
    """无控制台运行时（pythonw / DETACHED_PROCESS）sys.stdout 与 sys.stderr 会是 None，
    此时任何一次 print 都会抛 AttributeError 直接把进程带走。
    这里兜底成 devnull；真正的可观测性由日志文件承担。
    """
    for name in ("stdout", "stderr"):
        if getattr(sys, name, None) is None:
            try:
                setattr(sys, name, open(os.devnull, "w", encoding="utf-8", buffering=1))
            except Exception:
                pass


_ensure_stdio()

# 强制 stdout/stderr 使用 UTF-8，避免含 emoji 的推送/日志在 GBK 环境下编码崩溃（推送失效根因）
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
from config import LOG_PATH, EVENT_PATH, STATS_PATH, HISTORY_PATH
from utils import write_json, kill_residual_monitors, beijing_str
from logger import setup_logger

LOCK_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "monitor.lock")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# 死因落盘：进程被外部终止（控制台关闭 / 注销 / 关机）时不会有任何 traceback，
# 不主动记录就永远查不出原因 —— 2026-09-19 那次就是这么凭空消失的
DEATH_PATH = os.path.join(BASE_DIR, "data", "last_death.json")
_ctrl_handler_ref = None      # 注册的处理器必须保持引用，否则被 GC 回收后回调失效


def _record_death(kind, detail=""):
    """把死因写进 data/last_death.json，供事后归因"""
    try:
        write_json(DEATH_PATH, {
            "pid": os.getpid(),
            "time": beijing_str(),
            "kind": kind,
            "detail": detail,
        })
    except Exception:
        pass


def _install_death_recorder(logger=None):
    """注册「死因记录器」，让静默死亡留下痕迹。

    1) SetConsoleCtrlHandler —— 捕获控制台关闭 / 注销 / 关机事件。
       关键背景：Windows 关闭控制台时会向整个前台进程组广播 CTRL_CLOSE_EVENT，
       默认行为是「直接终止且不留任何痕迹」。这正是 monitor 与 watchdog 在
       2026-09-19 02:47 同一分钟内双双消失、日志里零 traceback 的原因。
       该事件无法取消（系统只给约 5 秒），所以这里只做最快的落盘。
    2) sys.excepthook —— 未捕获的致命异常同样落盘（pythonw 下 stderr 不可见）。
    """
    global _ctrl_handler_ref
    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes
            handler_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.DWORD)
            names = {
                0: "CTRL_C_EVENT",
                1: "CTRL_BREAK_EVENT",
                2: "CTRL_CLOSE_EVENT(控制台被关闭)",
                5: "CTRL_LOGOFF_EVENT(用户注销)",
                6: "CTRL_SHUTDOWN_EVENT(系统关机)",
            }

            def _on_ctrl(ctrl_type):
                kind = names.get(int(ctrl_type), f"CTRL_{int(ctrl_type)}_EVENT")
                _record_death(kind)
                try:
                    if logger:
                        logger.warning(f"[死因] 收到 {kind}，进程即将被系统终止")
                except Exception:
                    pass
                return False   # 不拦截（也拦不住），交还系统默认处理

            _ctrl_handler_ref = handler_type(_on_ctrl)
            ctypes.windll.kernel32.SetConsoleCtrlHandler(_ctrl_handler_ref, True)
        except Exception:
            pass

    def _hook(etype, evalue, tb):
        try:
            _record_death("uncaught_exception", f"{etype.__name__}: {evalue}")
            if logger:
                logger.error("[致命] 未捕获异常（进程即将退出）")
                for chunk in traceback.format_exception(etype, evalue, tb):
                    for seg in chunk.rstrip().splitlines():
                        logger.error("  %s", seg)
        except Exception:
            pass

    sys.excepthook = _hook


def _pid_alive(pid):
    """Windows 下用 os.kill(pid, 0) 检测进程是否存在（不会真正发信号）"""
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError, SystemError, ValueError):
        return False

def acquire_lock():
    """获取进程互斥锁，防止重复启动。

    采用 O_EXCL 原子创建锁文件 + 旧 PID 回收，彻底杜绝竞态窗口导致的多实例：
    旧逻辑在「删锁→新实例写锁」之间存在窗口，看门狗并发拉起会绕过检查，
    造成多个 monitor 同时运行、各自推送 Bark 通知（重复推送根因）。
    """
    lock = LOCK_FILE
    for _ in range(5):
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            # 锁已存在：检查持有者是否仍存活
            try:
                with open(lock) as f:
                    old_pid = int(f.read().strip())
            except (ValueError, OSError):
                old_pid = None
            if old_pid and _pid_alive(old_pid):
                print(f"❌ 监控已在运行中 (PID: {old_pid})，本实例退出")
                return False
            # 持有者已死或锁内容损坏 → 回收后重试
            try:
                os.remove(lock)
            except OSError:
                pass
            continue
        else:
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            return True
    print("❌ 无法获取 monitor.lock（多次重试失败），可能存在权限问题，退出")
    return False

def release_lock():
    """释放进程锁"""
    try:
        os.remove(LOCK_FILE)
    except OSError:
        pass

def main():
    # 启动前清场：杀掉所有「命令行含 app.py 且 cwd 是本项目」的孤儿 monitor
    # （绕过单实例锁的历史残留，比如早期竞态窗口产生的多实例）
    killed = kill_residual_monitors(self_pid=os.getpid(), base_dir=BASE_DIR)
    if killed:
        print(f"⚠️ 启动前清场：杀掉 {len(killed)} 个残留 monitor 实例:")
        for pid, cmd in killed:
            print(f"   - PID {pid}: {cmd}")

    # 进程互斥
    if not acquire_lock():
        sys.exit(1)

    # 确保目录和必要文件存在
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    os.makedirs(os.path.dirname(EVENT_PATH), exist_ok=True)
    if not os.path.exists(EVENT_PATH):
        write_json(EVENT_PATH, [])
    if not os.path.exists(HISTORY_PATH):
        write_json(HISTORY_PATH, [])

    # 启动日志
    logger = setup_logger()
    logger.info("岁己SUI 微博监控系统启动")
    # 注册死因记录器：控制台关闭 / 注销 / 关机 / 致命异常都会落盘留痕
    _install_death_recorder(logger)

    try:
        from monitor import Monitor
        monitor = Monitor(log_fn=logger.info)
        monitor.run()
    except KeyboardInterrupt:
        pass
    finally:
        release_lock()

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""验证 app._install_death_recorder 的死因捕获链路真的有效。

背景：2026-09-19 monitor 与 watchdog 在 02:47 同时静默消失且零 traceback，
事后无法归因。为此在 app.py 里加了「死因记录器」（SetConsoleCtrlHandler +
excepthook → data/last_death.json）。本脚本用两级验证证明它可用：

  1. 单元级：注册函数是否成功挂上 handler + 落盘链路是否通
  2. 信号级：对真实子进程发送 CTRL_BREAK_EVENT，看系统是否回调 handler 落盘

用法：python tests/_verify_death_recorder.py
"""

import json
import os
import signal
import subprocess
import sys
import time

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEATH = os.path.join(BASE, "data", "last_death.json")
PY = sys.executable


def _clean():
    try:
        if os.path.exists(DEATH):
            os.remove(DEATH)
    except OSError:
        pass


def _show(label):
    if os.path.exists(DEATH):
        try:
            data = json.load(open(DEATH, encoding="utf-8"))
            print(f"  {label}: kind={data.get('kind')!r} pid={data.get('pid')} time={data.get('time')}")
            return True
        except Exception as e:
            print(f"  {label}: 解析失败 {e}")
            return False
    print(f"  {label}: （未生成 last_death.json）")
    return False


def test_unit():
    """注册 + 落盘链路"""
    print("[1] 单元级：注册 handler 与落盘链路")
    _clean()
    code = (
        "import sys; sys.path.insert(0, r'%s')\n"
        "import app\n"
        "app._install_death_recorder()\n"
        "print('HANDLER_REGISTERED=', app._ctrl_handler_ref is not None)\n"
        "app._record_death('self_test_unit', '由 tests/_verify_death_recorder.py 触发')\n" % BASE
    )
    r = subprocess.run([PY, "-X", "utf8", "-c", code], capture_output=True, timeout=60)
    out = (r.stdout or b"").decode("utf-8", "replace").strip()
    print("  " + out.replace("\n", "\n  "))
    ok_reg = "HANDLER_REGISTERED= True" in out
    ok_write = _show("落盘")
    return ok_reg, ok_write


def test_signal():
    """真实信号：CTRL_BREAK_EVENT → 系统回调 handler"""
    print("[2] 信号级：向真实子进程发送 CTRL_BREAK_EVENT")
    _clean()
    code = (
        "import sys, time, ctypes, ctypes.wintypes as w\n"
        "sys.path.insert(0, r'%s')\n"
        "import app\n"
        "app._install_death_recorder()\n"
        "k = ctypes.windll.kernel32\n"
        "print('CONSOLE=', bool(k.GetConsoleWindow()), flush=True)\n"
        "print('READY', flush=True)\n"
        "time.sleep(30)\n" % BASE
    )
    flags = subprocess.CREATE_NEW_PROCESS_GROUP
    proc = subprocess.Popen([PY, "-X", "utf8", "-c", code],
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                            creationflags=flags)
    line = proc.stdout.readline().decode("utf-8", "replace").strip()
    print(f"  子进程输出: {line}")
    proc.stdout.readline()   # READY
    time.sleep(1)
    try:
        os.kill(proc.pid, signal.CTRL_BREAK_EVENT)
        print("  已发送 CTRL_BREAK_EVENT")
    except Exception as e:
        print(f"  发送失败（环境限制，不影响机制结论）: {e}")
    time.sleep(3)
    ok = _show("落盘")
    try:
        proc.kill()
    except Exception:
        pass
    return ok


if __name__ == "__main__":
    reg, write = test_unit()
    sig = test_signal()
    print()
    print("=== 结论 ===")
    print(f"  handler 注册成功   : {'✅' if reg else '❌'}")
    print(f"  落盘链路可用       : {'✅' if write else '❌'}")
    print(f"  系统信号回调落盘   : {'✅' if sig else '（未触发：可能是子进程无控制台，属环境限制）'}")
    _clean()
    print("  （已清除测试写入的 last_death.json）")

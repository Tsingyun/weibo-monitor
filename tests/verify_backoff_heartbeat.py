# -*- coding: utf-8 -*-
"""
验证：退避 / 暂停分支在等待前会刷新心跳。

背景（真实故障）：
  18:50 微博返回 432 风控 -> monitor 按设计进入指数退避（60s -> 300s -> 900s），
  但退避分支用 `continue` 跳过本轮且**不刷心跳**。watchdog 的 stale 阈值是 300s，
  于是把心跳停滞 358s 的「健康进程」判为卡死、杀掉重拉；新进程再次 432、再次退避、
  再次被杀 —— 形成「432 -> 退避 -> 被杀 -> 重启 -> 再 432」的不停重启。

方法：
  用 AST 从 monitor.py 中**提取真实的产品分支代码**，注入 stub self 后执行，
  断言 write_health() 被调用。验证的是真实代码路径，而不是复述逻辑。
  同时做反向对照：不在退避期时不应刷新（证明不是"无条件刷心跳"而侥幸通过）。

定位策略：
  同一 marker 可能命中多个 If（例如日志/计数分支也引用 backoff_until），
  因此要求候选分支同时具备 `time.sleep` 与 `continue` —— 即主循环里的等待分支。
"""
import ast
import sys
from datetime import datetime, timedelta

SRC = 'monitor.py'


class Stub:
    """最小替身：只关心 write_health 是否被调用。"""
    def __init__(self):
        self.calls = []
        self.backoff_until = None
        self.paused = False
        self.backoff_level = 0

    def write_health(self):
        self.calls.append('write_health')

    def log(self, *_a, **_k):
        pass


class FakeTime:
    """替身：吃掉 sleep，避免测试真的等待 15~60 秒。"""
    @staticmethod
    def sleep(_seconds):
        pass


def _has_call(node, attr):
    return any(
        isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == attr
        for n in ast.walk(node)
    )


def extract_branch(tree, marker, label):
    cands = []
    for node in ast.walk(tree):
        if isinstance(node, ast.If) and marker in ast.unparse(node.test):
            cands.append({
                'node': node,
                'sleep': _has_call(node, 'sleep'),
                'continue': any(isinstance(n, ast.Continue) for n in ast.walk(node)),
                'write_health': _has_call(node, 'write_health'),
            })
    print(f'[定位] 含 "{marker}" 的 If 分支 {len(cands)} 个:')
    for i, c in enumerate(cands, 1):
        print(f'    #{i} sleep={c["sleep"]} continue={c["continue"]} write_health={c["write_health"]}'
              f'  <- {ast.unparse(c["node"].test)[:70]}')
    for c in cands:
        if c['sleep'] and c['continue']:
            print(f'    -> 选中主循环等待分支（sleep+continue）')
            return c['node']
    return None


def run_branch(node, stub, **extra):
    body = ast.unparse(node)
    # `continue` 必须处于循环内 —— 包一层单次 for
    wrapped = 'for _ in range(1):\n' + '\n'.join('    ' + line for line in body.splitlines())
    env = {
        'self': stub,
        'time': FakeTime,
        'datetime': datetime,
        'beijing_now': lambda: datetime.now(),
        'POLL_INTERVAL': 1,
        'now': datetime.now(),
    }
    env.update(extra)
    exec(compile(wrapped, '<branch>', 'exec'), env)


def main():
    tree = ast.parse(open(SRC, encoding='utf-8').read())
    ok = True

    print('=== 退避分支（if self.backoff_until）===')
    node = extract_branch(tree, 'self.backoff_until', 'backoff')
    if node is None:
        print('  [FAIL] 未定位到退避分支')
        ok = False
    else:
        s = Stub()
        s.backoff_until = datetime.now() + timedelta(seconds=60)   # 处于退避中
        run_branch(node, s, now=datetime.now())
        hit = 'write_health' in s.calls
        ok &= hit
        print(f'  [{"PASS" if hit else "FAIL"}] 退避中 -> 调用 write_health: calls={s.calls}')

        s2 = Stub()
        s2.backoff_until = datetime.now() - timedelta(seconds=60)  # 退避已结束
        run_branch(node, s2, now=datetime.now())
        clean = s2.calls == []
        ok &= clean
        print(f'  [{"PASS" if clean else "FAIL"}] 反向对照：非退避期不刷新 -> calls={s2.calls}')

    print()
    print('=== 暂停分支（if self.paused）===')
    node2 = extract_branch(tree, 'self.paused', 'paused')
    if node2 is None:
        print('  [FAIL] 未定位到暂停分支')
        ok = False
    else:
        s3 = Stub()
        s3.paused = True
        run_branch(node2, s3, now=datetime.now())
        hit3 = 'write_health' in s3.calls
        ok &= hit3
        print(f'  [{"PASS" if hit3 else "FAIL"}] 暂停中 -> 调用 write_health: calls={s3.calls}')

    print()
    print('结论：', '两个分支都会在等待前刷新心跳 ✅' if ok else '存在未刷新心跳的分支 ❌')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())

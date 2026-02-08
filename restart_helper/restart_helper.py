from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except Exception:
        return False


def _wait_for_parent_exit(parent_pid: int, max_wait_ms: int) -> bool:
    deadline = time.monotonic() + (max(0, int(max_wait_ms)) / 1000.0)
    while time.monotonic() < deadline:
        if not _pid_alive(parent_pid):
            return True
        time.sleep(0.10)
    return not _pid_alive(parent_pid)


def _spawn_target(target: str, target_args: list[str]) -> int:
    flags = 0
    flags |= int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
    flags |= int(getattr(subprocess, "DETACHED_PROCESS", 0))
    proc = subprocess.Popen(
        [target] + list(target_args),
        creationflags=flags,
        close_fds=True,
    )
    return int(proc.pid or 0)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="ajpc_restart_helper")
    ap.add_argument("--parent-pid", type=int, required=True)
    ap.add_argument("--target", required=True)
    ap.add_argument("--arg", action="append", default=[])
    ap.add_argument("--delay-ms", type=int, default=700)
    ap.add_argument("--max-wait-ms", type=int, default=120000)
    ns = ap.parse_args(argv)

    if not _wait_for_parent_exit(int(ns.parent_pid), int(ns.max_wait_ms)):
        return 2

    if int(ns.delay_ms) > 0:
        time.sleep(int(ns.delay_ms) / 1000.0)

    try:
        _spawn_target(str(ns.target), [str(x) for x in (ns.arg or [])])
    except Exception:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

from __future__ import annotations

import os
import time
from typing import Any

from aqt import mw

from . import config

DEBUG_LOG_PATH = os.path.join(os.path.dirname(__file__), "ajpc_debug.log")


def dbg(*a: Any) -> None:
    if not config.DEBUG:
        return

    try:
        ts = time.strftime("%H:%M:%S")
    except Exception:
        ts = ""

    line = " ".join(str(x) for x in a)
    msg = f"[FamilyGate {ts}] {line}"

    try:
        import threading

        if mw is not None and threading.current_thread() is not threading.main_thread():
            mw.taskman.run_on_main(lambda m=msg: print(m, flush=True))
        else:
            print(msg, flush=True)
    except Exception:
        try:
            print(msg, flush=True)
        except Exception:
            pass

    try:
        with open(DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(msg + "\n")
    except Exception:
        pass

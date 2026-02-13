from __future__ import annotations

import inspect
import os
import time
from typing import Any

from aqt import mw

from . import config

DEBUG_LOG_PATH = os.path.join(os.path.dirname(__file__), "ajpc_debug.log")
_LEVEL_SCORE = {
    "trace": 10,
    "debug": 20,
    "info": 30,
    "warn": 40,
    "warning": 40,
    "error": 50,
}


def _source_from_stack() -> str:
    try:
        frame = inspect.currentframe()
        if frame is None:
            return "Core"
        cur = frame.f_back
        this_file = os.path.abspath(__file__)
        while cur is not None:
            fname = os.path.abspath(str(cur.f_code.co_filename or ""))
            if fname != this_file:
                module_name = str(cur.f_globals.get("__name__", "") or "")
                if module_name:
                    leaf = module_name.split(".")[-1].strip("_")
                    if leaf:
                        return leaf
                base = os.path.splitext(os.path.basename(fname))[0].strip("_")
                if base:
                    return base
                break
            cur = cur.f_back
    except Exception:
        pass
    return "Core"


def _normalize_level(level: str | None) -> str:
    v = str(level or "debug").strip().lower()
    if v == "warning":
        v = "warn"
    return v if v in {"trace", "debug", "info", "warn", "error"} else "debug"


def _score(level: str | None) -> int:
    return int(_LEVEL_SCORE.get(_normalize_level(level), 20))


def _should_log(source: str, level: str) -> bool:
    if not config.DEBUG:
        return False
    if not bool(config.DEBUG_MODULE_LOGS.get(source, True)):
        return False
    global_level = _normalize_level(getattr(config, "DEBUG_LEVEL", "debug"))
    module_level = _normalize_level(config.DEBUG_MODULE_LEVELS.get(source, global_level))
    threshold = max(_score(global_level), _score(module_level))
    return _score(level) >= threshold


def _emit(level: str, *a: Any, source: str | None = None) -> None:
    tag = str(source or _source_from_stack()).strip() or "Core"
    lvl = _normalize_level(level)
    if not _should_log(tag, lvl):
        return
    try:
        ts = time.strftime("%H:%M:%S")
    except Exception:
        ts = ""

    line = " ".join(str(x) for x in a)
    msg = f"[{tag} {lvl.upper()} {ts}] {line}"

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


def trace(*a: Any, source: str | None = None) -> None:
    _emit("trace", *a, source=source)


def debug(*a: Any, source: str | None = None) -> None:
    _emit("debug", *a, source=source)


def info(*a: Any, source: str | None = None) -> None:
    _emit("info", *a, source=source)


def warn(*a: Any, source: str | None = None) -> None:
    _emit("warn", *a, source=source)


def error(*a: Any, source: str | None = None) -> None:
    _emit("error", *a, source=source)


def dbg(*a: Any, source: str | None = None) -> None:
    debug(*a, source=source)

from __future__ import annotations

import json
import os
from typing import Any

ADDON_DIR = os.path.dirname(__file__)
CONFIG_PATH = os.path.join(ADDON_DIR, "config.json")

# Module-agnostic core state.
CFG: dict[str, Any] = {}
DEBUG = False
DEBUG_VERIFY_SUSPENSION = False
DEBUG_SHOW_RESTART_BUTTON = False
DEBUG_LEVEL = "debug"
DEBUG_MODULE_LOGS: dict[str, bool] = {}
DEBUG_MODULE_LEVELS: dict[str, str] = {}
RUN_ON_SYNC = True
RUN_ON_UI = True
STICKY_UNLOCK = True
RESTORE_MAIN_WINDOW_GEOMETRY = True
GRAPH_PRELOAD_ON_STARTUP = False
NOTETYPES_INSTALLED = False
WATCH_NIDS: set[int] = set()


def _load_config() -> dict[str, Any]:
    if not os.path.exists(CONFIG_PATH):
        return {}
    with open(CONFIG_PATH, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def cfg_get(path: str, default: Any = None) -> Any:
    cur: Any = CFG
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return default
        cur = cur[part]
    return cur


def _cfg_set(cfg: dict[str, Any], path: str, value: Any) -> None:
    cur: dict[str, Any] = cfg
    parts = path.split(".")
    for part in parts[:-1]:
        nxt = cur.get(part)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[part] = nxt
        cur = nxt
    cur[parts[-1]] = value


def reload_config() -> None:
    global CFG, DEBUG, DEBUG_VERIFY_SUSPENSION, DEBUG_SHOW_RESTART_BUTTON
    global DEBUG_LEVEL, DEBUG_MODULE_LOGS, DEBUG_MODULE_LEVELS
    global RUN_ON_SYNC, RUN_ON_UI
    global RESTORE_MAIN_WINDOW_GEOMETRY, GRAPH_PRELOAD_ON_STARTUP
    global STICKY_UNLOCK, NOTETYPES_INSTALLED
    global WATCH_NIDS

    CFG = _load_config()

    _dbg = CFG.get("debug", {})
    level_allowed = {"trace", "debug", "info", "warn", "error"}
    if isinstance(_dbg, dict):
        DEBUG = bool(_dbg.get("enabled", False))
        DEBUG_VERIFY_SUSPENSION = bool(_dbg.get("verify_suspension", False))
        DEBUG_SHOW_RESTART_BUTTON = bool(_dbg.get("show_restart_button", False))
        _lvl = str(_dbg.get("level", "debug")).strip().lower()
        DEBUG_LEVEL = _lvl if _lvl in level_allowed else "debug"
        _mlogs = _dbg.get("module_logs", {})
        if isinstance(_mlogs, dict):
            DEBUG_MODULE_LOGS = {str(k): bool(v) for k, v in _mlogs.items() if str(k).strip()}
        else:
            DEBUG_MODULE_LOGS = {}
        _mlevels = _dbg.get("module_levels", {})
        if isinstance(_mlevels, dict):
            out_levels: dict[str, str] = {}
            for k, v in _mlevels.items():
                key = str(k).strip()
                lvl = str(v).strip().lower()
                if key and lvl in level_allowed:
                    out_levels[key] = lvl
            DEBUG_MODULE_LEVELS = out_levels
        else:
            DEBUG_MODULE_LEVELS = {}
    else:
        DEBUG = bool(_dbg)
        DEBUG_VERIFY_SUSPENSION = False
        DEBUG_SHOW_RESTART_BUTTON = False
        DEBUG_LEVEL = "debug"
        DEBUG_MODULE_LOGS = {}
        DEBUG_MODULE_LEVELS = {}

    try:
        WATCH_NIDS = set(
            int(x)
            for x in (cfg_get("debug.watch_nids", None) or cfg_get("debug.watch_nids", []) or [])
        )
    except Exception:
        WATCH_NIDS = set()

    RUN_ON_SYNC = bool(cfg_get("run_on_sync", True))
    RUN_ON_UI = bool(cfg_get("run_on_ui", True))
    RESTORE_MAIN_WINDOW_GEOMETRY = bool(cfg_get("window_restore.enabled", True))
    GRAPH_PRELOAD_ON_STARTUP = bool(cfg_get("graph.preload_on_startup", False))
    STICKY_UNLOCK = bool(cfg_get("sticky_unlock", True))
    NOTETYPES_INSTALLED = bool(cfg_get("installer.notetypes_installed", False))

reload_config()


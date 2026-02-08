from __future__ import annotations

import os
import subprocess
import sys
import time

from aqt import gui_hooks, mw
from aqt.qt import (
    QAction,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGridLayout,
    QLabel,
    QPlainTextEdit,
    QProcess,
    QVBoxLayout,
    QWidget,
)
from aqt.utils import showInfo

from .. import config, logging
from ..ui import menu
from ..ui.settings_common import _parse_watch_nids
from . import ModuleSpec

_RESTART_DELAY_SECONDS = 2
_LOG_LEVELS: list[tuple[str, str]] = [
    ("Trace", "trace"),
    ("Debug", "debug"),
    ("Info", "info"),
    ("Warn", "warn"),
    ("Error", "error"),
]
_LOG_SOURCES: list[tuple[str, str]] = [
    ("__init__", "Core Init"),
    ("settings", "Settings UI"),
    ("menu", "Menu UI"),
    ("info", "Info Module"),
    ("debug", "Debug Module"),
    ("graph_api", "Graph API"),
    ("browser_graph", "Browser Graph"),
    ("link_core", "Link Core"),
    ("card_sorter", "Card Sorter"),
    ("card_stages", "Card Stages"),
    ("example_gate", "Example Gate"),
    ("family_gate", "Family Gate"),
    ("kanji_gate", "Kanji Gate"),
    ("mass_linker", "Mass Linker"),
]


def _find_anki_exe(start_path: str) -> str:
    p = str(start_path or "").strip()
    if not p:
        return ""
    p = os.path.abspath(p)
    cur = os.path.dirname(p) if os.path.isfile(p) else p
    for _ in range(7):
        candidate_gui = os.path.join(cur, "ankiw.exe")
        if os.path.exists(candidate_gui):
            return candidate_gui
        candidate = os.path.join(cur, "anki.exe")
        if os.path.exists(candidate):
            return candidate
        candidate_venv_gui = os.path.join(cur, ".venv", "Scripts", "ankiw.exe")
        if os.path.exists(candidate_venv_gui):
            return candidate_venv_gui
        candidate_venv = os.path.join(cur, ".venv", "Scripts", "anki.exe")
        if os.path.exists(candidate_venv):
            return candidate_venv
        nxt = os.path.dirname(cur)
        if not nxt or nxt == cur:
            break
        cur = nxt
    return ""


def _build_target_cmd() -> list[str]:
    if mw is None:
        return []

    app_path = ""
    app = mw.app if hasattr(mw, "app") else None
    if app is not None:
        try:
            app_path = str(app.applicationFilePath() or "").strip()
        except Exception:
            app_path = ""
    sys_exe = str(sys.executable or "").strip()
    argv0 = str(sys.argv[0] if sys.argv else "").strip()

    args = [str(x) for x in list(sys.argv[1:])]

    for base in (app_path, sys_exe, argv0):
        found = _find_anki_exe(base)
        if found:
            logging.dbg("restart target: using anki.exe", found, source="debug")
            return [found]

    for base in (app_path, sys_exe):
        b = str(base or "").strip().lower()
        if b.endswith("\\ankiw.exe") or b.endswith("/ankiw.exe"):
            logging.dbg("restart target: using direct ankiw path", base, source="debug")
            return [str(base)]
        if b.endswith("\\anki.exe") or b.endswith("/anki.exe"):
            try:
                gui_candidate = os.path.join(os.path.dirname(str(base)), "ankiw.exe")
            except Exception:
                gui_candidate = ""
            if gui_candidate and os.path.exists(gui_candidate):
                logging.dbg("restart target: switched direct anki->ankiw", gui_candidate, source="debug")
                return [gui_candidate]
            logging.dbg("restart target: using direct anki path", base, source="debug")
            return [str(base)]

    if app_path:
        low = app_path.lower()
        if (low.endswith("\\pythonw.exe") or low.endswith("/pythonw.exe")) and not args:
            logging.dbg("restart target: fallback pythonw -m aqt", app_path, source="debug")
            return [app_path, "-m", "aqt"]
        logging.dbg("restart target: fallback app path", app_path, source="debug")
        return [app_path] + args
    if sys_exe:
        logging.dbg("restart target: fallback sys.executable", sys_exe, source="debug")
        return [sys_exe] + [str(x) for x in list(sys.argv)]
    return []


def _restart_helper_cmd(target_cmd: list[str], delay_seconds: int) -> list[str]:
    helper_dir = os.path.join(config.ADDON_DIR, "restart_helper")
    helper_exe = os.path.join(helper_dir, "ajpc_restart_helper.exe")
    helper_py = os.path.join(helper_dir, "restart_helper.py")

    cmd: list[str]
    if os.path.exists(helper_exe):
        cmd = [helper_exe]
    elif os.path.exists(helper_py):
        pyw = os.path.join(sys.base_prefix, "pythonw.exe")
        py_exec = pyw if os.path.exists(pyw) else sys.executable
        cmd = [py_exec, helper_py]
    else:
        return []

    cmd.extend(
        [
            "--parent-pid",
            str(os.getpid()),
            "--target",
            str(target_cmd[0]),
            "--delay-ms",
            str(max(0, int(delay_seconds * 1000))),
            "--max-wait-ms",
            str(120000),
        ]
    )
    for arg in target_cmd[1:]:
        cmd.extend(["--arg", str(arg)])
    return cmd


def _restart_helper_cmd_py_fallback(target_cmd: list[str], delay_seconds: int) -> list[str]:
    helper_dir = os.path.join(config.ADDON_DIR, "restart_helper")
    helper_py = os.path.join(helper_dir, "restart_helper.py")
    if not os.path.exists(helper_py):
        return []
    pyw = os.path.join(sys.base_prefix, "pythonw.exe")
    py_exec = pyw if os.path.exists(pyw) else sys.executable
    cmd = [py_exec, helper_py]
    cmd.extend(
        [
            "--parent-pid",
            str(os.getpid()),
            "--target",
            str(target_cmd[0]),
            "--delay-ms",
            str(max(0, int(delay_seconds * 1000))),
            "--max-wait-ms",
            str(120000),
        ]
    )
    for arg in target_cmd[1:]:
        cmd.extend(["--arg", str(arg)])
    return cmd


def _start_restart_helper(target_cmd: list[str], delay_seconds: int) -> bool:
    flags = 0
    flags |= int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
    flags |= int(getattr(subprocess, "DETACHED_PROCESS", 0))

    primary_cmd = _restart_helper_cmd(target_cmd, delay_seconds)
    fallback_cmd = _restart_helper_cmd_py_fallback(target_cmd, delay_seconds)
    if not primary_cmd and not fallback_cmd:
        logging.warn("restart helper: missing helper files", source="debug")
        return False

    def _spawn_and_probe(cmd: list[str], label: str) -> bool:
        try:
            proc = subprocess.Popen(
                cmd,
                creationflags=flags,
                close_fds=True,
            )
            # Detect immediate startup crashes (e.g. broken onefile runtime).
            time.sleep(0.35)
            rc = proc.poll()
            if rc is not None:
                logging.warn("restart helper: process exited immediately", label, f"rc={rc}", source="debug")
                return False
            logging.dbg("restart helper: started via subprocess", label, cmd[0], source="debug")
            return True
        except Exception as exc:
            logging.warn("restart helper: subprocess launch failed", label, repr(exc), source="debug")
            return False

    if primary_cmd and _spawn_and_probe(primary_cmd, "primary"):
        return True
    if fallback_cmd and _spawn_and_probe(fallback_cmd, "python-fallback"):
        return True

    # Last attempt via QProcess for environments where detached flags are restricted.
    for cmd, label in ((primary_cmd, "primary"), (fallback_cmd, "python-fallback")):
        if not cmd:
            continue
        try:
            if QProcess.startDetached(cmd[0], cmd[1:]):
                logging.dbg("restart helper: started via QProcess", label, cmd[0], source="debug")
                return True
        except Exception as exc:
            logging.warn("restart helper: QProcess failed", label, repr(exc), source="debug")

    logging.error("restart helper: all start methods failed", source="debug")
    return False


def _delayed_restart_anki() -> None:
    if mw is None:
        return
    try:
        logging.dbg("restart click: begin", source="debug")
        target_cmd = _build_target_cmd()
        if not target_cmd:
            logging.warn("restart click: no target cmd", source="debug")
            showInfo("Failed to restart: executable path not found.")
            return
        logging.dbg("restart click: target", target_cmd[0], "argc=", len(target_cmd), source="debug")

        if not _start_restart_helper(target_cmd, _RESTART_DELAY_SECONDS):
            logging.warn("restart click: helper start failed", source="debug")
            showInfo(
                "Failed to start restart helper.\n"
                "Expected: restart_helper/ajpc_restart_helper.exe"
            )
            return

        ok = False
        try:
            ok = bool(mw.close())
        except Exception:
            ok = True
        logging.dbg("restart click: close requested, ok=", ok, source="debug")
        if not ok:
            return
    except Exception as exc:
        logging.error("restart click: exception", repr(exc), source="debug")
        showInfo("Restart failed:\n" + repr(exc))


def _sync_restart_top_action() -> None:
    if mw is None:
        return
    bar = getattr(getattr(mw, "form", None), "menubar", None)
    if bar is None:
        return
    action = getattr(mw, "_ajpc_restart_top_action", None)
    if action is None:
        action = QAction("\u27f3", mw)
        action.triggered.connect(_delayed_restart_anki)
        mw._ajpc_restart_top_action = action
    show = bool(config.DEBUG_SHOW_RESTART_BUTTON)
    if show:
        try:
            bar.removeAction(action)
        except Exception:
            pass
        bar.addAction(action)
        action.setVisible(True)
        action.setEnabled(True)
    else:
        action.setVisible(False)
        try:
            bar.removeAction(action)
        except Exception:
            pass


def _on_profile_open(*_args, **_kwargs) -> None:
    _sync_restart_top_action()


def _init() -> None:
    menu.register_refresh_callback(_sync_restart_top_action)
    gui_hooks.profile_did_open.append(_on_profile_open)
    _sync_restart_top_action()


def _build_settings(ctx):
    if not config.DEBUG:
        return None

    debug_tab = QWidget()
    debug_layout = QVBoxLayout()
    debug_tab.setLayout(debug_layout)
    debug_form = QFormLayout()
    debug_layout.addLayout(debug_form)

    global_level_combo = QComboBox()
    for label, value in _LOG_LEVELS:
        global_level_combo.addItem(label, value)
    cur_global_level = str(getattr(config, "DEBUG_LEVEL", "debug") or "debug").strip().lower()
    idx = global_level_combo.findData(cur_global_level)
    if idx < 0:
        idx = global_level_combo.findData("debug")
    global_level_combo.setCurrentIndex(max(0, idx))
    debug_form.addRow("Log level", global_level_combo)

    debug_verify_cb = QCheckBox()
    debug_verify_cb.setChecked(config.DEBUG_VERIFY_SUSPENSION)
    debug_form.addRow("Verify suspension", debug_verify_cb)

    restart_btn_cb = QCheckBox()
    restart_btn_cb.setChecked(bool(config.DEBUG_SHOW_RESTART_BUTTON))
    debug_form.addRow("Show top-bar restart button", restart_btn_cb)

    watch_nids_label = QLabel("Watch note IDs (one per line or comma-separated)")
    watch_nids_edit = QPlainTextEdit()
    if config.WATCH_NIDS:
        watch_nids_edit.setPlainText("\n".join(str(x) for x in sorted(config.WATCH_NIDS)))
    watch_nids_edit.setMinimumHeight(120)

    module_log_group = QWidget()
    module_log_grid = QGridLayout()
    module_log_group.setLayout(module_log_grid)
    module_log_grid.setContentsMargins(0, 0, 0, 0)
    module_log_grid.setHorizontalSpacing(10)
    module_log_grid.setVerticalSpacing(4)

    module_log_grid.addWidget(QLabel("Source"), 0, 0)
    module_log_grid.addWidget(QLabel("Enabled"), 0, 1)
    module_log_grid.addWidget(QLabel("Level"), 0, 2)

    source_controls: dict[str, tuple[QCheckBox, QComboBox]] = {}
    module_logs_cfg = dict(getattr(config, "DEBUG_MODULE_LOGS", {}) or {})
    module_levels_cfg = dict(getattr(config, "DEBUG_MODULE_LEVELS", {}) or {})
    for row, (source_key, source_label) in enumerate(_LOG_SOURCES, start=1):
        module_log_grid.addWidget(QLabel(source_label), row, 0)
        enabled_cb = QCheckBox()
        enabled_cb.setChecked(bool(module_logs_cfg.get(source_key, True)))
        module_log_grid.addWidget(enabled_cb, row, 1)
        level_combo = QComboBox()
        for label, value in _LOG_LEVELS:
            level_combo.addItem(label, value)
        source_level = str(module_levels_cfg.get(source_key, cur_global_level) or cur_global_level).strip().lower()
        idx_lvl = level_combo.findData(source_level)
        if idx_lvl < 0:
            idx_lvl = level_combo.findData(cur_global_level if cur_global_level else "debug")
        level_combo.setCurrentIndex(max(0, idx_lvl))
        module_log_grid.addWidget(level_combo, row, 2)
        source_controls[source_key] = (enabled_cb, level_combo)

    debug_layout.addWidget(QLabel("Module logging"))
    debug_layout.addWidget(module_log_group)
    debug_layout.addWidget(watch_nids_label)
    debug_layout.addWidget(watch_nids_edit)

    ctx.add_tab(debug_tab, "Debug")

    def _save(cfg: dict, errors: list[str]) -> None:
        watch_nids, bad_tokens = _parse_watch_nids(watch_nids_edit.toPlainText())
        if bad_tokens:
            errors.append("Watch NIDs invalid: " + ", ".join(bad_tokens))

        selected_level = str(global_level_combo.currentData() or "debug").strip().lower() or "debug"
        module_logs_out: dict[str, bool] = {}
        module_levels_out: dict[str, str] = {}
        for source_key, (enabled_cb, level_combo) in source_controls.items():
            module_logs_out[source_key] = bool(enabled_cb.isChecked())
            module_levels_out[source_key] = str(level_combo.currentData() or selected_level).strip().lower()

        config._cfg_set(cfg, "debug.level", selected_level)
        config._cfg_set(cfg, "debug.verify_suspension", bool(debug_verify_cb.isChecked()))
        config._cfg_set(cfg, "debug.show_restart_button", bool(restart_btn_cb.isChecked()))
        config._cfg_set(cfg, "debug.module_logs", module_logs_out)
        config._cfg_set(cfg, "debug.module_levels", module_levels_out)
        config._cfg_set(cfg, "debug.watch_nids", watch_nids)

    return _save


MODULE = ModuleSpec(
    id="debug",
    label="Debug",
    order=890,
    init=_init,
    settings_items=[
        {
            "label": "Open Debug Log",
            "callback": menu.open_debug_log,
            "visible_fn": lambda: bool(config.DEBUG),
            "order": 10,
        }
    ],
    build_settings=_build_settings,
)

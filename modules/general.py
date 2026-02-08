from __future__ import annotations

import json

from aqt import gui_hooks, mw
from aqt.qt import QByteArray, QCheckBox, QFormLayout, QLabel, Qt, QTimer, QWidget

from .. import config
from . import ModuleSpec


def _graph_api_status_text() -> str:
    if mw is None:
        return "missing (no main window)"
    status = str(getattr(mw, "_ajpc_graph_api_status", "unknown"))
    api = getattr(mw, "_ajpc_graph_api", None)
    if not isinstance(api, dict):
        return f"{status} (not installed)"
    version = str(api.get("version") or "").strip()
    getter_ok = callable(api.get("get_config"))
    if not version:
        return f"{status} (version missing)"
    if not getter_ok:
        return f"{status} (getter missing) v{version}"
    return f"{status} v{version}"


def _encode_qbytearray(value) -> str:
    try:
        return bytes(value.toBase64()).decode("ascii")
    except Exception:
        return ""


def _decode_qbytearray(value: str) -> QByteArray | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return QByteArray.fromBase64(raw.encode("ascii"))
    except Exception:
        return None


def _load_window_restore_cfg() -> dict:
    cfg = config._load_config()
    if not isinstance(cfg, dict):
        return {}
    slot = cfg.get("window_restore")
    return slot if isinstance(slot, dict) else {}


def _write_window_restore_cfg(*, geometry_b64: str, state_b64: str) -> None:
    cfg = config._load_config()
    if not isinstance(cfg, dict):
        cfg = {}
    config._cfg_set(cfg, "window_restore.main_window_geometry", str(geometry_b64 or ""))
    config._cfg_set(cfg, "window_restore.main_window_state", str(state_b64 or ""))
    with open(config.CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


def _restore_main_window_geometry() -> None:
    if mw is None or not config.RESTORE_MAIN_WINDOW_GEOMETRY:
        return
    slot = _load_window_restore_cfg()
    geom = _decode_qbytearray(str(slot.get("main_window_geometry") or ""))
    state = _decode_qbytearray(str(slot.get("main_window_state") or ""))
    try:
        if geom is not None:
            mw.restoreGeometry(geom)
    except Exception:
        pass
    try:
        if state is not None:
            mw.restoreState(state)
    except Exception:
        pass


def _save_main_window_geometry() -> None:
    if mw is None or not config.RESTORE_MAIN_WINDOW_GEOMETRY:
        return
    try:
        geom_b64 = _encode_qbytearray(mw.saveGeometry())
    except Exception:
        geom_b64 = ""
    try:
        state_b64 = _encode_qbytearray(mw.saveState())
    except Exception:
        state_b64 = ""
    if not geom_b64:
        return
    try:
        _write_window_restore_cfg(geometry_b64=geom_b64, state_b64=state_b64)
    except Exception:
        return


def _on_profile_did_open(*_args, **_kwargs) -> None:
    QTimer.singleShot(0, _restore_main_window_geometry)
    QTimer.singleShot(120, _restore_main_window_geometry)


def _on_profile_will_close(*_args, **_kwargs) -> None:
    _save_main_window_geometry()


def _init_window_restore_hooks() -> None:
    if mw is None:
        return
    if getattr(mw, "_ajpc_window_restore_hooks_installed", False):
        return
    gui_hooks.profile_did_open.append(_on_profile_did_open)
    close_hook = getattr(gui_hooks, "profile_will_close", None)
    if close_hook is not None:
        close_hook.append(_on_profile_will_close)
    mw._ajpc_window_restore_hooks_installed = True
    _on_profile_did_open()


def _build_settings(ctx):
    general_tab = QWidget()
    general_form = QFormLayout()
    general_tab.setLayout(general_form)

    debug_enabled_cb = QCheckBox()
    debug_enabled_cb.setChecked(config.DEBUG)
    general_form.addRow("Debug enabled", debug_enabled_cb)

    run_on_sync_cb = QCheckBox()
    run_on_sync_cb.setChecked(config.RUN_ON_SYNC)
    general_form.addRow("Run on sync", run_on_sync_cb)

    run_on_ui_cb = QCheckBox()
    run_on_ui_cb.setChecked(config.RUN_ON_UI)
    general_form.addRow("Run on UI", run_on_ui_cb)

    sticky_unlock_cb = QCheckBox()
    sticky_unlock_cb.setChecked(config.STICKY_UNLOCK)
    general_form.addRow("Sticky unlock", sticky_unlock_cb)

    restore_window_cb = QCheckBox()
    restore_window_cb.setChecked(config.RESTORE_MAIN_WINDOW_GEOMETRY)
    general_form.addRow("Restore main window position", restore_window_cb)

    graph_api_status_label = QLabel(_graph_api_status_text())
    graph_api_status_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    general_form.addRow("Graph API", graph_api_status_label)

    ctx.add_tab(general_tab, "General")

    def _save(cfg: dict, errors: list[str]) -> None:
        config._cfg_set(cfg, "debug.enabled", bool(debug_enabled_cb.isChecked()))
        config._cfg_set(cfg, "run_on_sync", bool(run_on_sync_cb.isChecked()))
        config._cfg_set(cfg, "run_on_ui", bool(run_on_ui_cb.isChecked()))
        config._cfg_set(cfg, "sticky_unlock", bool(sticky_unlock_cb.isChecked()))
        config._cfg_set(cfg, "window_restore.enabled", bool(restore_window_cb.isChecked()))

    return _save


MODULE = ModuleSpec(
    id="general",
    label="General",
    order=10,
    settings_items=[
        {
            "label": "Settings",
            "callback": lambda: _open_settings_dialog(),
            "order": 20,
        }
    ],
    init=_init_window_restore_hooks,
    build_settings=_build_settings,
)


def _open_settings_dialog() -> None:
    from ..ui.settings import open_settings_dialog

    open_settings_dialog()

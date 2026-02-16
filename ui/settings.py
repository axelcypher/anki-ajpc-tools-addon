from __future__ import annotations

import json

from aqt import mw
from aqt.qt import QDialog, QDialogButtonBox, QTabWidget, QVBoxLayout
from aqt.utils import showInfo, show_info

from .. import config, logging
from ..api import settings_api
from ..core import debug as core_debug
from ..core import general as core_general
from ..core import info as core_info
from ..modules import discover_modules
from . import menu
from .settings_common import SettingsContext


def open_settings_dialog() -> None:
    config.reload_config()
    logging.dbg(
        "reloaded config",
        "debug=",
        config.DEBUG,
        "run_on_sync=",
        config.RUN_ON_SYNC,
        "run_on_ui=",
        config.RUN_ON_UI,
        source="settings",
    )

    if mw is None:
        showInfo("No main window.")
        return

    dlg = QDialog(mw)
    dlg.setWindowTitle("AJpC Tools Settings")
    dlg.resize(760, 640)

    tabs = QTabWidget(dlg)
    ctx = SettingsContext(dlg=dlg, tabs=tabs, config=config)
    external_ctx = SettingsContext(dlg=dlg, tabs=tabs, config=config)

    save_fns: list = []
    external_validators: list = []
    external_savers: list = []

    core_builders = [
        ("general", core_general.build_settings),
        ("info", core_info.build_settings),
        ("debug", core_debug.build_settings),
    ]
    for core_id, core_build_fn in core_builders:
        if not callable(core_build_fn):
            continue
        try:
            save_fn = core_build_fn(ctx)
        except Exception as exc:
            logging.error("settings: core build failed", core_id, repr(exc), source="settings")
            continue
        if callable(save_fn):
            save_fns.append(save_fn)

    modules = discover_modules()
    for mod in modules:
        if not callable(mod.build_settings):
            continue
        try:
            save_fn = mod.build_settings(ctx)
        except Exception as exc:
            logging.error("settings: module build failed", mod.id, repr(exc), source="settings")
            continue
        if callable(save_fn):
            save_fns.append(save_fn)

    for provider in settings_api.list_providers():
        build_fn = provider.get("build_settings")
        pid = str(provider.get("id", ""))
        plabel = str(provider.get("label", pid))
        if not callable(build_fn):
            continue
        try:
            hook = build_fn(external_ctx)
        except Exception as exc:
            logging.error("settings: external provider build failed", pid, repr(exc), source="settings")
            continue

        if callable(hook):
            external_savers.append((pid, plabel, hook))
            continue
        if isinstance(hook, dict):
            validate_fn = hook.get("validate")
            save_fn = hook.get("save")
            if callable(validate_fn):
                external_validators.append((pid, plabel, validate_fn))
            if callable(save_fn):
                external_savers.append((pid, plabel, save_fn))

    buttons = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
    )

    def _save() -> None:
        cfg = config._load_config()
        if not isinstance(cfg, dict):
            cfg = {}

        errors: list[str] = []
        for save_fn in save_fns:
            try:
                save_fn(cfg, errors)
            except Exception as exc:
                errors.append(f"Settings save failed: {repr(exc)}")

        for pid, plabel, validate_fn in external_validators:
            try:
                validate_fn(errors)
            except Exception as exc:
                errors.append(f"{plabel}: validation failed: {repr(exc)}")
                logging.warn("settings: external validate failed", pid, repr(exc), source="settings")

        if errors:
            showInfo("Config not saved:\n" + "\n".join(errors))
            return

        try:
            with open(config.CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2, ensure_ascii=False)
        except Exception as exc:
            showInfo("Failed to save config:\n" + repr(exc))
            return

        ext_errors: list[str] = []
        for pid, plabel, save_fn in external_savers:
            try:
                save_fn()
            except Exception as exc:
                ext_errors.append(f"{plabel}: save failed: {repr(exc)}")
                logging.error("settings: external save failed", pid, repr(exc), source="settings")

        config.reload_config()
        menu.refresh_menu_state()
        if ext_errors:
            showInfo("Tools settings saved, but some external settings failed:\n" + "\n".join(ext_errors))
            return

        dlg.accept()
        show_info("Settings saved.")

    buttons.accepted.connect(_save)
    buttons.rejected.connect(dlg.reject)

    layout = QVBoxLayout(dlg)
    layout.setSpacing(2)
    layout.addWidget(tabs, 1)
    layout.addWidget(buttons)
    dlg.setLayout(layout)
    dlg.exec()

from __future__ import annotations

import json

from aqt import mw
from aqt.qt import QDialog, QDialogButtonBox, QTabWidget, QVBoxLayout
from aqt.utils import showInfo, show_info

from .. import config, logging
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
    )

    if mw is None:
        showInfo("No main window.")
        return

    dlg = QDialog(mw)
    dlg.setWindowTitle("AJpC Tools Settings")
    dlg.resize(760, 640)

    tabs = QTabWidget(dlg)
    ctx = SettingsContext(dlg=dlg, tabs=tabs, config=config)

    save_fns: list = []
    modules = discover_modules()
    for mod in modules:
        if callable(mod.build_settings):
            try:
                save_fn = mod.build_settings(ctx)
            except Exception as exc:
                logging.dbg("settings: module build failed", mod.id, repr(exc))
                continue
            if callable(save_fn):
                save_fns.append(save_fn)

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

        if errors:
            showInfo("Config not saved:\n" + "\n".join(errors))
            return

        try:
            with open(config.CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2, ensure_ascii=False)
        except Exception as exc:
            showInfo("Failed to save config:\n" + repr(exc))
            return

        config.reload_config()
        menu.refresh_menu_state()
        dlg.accept()
        show_info("Settings saved.")

    buttons.accepted.connect(_save)
    buttons.rejected.connect(dlg.reject)

    layout = QVBoxLayout(dlg)
    layout.addWidget(tabs)
    layout.addWidget(buttons)
    dlg.setLayout(layout)
    dlg.exec()

from __future__ import annotations

import os

from aqt import mw
from aqt.qt import QAction, QMenu
from aqt.utils import showInfo

from .. import config
from ..logging import DEBUG_LOG_PATH


def open_debug_log() -> None:
    path = DEBUG_LOG_PATH
    if not os.path.exists(path):
        showInfo("Debug log not found:\n" + path)
        return
    try:
        os.startfile(path)  # type: ignore[attr-defined]
    except Exception as exc:
        showInfo("Failed to open debug log:\n" + repr(exc))


def install_menu(
    on_run_family,
    on_run_example,
    on_run_kanji,
    on_run_jlpt,
    on_run_card_sorter,
    on_open_settings,
) -> None:
    if mw is None:
        return
    if getattr(mw, "_familygate_menu_installed", False):
        return

    try:
        for act in list(mw.form.menuTools.actions()):
            if act.text() in ("Run Family Gate", "Run Example Gate", "Run Kanji Gate"):
                mw.form.menuTools.removeAction(act)
    except Exception:
        pass

    menu = QMenu("AJpC", mw)

    action_family = QAction("Run Family Gate", mw)
    action_family.triggered.connect(on_run_family)
    action_family.setEnabled(bool(config.RUN_ON_UI))
    menu.addAction(action_family)

    action_example = QAction("Run Example Gate", mw)
    action_example.triggered.connect(on_run_example)
    action_example.setEnabled(bool(config.RUN_ON_UI))
    menu.addAction(action_example)

    action_kanji = QAction("Run Kanji Gate", mw)
    action_kanji.triggered.connect(on_run_kanji)
    action_kanji.setEnabled(bool(config.RUN_ON_UI))
    menu.addAction(action_kanji)

    action_jlpt = QAction("Run JLPT Tagger", mw)
    action_jlpt.triggered.connect(on_run_jlpt)
    action_jlpt.setEnabled(bool(config.RUN_ON_UI))
    menu.addAction(action_jlpt)

    action_card_sorter = QAction("Run Card Sorter", mw)
    action_card_sorter.triggered.connect(on_run_card_sorter)
    action_card_sorter.setEnabled(bool(config.RUN_ON_UI))
    menu.addAction(action_card_sorter)

    menu.addSeparator()

    action_open_log = QAction("Open Debug Log", mw)
    action_open_log.triggered.connect(open_debug_log)
    action_open_log.setVisible(bool(config.DEBUG))
    menu.addAction(action_open_log)

    action_settings = QAction("Settings", mw)
    action_settings.triggered.connect(on_open_settings)
    menu.addAction(action_settings)

    mw.form.menubar.addMenu(menu)
    mw._familygate_menu_installed = True
    mw._familygate_run_actions = [
        action_family,
        action_example,
        action_kanji,
        action_jlpt,
        action_card_sorter,
    ]
    mw._familygate_open_log_action = action_open_log

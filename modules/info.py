from __future__ import annotations

import os

from aqt import appVersion
from aqt.qt import QHBoxLayout, QLabel, QPushButton, QTextBrowser, QVBoxLayout, QWidget

from .. import config, logging
from ..ui import menu
from ..version import __version__
from . import ModuleSpec


def _build_settings(ctx):
    info_tab = QWidget()
    info_layout = QVBoxLayout()
    info_tab.setLayout(info_layout)

    try:
        anki_version = appVersion() if callable(appVersion) else str(appVersion)
    except Exception:
        anki_version = "unknown"

    info_header = QLabel(
        "AJpC Tools\n"
        "Author: axelcypher\n"
        f"Version: {__version__}\n"
        f"Tested with Anki: {anki_version}\n"
        "Note: This add-on was created with the help of generative AI."
    )
    info_header.setWordWrap(True)

    info_header_row = QHBoxLayout()
    info_header_row.addWidget(info_header)
    info_header_row.addStretch(1)

    info_buttons = QVBoxLayout()

    install_btn = QPushButton("Install Note Types")

    def _on_install_notetypes() -> None:
        menu.import_notetypes()
        _sync_installer_buttons()

    install_btn.clicked.connect(_on_install_notetypes)
    info_buttons.addWidget(install_btn)

    reset_btn = QPushButton("Reset Install Status")

    def _on_reset_install_status() -> None:
        menu.reset_notetypes_installed()
        _sync_installer_buttons()

    reset_btn.clicked.connect(_on_reset_install_status)
    info_buttons.addWidget(reset_btn)

    info_header_row.addLayout(info_buttons)
    info_layout.addLayout(info_header_row)

    info_doc = QTextBrowser()
    doc_text = ""
    try:
        readme_path = os.path.join(config.ADDON_DIR, "README.md")
        with open(readme_path, "r", encoding="utf-8") as f:
            doc_text = f.read()
    except Exception as exc:
        logging.dbg("settings: failed to read README.md", repr(exc))
        doc_text = "# README not found\n\nThe add-on README.md could not be loaded."
    if hasattr(info_doc, "setMarkdown"):
        info_doc.setMarkdown(doc_text)
    else:
        info_doc.setPlainText(doc_text)
    info_doc.setMinimumHeight(260)
    info_layout.addWidget(info_doc)

    ctx.add_tab(info_tab, "Info")

    def _sync_installer_buttons() -> None:
        has_pkg = bool(menu._notetypes_package_path())
        install_btn.setEnabled(has_pkg and not config.NOTETYPES_INSTALLED)
        install_btn.setVisible(not config.NOTETYPES_INSTALLED)

    _sync_installer_buttons()


MODULE = ModuleSpec(
    id="info",
    label="Info",
    order=90,
    build_settings=_build_settings,
)

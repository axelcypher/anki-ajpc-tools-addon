from __future__ import annotations

from aqt.qt import QCheckBox, QFormLayout, QLabel, QPlainTextEdit, QVBoxLayout, QWidget

from .. import config
from ..ui import menu
from ..ui.settings_common import _parse_watch_nids
from . import ModuleSpec


def _build_settings(ctx):
    debug_tab = QWidget()
    debug_layout = QVBoxLayout()
    debug_tab.setLayout(debug_layout)
    debug_form = QFormLayout()
    debug_layout.addLayout(debug_form)

    debug_enabled_cb = QCheckBox()
    debug_enabled_cb.setChecked(config.DEBUG)
    debug_form.addRow("Debug enabled", debug_enabled_cb)

    debug_verify_cb = QCheckBox()
    debug_verify_cb.setChecked(config.DEBUG_VERIFY_SUSPENSION)
    debug_form.addRow("Verify suspension", debug_verify_cb)

    watch_nids_label = QLabel("Watch note IDs (one per line or comma-separated)")
    watch_nids_edit = QPlainTextEdit()
    if config.WATCH_NIDS:
        watch_nids_edit.setPlainText("\n".join(str(x) for x in sorted(config.WATCH_NIDS)))
    watch_nids_edit.setMinimumHeight(120)

    debug_layout.addWidget(watch_nids_label)
    debug_layout.addWidget(watch_nids_edit)

    ctx.add_tab(debug_tab, "Debug")

    def _save(cfg: dict, errors: list[str]) -> None:
        watch_nids, bad_tokens = _parse_watch_nids(watch_nids_edit.toPlainText())
        if bad_tokens:
            errors.append("Watch NIDs invalid: " + ", ".join(bad_tokens))

        config._cfg_set(cfg, "debug.enabled", bool(debug_enabled_cb.isChecked()))
        config._cfg_set(cfg, "debug.verify_suspension", bool(debug_verify_cb.isChecked()))
        config._cfg_set(cfg, "debug.watch_nids", watch_nids)

    return _save


MODULE = ModuleSpec(
    id="debug",
    label="Debug",
    order=80,
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

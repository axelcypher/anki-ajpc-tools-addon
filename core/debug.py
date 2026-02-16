from __future__ import annotations

from aqt.qt import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGridLayout,
    QLabel,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from .. import config
from ..ui import menu
from ..ui.settings_common import _parse_watch_nids

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
    ("family_priority", "Family Priority"),
    ("kanji_gate", "Kanji Gate"),
    ("mass_linker", "Mass Linker"),
]


def init() -> None:
    return


def build_settings(ctx):
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
        config._cfg_set(cfg, "debug.module_logs", module_logs_out)
        config._cfg_set(cfg, "debug.module_levels", module_levels_out)
        config._cfg_set(cfg, "debug.watch_nids", watch_nids)

    return _save


def settings_items() -> list[dict]:
    return [
        {
            "label": "Open Debug Log",
            "callback": menu.open_debug_log,
            "visible_fn": lambda: bool(config.DEBUG),
            "order": 10,
        }
    ]

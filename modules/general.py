from __future__ import annotations

from aqt.qt import QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QWidget

from .. import config
from . import ModuleSpec


def _build_settings(ctx):
    general_tab = QWidget()
    general_form = QFormLayout()
    general_tab.setLayout(general_form)

    run_on_sync_cb = QCheckBox()
    run_on_sync_cb.setChecked(config.RUN_ON_SYNC)
    general_form.addRow("Run on sync", run_on_sync_cb)

    run_on_ui_cb = QCheckBox()
    run_on_ui_cb.setChecked(config.RUN_ON_UI)
    general_form.addRow("Run on UI", run_on_ui_cb)

    sticky_unlock_cb = QCheckBox()
    sticky_unlock_cb.setChecked(config.STICKY_UNLOCK)
    general_form.addRow("Sticky unlock", sticky_unlock_cb)

    stab_default_spin = QDoubleSpinBox()
    stab_default_spin.setDecimals(2)
    stab_default_spin.setRange(0, 100000)
    stab_default_spin.setValue(config.STABILITY_DEFAULT_THRESHOLD)
    general_form.addRow("Default stability threshold", stab_default_spin)

    stab_agg_combo = QComboBox()
    agg_opts = ["min", "max", "avg"]
    stab_agg_combo.addItems(agg_opts)
    agg_index = agg_opts.index(config.STABILITY_AGG) if config.STABILITY_AGG in agg_opts else 0
    stab_agg_combo.setCurrentIndex(agg_index)
    general_form.addRow("Stability aggregation", stab_agg_combo)

    ctx.add_tab(general_tab, "General")

    def _save(cfg: dict, errors: list[str]) -> None:
        config._cfg_set(cfg, "run_on_sync", bool(run_on_sync_cb.isChecked()))
        config._cfg_set(cfg, "run_on_ui", bool(run_on_ui_cb.isChecked()))
        config._cfg_set(cfg, "sticky_unlock", bool(sticky_unlock_cb.isChecked()))
        config._cfg_set(cfg, "stability.default_threshold", float(stab_default_spin.value()))
        config._cfg_set(cfg, "stability.aggregation", str(stab_agg_combo.currentText()))

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
    build_settings=_build_settings,
)


def _open_settings_dialog() -> None:
    from ..ui.settings import open_settings_dialog

    open_settings_dialog()

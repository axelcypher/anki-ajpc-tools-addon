from __future__ import annotations

import json
import re
from typing import Any

from aqt import appVersion, mw
from aqt.qt import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStandardItem,
    QStandardItemModel,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
    Qt,
)
from aqt.utils import showInfo, show_info

from .. import config, logging
from ..version import __version__


def _format_json(data: Any) -> str:
    try:
        return json.dumps(data, indent=2, ensure_ascii=False)
    except Exception:
        return "{}"


def _parse_watch_nids(text: str) -> tuple[list[int], list[str]]:
    tokens = re.split(r"[,\s;]+", text.strip())
    out: list[int] = []
    bad: list[str] = []
    for tok in tokens:
        if not tok:
            continue
        try:
            out.append(int(tok))
        except Exception:
            bad.append(tok)
    return out, bad


def _parse_list_entries(text: str) -> list[str]:
    tokens = re.split(r"[,\n;]+", text.strip())
    out: list[str] = []
    for tok in tokens:
        s = tok.strip()
        if s:
            out.append(s)
    return out


def _update_menu_state() -> None:
    if mw is None:
        return
    actions = getattr(mw, "_familygate_run_actions", None)
    if not actions:
        return
    for act in actions:
        try:
            act.setEnabled(bool(config.RUN_ON_UI))
        except Exception:
            continue
    try:
        open_log_action = getattr(mw, "_familygate_open_log_action", None)
        if open_log_action is not None:
            open_log_action.setVisible(bool(config.DEBUG))
    except Exception:
        pass


def _get_deck_names() -> list[str]:
    if mw is None or not getattr(mw, "col", None):
        return []
    names: list[str] = []
    try:
        names = [name for name, _did in mw.col.decks.all_names_and_ids()]
    except Exception:
        try:
            names = list(mw.col.decks.all_names())
        except Exception:
            try:
                decks = mw.col.decks.all()
                for d in decks:
                    if isinstance(d, dict):
                        name = d.get("name")
                    else:
                        name = getattr(d, "name", None)
                    if name:
                        names.append(str(name))
            except Exception:
                names = []
    return sorted(set(names))


def _get_note_type_names() -> list[str]:
    if mw is None or not getattr(mw, "col", None):
        return []
    names: list[str] = []
    try:
        models = mw.col.models.all()
        for m in models:
            if isinstance(m, dict):
                name = m.get("name")
            else:
                name = getattr(m, "name", None)
            if name:
                names.append(str(name))
    except Exception:
        names = []
    return sorted(set(names))


def _get_fields_for_note_type(note_type_name: str) -> list[str]:
    if mw is None or not getattr(mw, "col", None):
        return []
    try:
        model = mw.col.models.by_name(note_type_name)
    except Exception:
        model = None
    if not model:
        return []
    fields = model.get("flds", []) if isinstance(model, dict) else []
    out: list[str] = []
    for f in fields:
        if isinstance(f, dict):
            name = f.get("name")
        else:
            name = getattr(f, "name", None)
        if name:
            out.append(str(name))
    return out


def _get_template_names(note_type_name: str) -> list[str]:
    if mw is None or not getattr(mw, "col", None):
        return []
    try:
        model = mw.col.models.by_name(note_type_name)
    except Exception:
        model = None
    if not model:
        return []
    tmpls = model.get("tmpls", []) if isinstance(model, dict) else []
    out: list[str] = []
    for t in tmpls:
        if isinstance(t, dict):
            name = t.get("name")
        else:
            name = getattr(t, "name", None)
        if name:
            out.append(str(name))
    return out


def _populate_field_combo(combo: QComboBox, field_names: list[str], current_value: str) -> None:
    combo.setEditable(True)
    combo.addItem("", "")
    for name in field_names:
        combo.addItem(name, name)
    cur = (current_value or "").strip()
    if cur:
        idx = combo.findData(cur)
        if idx == -1:
            combo.addItem(f"{cur} (missing)", cur)
            idx = combo.findData(cur)
        if idx >= 0:
            combo.setCurrentIndex(idx)


def _checked_items(model: QStandardItemModel) -> list[str]:
    out: list[str] = []
    for i in range(model.rowCount()):
        item = model.item(i)
        if item and item.checkState() == Qt.CheckState.Checked:
            out.append(item.text())
    return out


def _sync_checkable_combo_text(combo: QComboBox, model: QStandardItemModel) -> None:
    checked = _checked_items(model)
    if checked:
        text = ", ".join(checked[:3])
        if len(checked) > 3:
            text += f" (+{len(checked) - 3})"
    else:
        text = "<none>"
    if combo.lineEdit() is not None:
        combo.lineEdit().setText(text)


def _make_checkable_combo(items: list[str], selected: list[str]) -> tuple[QComboBox, QStandardItemModel]:
    combo = QComboBox()
    combo.setEditable(True)
    if combo.lineEdit() is not None:
        combo.lineEdit().setReadOnly(True)
    model = QStandardItemModel(combo)
    selected_set = set(selected or [])
    for name in items:
        item = QStandardItem(name)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        item.setData(
            Qt.CheckState.Checked if name in selected_set else Qt.CheckState.Unchecked,
            Qt.ItemDataRole.CheckStateRole,
        )
        model.appendRow(item)
    combo.setModel(model)

    def _toggle(idx) -> None:
        item = model.itemFromIndex(idx)
        if not item:
            return
        if item.checkState() == Qt.CheckState.Checked:
            item.setCheckState(Qt.CheckState.Unchecked)
        else:
            item.setCheckState(Qt.CheckState.Checked)
        _sync_checkable_combo_text(combo, model)

    combo.view().pressed.connect(_toggle)
    model.itemChanged.connect(lambda _item: _sync_checkable_combo_text(combo, model))
    _sync_checkable_combo_text(combo, model)
    return combo, model


def _populate_deck_combo(combo: QComboBox, deck_names: list[str], current_value: str) -> None:
    combo.setEditable(False)
    combo.addItem("<none>", "")
    for name in deck_names:
        combo.addItem(name, name)
    cur = (current_value or "").strip()
    if cur:
        idx = combo.findData(cur)
        if idx == -1:
            combo.addItem(f"{cur} (missing)", cur)
            idx = combo.findData(cur)
        if idx >= 0:
            combo.setCurrentIndex(idx)
    else:
        combo.setCurrentIndex(0)


def _combo_value(combo: QComboBox) -> str:
    data = combo.currentData()
    if data is None:
        return str(combo.currentText()).strip()
    return str(data).strip()


def open_settings_dialog() -> None:
    config.reload_config()
    logging.dbg("reloaded config", "debug=", config.DEBUG, "run_on_sync=", config.RUN_ON_SYNC, "run_on_ui=", config.RUN_ON_UI)

    if mw is None:
        showInfo("No main window.")
        return

    dlg = QDialog(mw)
    dlg.setWindowTitle("AJpC Tools Settings")
    dlg.resize(760, 640)

    tabs = QTabWidget(dlg)

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

    tabs.addTab(general_tab, "General")

    family_tab = QWidget()
    family_layout = QVBoxLayout()
    family_tab.setLayout(family_layout)
    family_form = QFormLayout()
    family_layout.addLayout(family_form)

    family_enabled_cb = QCheckBox()
    family_enabled_cb.setChecked(config.FAMILY_GATE_ENABLED)
    family_form.addRow("Enabled", family_enabled_cb)

    family_field_edit = QLineEdit()
    family_field_edit.setText(config.FAMILY_FIELD)
    family_form.addRow("Family field", family_field_edit)

    family_sep_edit = QLineEdit()
    family_sep_edit.setText(config.FAMILY_SEP)
    family_form.addRow("Family separator", family_sep_edit)

    family_prio_spin = QSpinBox()
    family_prio_spin.setRange(-10000, 10000)
    family_prio_spin.setValue(config.FAMILY_DEFAULT_PRIO)
    family_form.addRow("Default prio", family_prio_spin)

    family_note_type_names = sorted(
        set(_get_note_type_names() + list((config.FAMILY_NOTE_TYPES or {}).keys()))
    )
    family_note_type_combo, family_note_type_model = _make_checkable_combo(
        family_note_type_names, list((config.FAMILY_NOTE_TYPES or {}).keys())
    )
    family_form.addRow("Note types", family_note_type_combo)

    family_stages_group = QGroupBox("Stages per note type")
    family_stages_layout = QVBoxLayout()
    family_stages_group.setLayout(family_stages_layout)
    family_layout.addWidget(family_stages_group)

    family_stages_scroll = QScrollArea()
    family_stages_scroll.setWidgetResizable(True)
    family_stages_container = QWidget()
    family_stages_container_layout = QVBoxLayout()
    family_stages_container.setLayout(family_stages_container_layout)
    family_stages_scroll.setWidget(family_stages_container)
    family_stages_layout.addWidget(family_stages_scroll)

    family_state: dict[str, list[dict[str, Any]]] = {}
    for nt_name, nt_cfg in (config.FAMILY_NOTE_TYPES or {}).items():
        stages = nt_cfg.get("stages") if isinstance(nt_cfg, dict) else None
        out_stages: list[dict[str, Any]] = []
        if isinstance(stages, list):
            for st in stages:
                if isinstance(st, dict):
                    tmpls = [str(x) for x in (st.get("templates") or [])]
                    thr = float(st.get("threshold", config.STABILITY_DEFAULT_THRESHOLD))
                    out_stages.append({"templates": tmpls, "threshold": thr})
                elif isinstance(st, list):
                    tmpls = [str(x) for x in st]
                    out_stages.append(
                        {"templates": tmpls, "threshold": config.STABILITY_DEFAULT_THRESHOLD}
                    )
        family_state[nt_name] = out_stages

    family_note_type_widgets: dict[str, list[dict[str, Any]]] = {}

    def _capture_family_state() -> None:
        for nt_name, stages in family_note_type_widgets.items():
            out: list[dict[str, Any]] = []
            for stage in stages:
                templates_model = stage["templates_model"]
                threshold_spin = stage["threshold_spin"]
                out.append(
                    {
                        "templates": _checked_items(templates_model),
                        "threshold": float(threshold_spin.value()),
                    }
                )
            family_state[nt_name] = out

    def _clear_family_layout() -> None:
        while family_stages_container_layout.count():
            item = family_stages_container_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    def _add_family_stage(nt_name: str) -> None:
        _capture_family_state()
        family_state.setdefault(nt_name, []).append(
            {"templates": [], "threshold": float(config.STABILITY_DEFAULT_THRESHOLD)}
        )
        _refresh_family_stages(capture=False)

    def _remove_family_stage(nt_name: str, idx: int) -> None:
        _capture_family_state()
        stages = family_state.get(nt_name, [])
        if 0 <= idx < len(stages):
            del stages[idx]
        family_state[nt_name] = stages
        _refresh_family_stages(capture=False)

    def _refresh_family_stages(*, capture: bool = True) -> None:
        if capture:
            _capture_family_state()
        _clear_family_layout()
        family_note_type_widgets.clear()

        selected_types = _checked_items(family_note_type_model)
        for nt_name in selected_types:
            stages = family_state.get(nt_name, [])
            family_note_type_widgets[nt_name] = []

            group = QGroupBox(nt_name)
            group_layout = QVBoxLayout()
            group.setLayout(group_layout)

            add_btn = QPushButton("Add stage")
            add_btn.clicked.connect(lambda _=None, n=nt_name: _add_family_stage(n))
            group_layout.addWidget(add_btn)

            all_templates = set(_get_template_names(nt_name))
            for st in stages:
                for t in st.get("templates", []) or []:
                    all_templates.add(str(t))
            template_names = sorted(all_templates)

            for idx, st in enumerate(stages):
                stage_box = QGroupBox(f"Stage {idx}")
                stage_form = QFormLayout()
                stage_box.setLayout(stage_form)

                templates_combo, templates_model = _make_checkable_combo(
                    template_names, list(st.get("templates", []) or [])
                )
                stage_form.addRow("Templates", templates_combo)

                threshold_spin = QDoubleSpinBox()
                threshold_spin.setDecimals(2)
                threshold_spin.setRange(0, 100000)
                threshold_spin.setValue(float(st.get("threshold", config.STABILITY_DEFAULT_THRESHOLD)))
                stage_form.addRow("Threshold", threshold_spin)

                remove_btn = QPushButton("Remove stage")
                remove_btn.clicked.connect(lambda _=None, n=nt_name, i=idx: _remove_family_stage(n, i))
                stage_form.addRow(remove_btn)

                group_layout.addWidget(stage_box)
                family_note_type_widgets[nt_name].append(
                    {
                        "templates_model": templates_model,
                        "threshold_spin": threshold_spin,
                    }
                )

            family_stages_container_layout.addWidget(group)

        family_stages_container_layout.addStretch(1)

    _refresh_family_stages()
    family_note_type_model.itemChanged.connect(lambda _item: _refresh_family_stages())

    tabs.addTab(family_tab, "Family Gate")

    example_tab = QWidget()
    example_form = QFormLayout()
    example_tab.setLayout(example_form)

    deck_names = _get_deck_names()

    example_enabled_cb = QCheckBox()
    example_enabled_cb.setChecked(config.EXAMPLE_GATE_ENABLED)
    example_form.addRow("Enabled", example_enabled_cb)

    vocab_deck_combo = QComboBox()
    _populate_deck_combo(vocab_deck_combo, deck_names, config.VOCAB_DECK)
    example_form.addRow("Vocab deck", vocab_deck_combo)

    example_deck_combo = QComboBox()
    _populate_deck_combo(example_deck_combo, deck_names, config.EXAMPLE_DECK)
    example_form.addRow("Example deck", example_deck_combo)

    vocab_key_edit = QLineEdit()
    vocab_key_edit.setText(config.VOCAB_KEY_FIELD)
    example_form.addRow("Vocab key field", vocab_key_edit)

    example_key_edit = QLineEdit()
    example_key_edit.setText(config.EXAMPLE_KEY_FIELD)
    example_form.addRow("Example key field", example_key_edit)

    example_stage_sep_edit = QLineEdit()
    example_stage_sep_edit.setText(config.EX_STAGE_SEP)
    example_form.addRow("Stage separator", example_stage_sep_edit)

    example_default_stage_spin = QSpinBox()
    example_default_stage_spin.setRange(0, 10000)
    example_default_stage_spin.setValue(config.EX_STAGE_DEFAULT)
    example_form.addRow("Default stage", example_default_stage_spin)

    tabs.addTab(example_tab, "Example Gate")

    jlpt_tab = QWidget()
    jlpt_layout = QVBoxLayout()
    jlpt_tab.setLayout(jlpt_layout)
    jlpt_form = QFormLayout()
    jlpt_layout.addLayout(jlpt_form)

    jlpt_deck_combo, jlpt_deck_model = _make_checkable_combo(
        deck_names, list(config.JLPT_TAGGER_DECKS or [])
    )
    jlpt_form.addRow("Decks", jlpt_deck_combo)

    note_type_names = sorted(
        set(
            _get_note_type_names()
            + list((config.JLPT_TAGGER_NOTE_TYPES or []))
            + list((config.FAMILY_NOTE_TYPES or {}).keys())
        )
    )
    jlpt_note_type_combo, jlpt_note_type_model = _make_checkable_combo(
        note_type_names, list(config.JLPT_TAGGER_NOTE_TYPES or [])
    )
    jlpt_form.addRow("Note types", jlpt_note_type_combo)

    fields_group = QGroupBox("Fields per note type")
    fields_group_layout = QVBoxLayout()
    fields_group.setLayout(fields_group_layout)

    fields_scroll = QScrollArea()
    fields_scroll.setWidgetResizable(True)
    fields_container = QWidget()
    fields_container_layout = QVBoxLayout()
    fields_container.setLayout(fields_container_layout)
    fields_scroll.setWidget(fields_container)
    fields_group_layout.addWidget(fields_scroll)

    jlpt_layout.addWidget(fields_group)

    jlpt_map_label = QLabel("Tag mapping (JSON)")
    jlpt_map_edit = QPlainTextEdit()
    jlpt_map_edit.setPlainText(
        _format_json(config.JLPT_TAGGER_TAG_MAP or config.DEFAULT_JLPT_TAG_MAP)
    )
    jlpt_map_edit.setMinimumHeight(140)
    jlpt_layout.addWidget(jlpt_map_label)
    jlpt_layout.addWidget(jlpt_map_edit)

    fields_state: dict[str, dict[str, str]] = dict(config.JLPT_TAGGER_FIELDS or {})
    note_type_fields_widgets: dict[str, tuple[QComboBox, QComboBox]] = {}

    def _clear_layout(layout: QVBoxLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    def _capture_fields_state() -> None:
        for nt_name, widgets in note_type_fields_widgets.items():
            vocab_combo, reading_combo = widgets
            fields_state[nt_name] = {
                "vocab_field": _combo_value(vocab_combo),
                "reading_field": _combo_value(reading_combo),
            }

    def _refresh_note_type_fields() -> None:
        _capture_fields_state()
        _clear_layout(fields_container_layout)
        note_type_fields_widgets.clear()

        selected_types = _checked_items(jlpt_note_type_model)
        for nt_name in selected_types:
            field_names = _get_fields_for_note_type(nt_name)
            cfg_fields = fields_state.get(nt_name, {})
            vocab_combo = QComboBox()
            reading_combo = QComboBox()
            _populate_field_combo(vocab_combo, field_names, cfg_fields.get("vocab_field", ""))
            _populate_field_combo(reading_combo, field_names, cfg_fields.get("reading_field", ""))

            group = QGroupBox(nt_name)
            group_form = QFormLayout()
            group_form.addRow("Vocab field", vocab_combo)
            group_form.addRow("Reading field", reading_combo)
            group.setLayout(group_form)

            fields_container_layout.addWidget(group)
            note_type_fields_widgets[nt_name] = (vocab_combo, reading_combo)

        fields_container_layout.addStretch(1)

    _refresh_note_type_fields()
    jlpt_note_type_model.itemChanged.connect(lambda _item: _refresh_note_type_fields())

    tabs.addTab(jlpt_tab, "JLPT Tagger")

    card_sorter_tab = QWidget()
    card_sorter_layout = QVBoxLayout()
    card_sorter_tab.setLayout(card_sorter_layout)
    card_sorter_form = QFormLayout()
    card_sorter_layout.addLayout(card_sorter_form)

    card_sorter_enabled_cb = QCheckBox()
    card_sorter_enabled_cb.setChecked(config.CARD_SORTER_ENABLED)
    card_sorter_form.addRow("Enabled", card_sorter_enabled_cb)

    card_sorter_run_on_add_cb = QCheckBox()
    card_sorter_run_on_add_cb.setChecked(config.CARD_SORTER_RUN_ON_ADD)
    card_sorter_form.addRow("Run on add note", card_sorter_run_on_add_cb)

    card_sorter_run_on_sync_start_cb = QCheckBox()
    card_sorter_run_on_sync_start_cb.setChecked(config.CARD_SORTER_RUN_ON_SYNC_START)
    card_sorter_form.addRow("Run on sync start", card_sorter_run_on_sync_start_cb)

    card_sorter_run_on_sync_finish_cb = QCheckBox()
    card_sorter_run_on_sync_finish_cb.setChecked(config.CARD_SORTER_RUN_ON_SYNC_FINISH)
    card_sorter_form.addRow("Run on sync finish", card_sorter_run_on_sync_finish_cb)

    card_sorter_exclude_deck_names = sorted(
        set(deck_names + list(config.CARD_SORTER_EXCLUDE_DECKS or []))
    )
    card_sorter_exclude_decks_combo, card_sorter_exclude_decks_model = _make_checkable_combo(
        card_sorter_exclude_deck_names, list(config.CARD_SORTER_EXCLUDE_DECKS or [])
    )
    card_sorter_form.addRow("Exclude decks", card_sorter_exclude_decks_combo)

    card_sorter_note_type_names = sorted(
        set(_get_note_type_names() + list((config.CARD_SORTER_NOTE_TYPES or {}).keys()))
    )
    card_sorter_note_type_combo, card_sorter_note_type_model = _make_checkable_combo(
        card_sorter_note_type_names, list((config.CARD_SORTER_NOTE_TYPES or {}).keys())
    )
    card_sorter_form.addRow("Note types", card_sorter_note_type_combo)

    card_sorter_rules_group = QGroupBox("Rules per note type")
    card_sorter_rules_layout = QVBoxLayout()
    card_sorter_rules_group.setLayout(card_sorter_rules_layout)
    card_sorter_layout.addWidget(card_sorter_rules_group)

    card_sorter_exclude_tags_label = QLabel("Exclude tags (one per line or comma-separated)")
    card_sorter_exclude_tags_edit = QPlainTextEdit()
    if config.CARD_SORTER_EXCLUDE_TAGS:
        card_sorter_exclude_tags_edit.setPlainText("\n".join(config.CARD_SORTER_EXCLUDE_TAGS))
    card_sorter_exclude_tags_edit.setMaximumHeight(60)
    card_sorter_rules_layout.addWidget(card_sorter_exclude_tags_label)
    card_sorter_rules_layout.addWidget(card_sorter_exclude_tags_edit)

    card_sorter_rules_scroll = QScrollArea()
    card_sorter_rules_scroll.setWidgetResizable(True)
    card_sorter_rules_container = QWidget()
    card_sorter_rules_container_layout = QVBoxLayout()
    card_sorter_rules_container.setLayout(card_sorter_rules_container_layout)
    card_sorter_rules_scroll.setWidget(card_sorter_rules_container)
    card_sorter_rules_layout.addWidget(card_sorter_rules_scroll)

    card_sorter_state: dict[str, dict[str, Any]] = {}
    for nt_name, nt_cfg in (config.CARD_SORTER_NOTE_TYPES or {}).items():
        if not isinstance(nt_cfg, dict):
            continue
        mode = str(nt_cfg.get("mode", "by_template")).strip() or "by_template"
        default_deck = str(nt_cfg.get("default_deck", "")).strip()
        by_template_raw = nt_cfg.get("by_template", {}) or {}
        by_template: dict[str, str] = {}
        if isinstance(by_template_raw, dict):
            for k, v in by_template_raw.items():
                key = str(k).strip()
                val = str(v).strip()
                if key:
                    by_template[key] = val
        card_sorter_state[nt_name] = {
            "mode": mode,
            "default_deck": default_deck,
            "by_template": by_template,
        }

    card_sorter_note_type_widgets: dict[str, dict[str, Any]] = {}

    def _capture_card_sorter_state() -> None:
        for nt_name, widgets in card_sorter_note_type_widgets.items():
            mode_combo = widgets["mode_combo"]
            default_deck_combo = widgets["default_deck_combo"]
            template_combos = widgets["template_combos"]
            mode = _combo_value(mode_combo) or "by_template"
            default_deck = _combo_value(default_deck_combo)
            by_template: dict[str, str] = {}
            for tmpl_name, combo in template_combos.items():
                deck_name = _combo_value(combo)
                if deck_name:
                    by_template[tmpl_name] = deck_name
            card_sorter_state[nt_name] = {
                "mode": mode,
                "default_deck": default_deck,
                "by_template": by_template,
            }

    def _clear_card_sorter_layout() -> None:
        while card_sorter_rules_container_layout.count():
            item = card_sorter_rules_container_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    def _refresh_card_sorter_rules() -> None:
        _capture_card_sorter_state()
        _clear_card_sorter_layout()
        card_sorter_note_type_widgets.clear()

        selected_types = _checked_items(card_sorter_note_type_model)
        for nt_name in selected_types:
            cfg = card_sorter_state.get(nt_name)
            if not cfg:
                cfg = {"mode": "by_template", "default_deck": "", "by_template": {}}
                card_sorter_state[nt_name] = cfg

            group = QGroupBox(nt_name)
            group_layout = QVBoxLayout()
            group.setLayout(group_layout)

            form = QFormLayout()
            group_layout.addLayout(form)

            mode_combo = QComboBox()
            mode_combo.addItem("All cards -> deck", "all")
            mode_combo.addItem("By template", "by_template")
            mode_val = cfg.get("mode", "by_template")
            idx = mode_combo.findData(mode_val)
            if idx < 0:
                idx = 1
            mode_combo.setCurrentIndex(idx)
            form.addRow("Mode", mode_combo)

            default_deck_combo = QComboBox()
            _populate_deck_combo(default_deck_combo, deck_names, cfg.get("default_deck", ""))
            form.addRow("Default deck", default_deck_combo)

            template_group = QGroupBox("Template mapping")
            template_form = QFormLayout()
            template_group.setLayout(template_form)

            by_template = cfg.get("by_template", {}) or {}
            if not isinstance(by_template, dict):
                by_template = {}
            template_names = sorted(set(_get_template_names(nt_name)) | set(by_template.keys()))
            template_combos: dict[str, QComboBox] = {}
            for tmpl_name in template_names:
                deck_combo = QComboBox()
                _populate_deck_combo(deck_combo, deck_names, by_template.get(tmpl_name, ""))
                template_form.addRow(tmpl_name, deck_combo)
                template_combos[tmpl_name] = deck_combo

            group_layout.addWidget(template_group)

            def _toggle_template_group(_idx, combo=mode_combo, box=template_group) -> None:
                box.setVisible(_combo_value(combo) == "by_template")

            mode_combo.currentIndexChanged.connect(_toggle_template_group)
            _toggle_template_group(0)

            card_sorter_rules_container_layout.addWidget(group)
            card_sorter_note_type_widgets[nt_name] = {
                "mode_combo": mode_combo,
                "default_deck_combo": default_deck_combo,
                "template_combos": template_combos,
            }

        card_sorter_rules_container_layout.addStretch(1)

    _refresh_card_sorter_rules()
    card_sorter_note_type_model.itemChanged.connect(lambda _item: _refresh_card_sorter_rules())

    tabs.addTab(card_sorter_tab, "Card Sorter")

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

    tabs.addTab(debug_tab, "Debug")

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
    info_layout.addWidget(info_header)

    info_doc = QTextBrowser()
    doc_text = (
        "# AJpC Add-on Documentation (Family Gate, Example Gate, JLPT Tagger, Card Sorter)\n"
        "\n"
        "## What this add-on does\n"
        "\n"
        "This add-on helps you control *when* Anki cards become available, so you can learn in a structured order:\n"
        "\n"
        "1. **Family Gate**\n"
        "   Keeps \"advanced\" cards hidden until the \"base\" cards are learned well enough.\n"
        "2. **Example Gate**\n"
        "   Unlocks example sentence cards only after the related vocabulary is ready.\n"
        "3. **JLPT Tagger**\n"
        "   Looks up a word on Jisho, verifies it using the reading, and adds helpful tags (JLPT level + \"common\" where applicable).\n"
        "4. **Card Sorter**\n"
        "   Moves cards into the right decks based on note type and card template.\n"
        "\n"
        "---\n"
        "\n"
        "## Core concepts\n"
        "\n"
        "### Notes, Cards, and Templates\n"
        "\n"
        "* A **note** is the entry with your fields (e.g., Vocab, Reading, FamilyID).\n"
        "* A **card** is what you review.\n"
        "* A **template** is the card type name shown in Anki (e.g., \"German -> Base Form\").\n"
        "\n"
        "When the add-on says \"template name\", it means the **exact card type name** in your note type. Spacing matters.\n"
        "\n"
        "---\n"
        "\n"
        "## Family Gate\n"
        "\n"
        "### Goal\n"
        "\n"
        "Only show the next set of cards when you have learned the prerequisite cards to a certain quality level.\n"
        "\n"
        "### What \"FamilyID\" means\n"
        "\n"
        "Each note can contain one or more entries in the **FamilyID** field.\n"
        "\n"
        "* Notes that share the same FamilyID entry are treated as related.\n"
        "* This relation is used to control availability across related notes.\n"
        "\n"
        "### Stages: learning steps inside one note\n"
        "\n"
        "For each note type, you define **Stages**:\n"
        "\n"
        "* **Stage 0** is the \"foundation stage\" (usually the main recognition/production cards).\n"
        "* Later stages are \"extra\" cards (conjugations, variations, additional directions, etc.).\n"
        "\n"
        "Each stage contains:\n"
        "\n"
        "* Which **card types** belong to it (by template name)\n"
        "* A **threshold** (how well you must know those cards before the stage is considered \"ready\")\n"
        "\n"
        "### What \"threshold\" means\n"
        "\n"
        "Threshold is measured in **FSRS Stability**, and the values are treated as **days**.\n"
        "\n"
        "* Higher stability means Anki expects you to remember it longer.\n"
        "* A stage becomes \"ready\" when the cards in that stage reach the configured stability requirement (in days).\n"
        "\n"
        "### How unlocking works inside a note (stage chain)\n"
        "\n"
        "Within a single note:\n"
        "\n"
        "* If the gate is open for that note, **Stage 0** cards are allowed (unsuspended).\n"
        "* **Stage 1** cards are allowed only if **Stage 0 is ready**.\n"
        "* **Stage 2** cards are allowed only if **Stage 1 is ready**, and so on.\n"
        "\n"
        "So within one note, stages unlock like a chain.\n"
        "\n"
        "---\n"
        "\n"
        "## Family Gate Priority (learning order between related notes)\n"
        "\n"
        "### Why priority exists\n"
        "\n"
        "Sometimes you want multiple related notes, but not all at once.\n"
        "\n"
        "Priority is how you enforce that order **between notes** (for example: base words first, then a pattern/suffix, then a compound).\n"
        "\n"
        "### How it behaves\n"
        "\n"
        "You attach a \"priority number\" to a FamilyID entry inside the FamilyID field:\n"
        "\n"
        "* **Priority 0** = available first\n"
        "* **Priority 1** = unlocks only after all priority 0 notes in that family are **Stage 0 ready**\n"
        "* **Priority 2** = unlocks only after all priority 1 notes are **Stage 0 ready**\n"
        "  ...and so on.\n"
        "\n"
        "If a note contains multiple family links, **all of them must be satisfied** before the note can unlock.\n"
        "\n"
        "### Example: deguchi / kita / ~guchi / kita-guchi\n"
        "\n"
        "Setup:\n"
        "\n"
        "* **kita** has: kita at priority 0 (kita or kita@0)\n"
        "* **deguchi** has: deguchi at priority 0 (deguchi or deguchi@0)\n"
        "* **~guchi** has: deguchi at priority 1 (deguchi@1)\n"
        "* **kita-guchi** has: kita at priority 1 and deguchi at priority 2 (kita@1; deguchi@2)\n"
        "\n"
        "Learning order:\n"
        "\n"
        "1. **deguchi + kita** (priority 0 -> available first)\n"
        "2. **~guchi** (waits until deguchi is Stage 0 ready)\n"
        "3. **kita-guchi** (waits until kita is Stage 0 ready AND deguchi is Stage 1 ready)\n"
        "\n"
        "This ensures the compound appears only after its components (and the pattern) are established.\n"
        "\n"
        "---\n"
        "\n"
        "## Example Gate\n"
        "\n"
        "### Goal\n"
        "\n"
        "Example sentences should appear only when the vocab is ready.\n"
        "\n"
        "### How matching works\n"
        "\n"
        "* You have two note types:\n"
        "\n"
        "  * a **vocab note**\n"
        "  * an **example note**\n"
        "* Both vocab notes and example notes contain a key field (e.g., `Vocab`).\n"
        "* The add-on uses an **exact match**:\n"
        "\n"
        "  * The example note's key field must be **identical** to the vocab note's key field.\n"
        "\n"
        "### When an example card unlocks\n"
        "\n"
        "An example card is allowed only if:\n"
        "\n"
        "* the matching vocab entry exists (exact key match), and\n"
        "* the vocab entry is ready according to the configured stability requirement (days)\n"
        "\n"
        "(There is no optional stage selection via suffix; example unlocking is driven by stability readiness.)\n"
        "\n"
        "---\n"
        "\n"
        "## JLPT Tagger\n"
        "\n"
        "### Goal\n"
        "\n"
        "Automatically tag your vocab with:\n"
        "\n"
        "* JLPT level (N5-N1 where available)\n"
        "* \"common\" if Jisho marks it as common\n"
        "* a fallback tag if no JLPT level exists\n"
        "\n"
        "### How it works\n"
        "\n"
        "1. The add-on reads the word from your **Vocab** field.\n"
        "2. It searches Jisho for that term.\n"
        "3. It compares the reading from Anki to the reading from Jisho.\n"
        "4. Only if it matches, tags are applied.\n"
        "\n"
        "### Tag rules\n"
        "\n"
        "* If multiple JLPT levels appear, the lowest level (easiest) is chosen.\n"
        "* If no JLPT level exists, it applies your configured \"no JLPT\" tag.\n"
        "* Adds \"common\" if the entry is marked common.\n"
        "\n"
        "Credit: https://ankiweb.net/shared/info/368576817 - I got the idea for the tagger\n"
        "from this add-on. Since it doesn't work reliably on the current Anki version,\n"
        "I implemented my own version.\n"
        "\n"
        "---\n"
        "\n"
        "## Card Sorter\n"
        "\n"
        "### Goal\n"
        "\n"
        "Automatically move cards into the correct deck so your study order stays clean and predictable.\n"
        "\n"
        "### How it works\n"
        "\n"
        "* You pick one or more **note types**.\n"
        "* For each note type, you either:\n"
        "  * send **all cards** to one deck, or\n"
        "  * map **each card template** to a specific deck.\n"
        "* Excluded decks and tags are ignored.\n"
        "* The sorter can run on add note, on sync, or manually from the AJpC menu.\n"
        "\n"
        "### Example\n"
        "\n"
        "Note type: **JP Vocab**\n"
        "\n"
        "* Template \"Front -> Back\" -> deck \"Japanese::Vocab\"\n"
        "* Template \"Back -> Front\" -> deck \"Japanese::Vocab::Reverse\"\n"
        "\n"
        "Result: each card goes to the exact deck you want without manual dragging.\n"
        "\n"
        "Credit: https://ankiweb.net/shared/info/1310787152 - The Card Sorter feature is based on this add-on.\n"
        "\n"
        "---\n"
        "\n"
        "## Usage\n"
        "\n"
        "In Anki you have an AJpC menu with:\n"
        "\n"
        "* **Run Family Gate**\n"
        "* **Run Example Gate**\n"
        "* **Run JLPT Tagger**\n"
        "* **Run Card Sorter**\n"
        "\n"
        "All settings are configured via the Add-on Settings UI.\n"
    )
    if hasattr(info_doc, "setMarkdown"):
        info_doc.setMarkdown(doc_text)
    else:
        info_doc.setPlainText(doc_text)
    info_doc.setMinimumHeight(260)
    info_layout.addWidget(info_doc)

    tabs.addTab(info_tab, "Info")

    buttons = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
    )

    def _save() -> None:
        cfg = config._load_config()
        if not isinstance(cfg, dict):
            cfg = {}

        errors: list[str] = []

        fam_sep = family_sep_edit.text().strip()
        if not fam_sep:
            errors.append("Family separator cannot be empty.")

        ex_stage_sep = example_stage_sep_edit.text().strip()
        if not ex_stage_sep:
            errors.append("Example stage separator cannot be empty.")

        _capture_family_state()
        family_note_types = _checked_items(family_note_type_model)
        family_note_types_cfg: dict[str, Any] = {}
        for nt_name in family_note_types:
            stages = family_state.get(nt_name, [])
            if not stages:
                errors.append(f"Family Gate: no stages defined for note type: {nt_name}")
                continue
            stage_cfgs: list[dict[str, Any]] = []
            for s_idx, st in enumerate(stages):
                tmpls = [str(x) for x in (st.get("templates") or []) if str(x)]
                if not tmpls:
                    errors.append(f"Family Gate: stage {s_idx} has no templates ({nt_name})")
                    continue
                thr = float(st.get("threshold", config.STABILITY_DEFAULT_THRESHOLD))
                stage_cfgs.append({"templates": tmpls, "threshold": thr})
            if stage_cfgs:
                family_note_types_cfg[nt_name] = {"stages": stage_cfgs}

        watch_nids, bad_tokens = _parse_watch_nids(watch_nids_edit.toPlainText())
        if bad_tokens:
            errors.append("Watch NIDs invalid: " + ", ".join(bad_tokens))

        _capture_fields_state()
        jlpt_decks = _checked_items(jlpt_deck_model)
        jlpt_note_types = _checked_items(jlpt_note_type_model)
        jlpt_fields: dict[str, dict[str, str]] = dict(fields_state)

        for nt_name in jlpt_note_types:
            cfg_fields = jlpt_fields.get(nt_name, {})
            vocab_field = str(cfg_fields.get("vocab_field", "")).strip()
            reading_field = str(cfg_fields.get("reading_field", "")).strip()
            if not vocab_field or not reading_field:
                errors.append(f"JLPT fields missing for note type: {nt_name}")
            else:
                jlpt_fields[nt_name] = {
                    "vocab_field": vocab_field,
                    "reading_field": reading_field,
                }

        jlpt_map_text = jlpt_map_edit.toPlainText().strip()
        if jlpt_map_text:
            try:
                jlpt_map_val = json.loads(jlpt_map_text)
            except Exception as exc:
                errors.append(f"JLPT tag map JSON invalid: {exc}")
                jlpt_map_val = None
            else:
                if not isinstance(jlpt_map_val, dict):
                    errors.append("JLPT tag map must be a JSON object.")
        else:
            jlpt_map_val = config.DEFAULT_JLPT_TAG_MAP.copy()

        _capture_card_sorter_state()
        card_sorter_note_types = _checked_items(card_sorter_note_type_model)
        card_sorter_cfg: dict[str, Any] = {}
        for nt_name in card_sorter_note_types:
            cfg_state = card_sorter_state.get(nt_name, {})
            mode = str(cfg_state.get("mode", "by_template")).strip() or "by_template"
            default_deck = str(cfg_state.get("default_deck", "")).strip()
            by_template_raw = cfg_state.get("by_template", {}) or {}
            by_template: dict[str, str] = {}
            if isinstance(by_template_raw, dict):
                for k, v in by_template_raw.items():
                    key = str(k).strip()
                    val = str(v).strip()
                    if key and val:
                        by_template[key] = val

            if mode == "all":
                if not default_deck:
                    errors.append(f"Card Sorter: default deck missing for note type: {nt_name}")
                    continue
                card_sorter_cfg[nt_name] = {"mode": "all", "default_deck": default_deck}
            else:
                if not by_template:
                    errors.append(f"Card Sorter: no template mapping for note type: {nt_name}")
                    continue
                payload = {"mode": "by_template", "by_template": by_template}
                if default_deck:
                    payload["default_deck"] = default_deck
                card_sorter_cfg[nt_name] = payload

        card_sorter_exclude_decks = _checked_items(card_sorter_exclude_decks_model)
        card_sorter_exclude_tags = _parse_list_entries(card_sorter_exclude_tags_edit.toPlainText())

        if errors:
            showInfo("Config not saved:\n" + "\n".join(errors))
            return

        config._cfg_set(cfg, "run_on_sync", bool(run_on_sync_cb.isChecked()))
        config._cfg_set(cfg, "run_on_ui", bool(run_on_ui_cb.isChecked()))
        config._cfg_set(cfg, "sticky_unlock", bool(sticky_unlock_cb.isChecked()))
        config._cfg_set(cfg, "stability.default_threshold", float(stab_default_spin.value()))
        config._cfg_set(cfg, "stability.aggregation", str(stab_agg_combo.currentText()))

        config._cfg_set(cfg, "family_gate.enabled", bool(family_enabled_cb.isChecked()))
        config._cfg_set(cfg, "family_gate.family.field", family_field_edit.text().strip())
        config._cfg_set(cfg, "family_gate.family.separator", fam_sep)
        config._cfg_set(cfg, "family_gate.family.default_prio", int(family_prio_spin.value()))
        config._cfg_set(cfg, "family_gate.note_types", family_note_types_cfg)

        config._cfg_set(cfg, "example_gate.enabled", bool(example_enabled_cb.isChecked()))
        config._cfg_set(cfg, "example_gate.vocab_deck", _combo_value(vocab_deck_combo))
        config._cfg_set(cfg, "example_gate.example_deck", _combo_value(example_deck_combo))
        config._cfg_set(cfg, "example_gate.vocab_key_field", vocab_key_edit.text().strip())
        config._cfg_set(cfg, "example_gate.example_key_field", example_key_edit.text().strip())
        config._cfg_set(cfg, "example_gate.example_stage_syntax.separator", ex_stage_sep)
        config._cfg_set(cfg, "example_gate.example_stage_syntax.default_stage", int(example_default_stage_spin.value()))

        config._cfg_set(cfg, "jlpt_tagger.decks", jlpt_decks)
        config._cfg_set(cfg, "jlpt_tagger.note_types", jlpt_note_types)
        config._cfg_set(cfg, "jlpt_tagger.note_type_fields", jlpt_fields)
        config._cfg_set(cfg, "jlpt_tagger.tag_map", jlpt_map_val)

        config._cfg_set(cfg, "card_sorter.enabled", bool(card_sorter_enabled_cb.isChecked()))
        config._cfg_set(cfg, "card_sorter.run_on_add_note", bool(card_sorter_run_on_add_cb.isChecked()))
        config._cfg_set(cfg, "card_sorter.run_on_sync_start", bool(card_sorter_run_on_sync_start_cb.isChecked()))
        config._cfg_set(cfg, "card_sorter.run_on_sync_finish", bool(card_sorter_run_on_sync_finish_cb.isChecked()))
        config._cfg_set(cfg, "card_sorter.exclude_decks", card_sorter_exclude_decks)
        config._cfg_set(cfg, "card_sorter.exclude_tags", card_sorter_exclude_tags)
        config._cfg_set(cfg, "card_sorter.note_types", card_sorter_cfg)

        config._cfg_set(cfg, "debug.enabled", bool(debug_enabled_cb.isChecked()))
        config._cfg_set(cfg, "debug.verify_suspension", bool(debug_verify_cb.isChecked()))
        config._cfg_set(cfg, "debug.watch_nids", watch_nids)

        try:
            with open(config.CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2, ensure_ascii=False)
        except Exception as exc:
            showInfo("Failed to save config:\n" + repr(exc))
            return

        config.reload_config()
        _update_menu_state()
        dlg.accept()
        show_info("Settings saved.")

    buttons.accepted.connect(_save)
    buttons.rejected.connect(dlg.reject)

    layout = QVBoxLayout(dlg)
    layout.addWidget(tabs)
    layout.addWidget(buttons)
    dlg.setLayout(layout)
    dlg.exec()

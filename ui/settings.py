from __future__ import annotations

import json
import os
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
    QHBoxLayout,
    QVBoxLayout,
    QWidget,
    Qt,
)
from aqt.utils import showInfo, show_info

from .. import config, logging
from . import menu
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
    api = getattr(mw, "_ajpc_menu_api", None)
    if isinstance(api, dict):
        refresh = api.get("refresh")
        if callable(refresh):
            refresh()


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


def _get_note_type_items() -> list[tuple[str, str]]:
    if mw is None or not getattr(mw, "col", None):
        return []
    items: list[tuple[str, str]] = []
    try:
        models = mw.col.models.all()
        for m in models:
            if isinstance(m, dict):
                name = m.get("name")
                mid = m.get("id")
            else:
                name = getattr(m, "name", None)
                mid = getattr(m, "id", None)
            if name and mid is not None:
                items.append((str(mid), str(name)))
    except Exception:
        items = []
    items.sort(key=lambda x: x[1].lower())
    return items


def _note_type_label(note_type_id: str) -> str:
    if mw is None or not getattr(mw, "col", None):
        return f"<missing {note_type_id}>"
    try:
        mid = int(str(note_type_id))
    except Exception:
        mid = None
    model = mw.col.models.get(mid) if mid is not None else None
    if not model:
        return f"<missing {note_type_id}>"
    return str(model.get("name", note_type_id))


def _merge_note_type_items(
    base: list[tuple[str, str]], extra_ids: list[str]
) -> list[tuple[str, str]]:
    out = list(base)
    seen = {str(k) for k, _ in base}
    for raw in extra_ids:
        sid = str(raw).strip()
        if not sid or sid in seen:
            continue
        out.append((sid, f"<missing {sid}>"))
        seen.add(sid)
    return out


def _get_fields_for_note_type(note_type_id: str) -> list[str]:
    if mw is None or not getattr(mw, "col", None):
        return []
    try:
        mid = int(str(note_type_id))
        model = mw.col.models.get(mid)
    except Exception:
        model = None
    if not model:
        try:
            model = mw.col.models.by_name(str(note_type_id))
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


def _get_template_names(note_type_id: str) -> list[str]:
    if mw is None or not getattr(mw, "col", None):
        return []
    try:
        mid = int(str(note_type_id))
        model = mw.col.models.get(mid)
    except Exception:
        model = None
    if not model:
        try:
            model = mw.col.models.by_name(str(note_type_id))
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


def _get_all_field_names() -> list[str]:
    if mw is None or not getattr(mw, "col", None):
        return []
    out: set[str] = set()
    for model in mw.col.models.all():
        fields = model.get("flds", []) if isinstance(model, dict) else []
        for f in fields:
            if isinstance(f, dict):
                name = f.get("name")
            else:
                name = getattr(f, "name", None)
            if name:
                out.add(str(name))
    return sorted(out)


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
            data = item.data(Qt.ItemDataRole.UserRole)
            out.append(str(data) if data is not None else item.text())
    return out


def _checked_labels(model: QStandardItemModel) -> list[str]:
    out: list[str] = []
    for i in range(model.rowCount()):
        item = model.item(i)
        if item and item.checkState() == Qt.CheckState.Checked:
            out.append(item.text())
    return out


def _sync_checkable_combo_text(combo: QComboBox, model: QStandardItemModel) -> None:
    checked = _checked_labels(model)
    if checked:
        text = ", ".join(checked[:3])
        if len(checked) > 3:
            text += f" (+{len(checked) - 3})"
    else:
        text = "<none>"
    if combo.lineEdit() is not None:
        combo.lineEdit().setText(text)


def _make_checkable_combo(items: list[Any], selected: list[str]) -> tuple[QComboBox, QStandardItemModel]:
    combo = QComboBox()
    combo.setEditable(True)
    if combo.lineEdit() is not None:
        combo.lineEdit().setReadOnly(True)
    model = QStandardItemModel(combo)
    selected_set = {str(x) for x in (selected or [])}
    for it in items:
        if isinstance(it, (list, tuple)) and len(it) == 2:
            value = str(it[0])
            label = str(it[1])
        else:
            value = str(it)
            label = str(it)
        item = QStandardItem(label)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        item.setData(value, Qt.ItemDataRole.UserRole)
        item.setData(
            Qt.CheckState.Checked if value in selected_set else Qt.CheckState.Unchecked,
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


def _rebuild_checkable_model(
    combo: QComboBox,
    model: QStandardItemModel,
    items: list[Any],
    selected: list[str],
) -> None:
    model.clear()
    selected_set = {str(x) for x in (selected or [])}
    for it in items:
        if isinstance(it, (list, tuple)) and len(it) == 2:
            value = str(it[0])
            label = str(it[1])
        else:
            value = str(it)
            label = str(it)
        item = QStandardItem(label)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        item.setData(value, Qt.ItemDataRole.UserRole)
        item.setData(
            Qt.CheckState.Checked if value in selected_set else Qt.CheckState.Unchecked,
            Qt.ItemDataRole.CheckStateRole,
        )
        model.appendRow(item)
    _sync_checkable_combo_text(combo, model)


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


def _populate_note_type_combo(combo: QComboBox, note_type_items: list[tuple[str, str]], current_value: str) -> None:
    combo.setEditable(False)
    combo.addItem("<none>", "")
    for note_type_id, name in note_type_items:
        combo.addItem(name, str(note_type_id))
    cur = (current_value or "").strip()
    if cur:
        idx = combo.findData(cur)
        if idx == -1:
            combo.addItem(f"<missing {cur}>", cur)
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

    family_note_type_items = _merge_note_type_items(
        _get_note_type_items(), list((config.FAMILY_NOTE_TYPES or {}).keys())
    )
    family_note_type_combo, family_note_type_model = _make_checkable_combo(
        family_note_type_items, list((config.FAMILY_NOTE_TYPES or {}).keys())
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
    for nt_id, nt_cfg in (config.FAMILY_NOTE_TYPES or {}).items():
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
        family_state[str(nt_id)] = out_stages

    family_note_type_widgets: dict[str, list[dict[str, Any]]] = {}

    def _capture_family_state() -> None:
        for nt_id, stages in family_note_type_widgets.items():
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
            family_state[nt_id] = out

    def _clear_family_layout() -> None:
        while family_stages_container_layout.count():
            item = family_stages_container_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    def _add_family_stage(nt_id: str) -> None:
        _capture_family_state()
        family_state.setdefault(nt_id, []).append(
            {"templates": [], "threshold": float(config.STABILITY_DEFAULT_THRESHOLD)}
        )
        _refresh_family_stages(capture=False)

    def _remove_family_stage(nt_id: str, idx: int) -> None:
        _capture_family_state()
        stages = family_state.get(nt_id, [])
        if 0 <= idx < len(stages):
            del stages[idx]
        family_state[nt_id] = stages
        _refresh_family_stages(capture=False)

    def _refresh_family_stages(*, capture: bool = True) -> None:
        if capture:
            _capture_family_state()
        _clear_family_layout()
        family_note_type_widgets.clear()

        selected_types = _checked_items(family_note_type_model)
        for nt_id in selected_types:
            stages = family_state.get(nt_id, [])
            family_note_type_widgets[nt_id] = []

            group = QGroupBox(_note_type_label(nt_id))
            group_layout = QVBoxLayout()
            group.setLayout(group_layout)

            add_btn = QPushButton("Add stage")
            add_btn.clicked.connect(lambda _=None, n=nt_id: _add_family_stage(n))
            group_layout.addWidget(add_btn)

            all_templates = set(_get_template_names(nt_id))
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
                remove_btn.clicked.connect(lambda _=None, n=nt_id, i=idx: _remove_family_stage(n, i))
                stage_form.addRow(remove_btn)

                group_layout.addWidget(stage_box)
                family_note_type_widgets[nt_id].append(
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

    kanji_tab = QWidget()
    kanji_layout = QVBoxLayout()
    kanji_tab.setLayout(kanji_layout)
    kanji_form = QFormLayout()
    kanji_layout.addLayout(kanji_form)

    kanji_enabled_cb = QCheckBox()
    kanji_enabled_cb.setChecked(config.KANJI_GATE_ENABLED)
    kanji_form.addRow("Enabled", kanji_enabled_cb)

    behavior_combo = QComboBox()
    behavior_combo.addItem("Kanji Only", "kanji_only")
    behavior_combo.addItem("Kanji then Components", "kanji_then_components")
    behavior_combo.addItem("Components then Kanji", "components_then_kanji")
    behavior_combo.addItem("Kanji and Components", "kanji_and_components")
    behavior_idx = behavior_combo.findData(config.KANJI_GATE_BEHAVIOR)
    if behavior_idx < 0:
        behavior_idx = 0
    behavior_combo.setCurrentIndex(behavior_idx)
    kanji_form.addRow("Behavior", behavior_combo)

    kanji_agg_combo = QComboBox()
    agg_opts = ["min", "max", "avg"]
    kanji_agg_combo.addItems(agg_opts)
    agg_index = (
        agg_opts.index(config.KANJI_GATE_STABILITY_AGG)
        if config.KANJI_GATE_STABILITY_AGG in agg_opts
        else 0
    )
    kanji_agg_combo.setCurrentIndex(agg_index)
    kanji_form.addRow("Stability aggregation", kanji_agg_combo)

    kanji_note_type_items = _merge_note_type_items(
        _get_note_type_items(),
        [config.KANJI_GATE_KANJI_NOTE_TYPE, config.KANJI_GATE_RADICAL_NOTE_TYPE],
    )

    kanji_note_type_combo = QComboBox()
    _populate_note_type_combo(
        kanji_note_type_combo, kanji_note_type_items, config.KANJI_GATE_KANJI_NOTE_TYPE
    )
    kanji_form.addRow("Kanji note type", kanji_note_type_combo)

    kanji_field_combo = QComboBox()
    _populate_field_combo(
        kanji_field_combo,
        _get_fields_for_note_type(config.KANJI_GATE_KANJI_NOTE_TYPE),
        config.KANJI_GATE_KANJI_FIELD,
    )
    kanji_form.addRow("Kanji field", kanji_field_combo)

    kanji_alt_field_combo = QComboBox()
    _populate_field_combo(
        kanji_alt_field_combo,
        _get_fields_for_note_type(config.KANJI_GATE_KANJI_NOTE_TYPE),
        config.KANJI_GATE_KANJI_ALT_FIELD,
    )
    kanji_form.addRow("Kanji alt field", kanji_alt_field_combo)

    components_field_label = QLabel("Components field")
    kanji_components_field_combo = QComboBox()
    _populate_field_combo(
        kanji_components_field_combo,
        _get_fields_for_note_type(config.KANJI_GATE_KANJI_NOTE_TYPE),
        config.KANJI_GATE_COMPONENTS_FIELD,
    )
    kanji_form.addRow(components_field_label, kanji_components_field_combo)

    kanji_radical_field_label = QLabel("Kanji radical field")
    kanji_radical_field_combo = QComboBox()
    _populate_field_combo(
        kanji_radical_field_combo,
        _get_fields_for_note_type(config.KANJI_GATE_KANJI_NOTE_TYPE),
        config.KANJI_GATE_KANJI_RADICAL_FIELD,
    )
    kanji_form.addRow(kanji_radical_field_label, kanji_radical_field_combo)

    radical_note_type_label = QLabel("Radical note type")
    radical_note_type_combo = QComboBox()
    _populate_note_type_combo(
        radical_note_type_combo, kanji_note_type_items, config.KANJI_GATE_RADICAL_NOTE_TYPE
    )
    kanji_form.addRow(radical_note_type_label, radical_note_type_combo)

    radical_field_label = QLabel("Radical field")
    radical_field_combo = QComboBox()
    _populate_field_combo(
        radical_field_combo,
        _get_fields_for_note_type(config.KANJI_GATE_RADICAL_NOTE_TYPE),
        config.KANJI_GATE_RADICAL_FIELD,
    )
    kanji_form.addRow(radical_field_label, radical_field_combo)

    kanji_threshold_label = QLabel("Kanji threshold")
    kanji_threshold_spin = QDoubleSpinBox()
    kanji_threshold_spin.setDecimals(2)
    kanji_threshold_spin.setRange(0, 100000)
    kanji_threshold_spin.setValue(float(config.KANJI_GATE_KANJI_THRESHOLD))
    kanji_form.addRow(kanji_threshold_label, kanji_threshold_spin)

    component_threshold_label = QLabel("Component threshold")
    component_threshold_spin = QDoubleSpinBox()
    component_threshold_spin.setDecimals(2)
    component_threshold_spin.setRange(0, 100000)
    component_threshold_spin.setValue(float(config.KANJI_GATE_COMPONENT_THRESHOLD))
    kanji_form.addRow(component_threshold_label, component_threshold_spin)

    vocab_note_type_items = _merge_note_type_items(
        _get_note_type_items(), list((config.KANJI_GATE_VOCAB_NOTE_TYPES or {}).keys())
    )
    kanji_vocab_note_type_combo, kanji_vocab_note_type_model = _make_checkable_combo(
        vocab_note_type_items, list((config.KANJI_GATE_VOCAB_NOTE_TYPES or {}).keys())
    )
    kanji_form.addRow("Vocab note types", kanji_vocab_note_type_combo)

    vocab_group = QGroupBox("Vocab note type config")
    vocab_group_layout = QVBoxLayout()
    vocab_group.setLayout(vocab_group_layout)

    vocab_scroll = QScrollArea()
    vocab_scroll.setWidgetResizable(True)
    vocab_container = QWidget()
    vocab_container_layout = QVBoxLayout()
    vocab_container.setLayout(vocab_container_layout)
    vocab_scroll.setWidget(vocab_container)
    vocab_group_layout.addWidget(vocab_scroll)
    kanji_layout.addWidget(vocab_group)

    kanji_vocab_state: dict[str, dict[str, Any]] = {}
    for nt_id, nt_cfg in (config.KANJI_GATE_VOCAB_NOTE_TYPES or {}).items():
        if not isinstance(nt_cfg, dict):
            continue
        kanji_vocab_state[str(nt_id)] = {
            "furigana_field": str(nt_cfg.get("furigana_field", "")).strip(),
            "base_templates": [str(x) for x in (nt_cfg.get("base_templates") or [])],
            "kanji_templates": [str(x) for x in (nt_cfg.get("kanji_templates") or [])],
            "base_threshold": float(
                nt_cfg.get("base_threshold", config.STABILITY_DEFAULT_THRESHOLD)
            ),
        }

    kanji_vocab_widgets: dict[str, dict[str, Any]] = {}

    def _clear_kanji_vocab_layout() -> None:
        while vocab_container_layout.count():
            item = vocab_container_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    def _capture_kanji_vocab_state() -> None:
        for nt_id, widgets in kanji_vocab_widgets.items():
            kanji_vocab_state[nt_id] = {
                "furigana_field": _combo_value(widgets["furigana_combo"]),
                "base_templates": _checked_items(widgets["base_templates_model"]),
                "kanji_templates": _checked_items(widgets["kanji_templates_model"]),
                "base_threshold": float(widgets["base_threshold_spin"].value()),
            }

    def _refresh_kanji_vocab_config() -> None:
        _capture_kanji_vocab_state()
        _clear_kanji_vocab_layout()
        kanji_vocab_widgets.clear()

        selected_types = _checked_items(kanji_vocab_note_type_model)
        for nt_id in selected_types:
            cfg = kanji_vocab_state.get(nt_id, {})
            field_names = _get_fields_for_note_type(nt_id)

            vocab_furigana_combo = QComboBox()
            _populate_field_combo(
                vocab_furigana_combo,
                field_names,
                cfg.get("furigana_field", ""),
            )

            template_names = sorted(
                set(_get_template_names(nt_id))
                | set(cfg.get("base_templates", []) or [])
                | set(cfg.get("kanji_templates", []) or [])
            )
            base_templates_combo, base_templates_model = _make_checkable_combo(
                template_names, list(cfg.get("base_templates", []) or [])
            )
            kanji_templates_combo, kanji_templates_model = _make_checkable_combo(
                template_names, list(cfg.get("kanji_templates", []) or [])
            )

            base_threshold_spin = QDoubleSpinBox()
            base_threshold_spin.setDecimals(2)
            base_threshold_spin.setRange(0, 100000)
            base_threshold_spin.setValue(
                float(cfg.get("base_threshold", config.STABILITY_DEFAULT_THRESHOLD))
            )

            group = QGroupBox(_note_type_label(nt_id))
            group_form = QFormLayout()
            group_form.addRow("Vocab furigana field", vocab_furigana_combo)
            group_form.addRow("Vocab base templates (Grundform)", base_templates_combo)
            group_form.addRow("Vocab kanjiform templates", kanji_templates_combo)
            group_form.addRow("Base threshold", base_threshold_spin)
            group.setLayout(group_form)

            vocab_container_layout.addWidget(group)
            kanji_vocab_widgets[nt_id] = {
                "furigana_combo": vocab_furigana_combo,
                "base_templates_model": base_templates_model,
                "kanji_templates_model": kanji_templates_model,
                "base_threshold_spin": base_threshold_spin,
            }

        vocab_container_layout.addStretch(1)

    def _refresh_kanji_note_fields() -> None:
        nt_name = _combo_value(kanji_note_type_combo)
        cur_kanji = _combo_value(kanji_field_combo)
        cur_alt = _combo_value(kanji_alt_field_combo)
        cur_comps = _combo_value(kanji_components_field_combo)
        cur_rad = _combo_value(kanji_radical_field_combo)
        fields = _get_fields_for_note_type(nt_name)
        kanji_field_combo.clear()
        kanji_alt_field_combo.clear()
        kanji_components_field_combo.clear()
        kanji_radical_field_combo.clear()
        _populate_field_combo(kanji_field_combo, fields, cur_kanji)
        _populate_field_combo(kanji_alt_field_combo, fields, cur_alt)
        _populate_field_combo(kanji_components_field_combo, fields, cur_comps)
        _populate_field_combo(kanji_radical_field_combo, fields, cur_rad)

    def _refresh_radical_fields() -> None:
        nt_name = _combo_value(radical_note_type_combo)
        cur_val = _combo_value(radical_field_combo)
        radical_field_combo.clear()
        _populate_field_combo(radical_field_combo, _get_fields_for_note_type(nt_name), cur_val)

    def _set_row_visible(label: QLabel, widget: QWidget, visible: bool) -> None:
        label.setVisible(visible)
        widget.setVisible(visible)

    def _refresh_kanji_mode_ui() -> None:
        mode = _combo_value(behavior_combo)
        use_components = mode in (
            "kanji_then_components",
            "components_then_kanji",
            "kanji_and_components",
        )
        _set_row_visible(components_field_label, kanji_components_field_combo, use_components)
        _set_row_visible(kanji_radical_field_label, kanji_radical_field_combo, use_components)
        _set_row_visible(radical_note_type_label, radical_note_type_combo, use_components)
        _set_row_visible(radical_field_label, radical_field_combo, use_components)
        _set_row_visible(kanji_threshold_label, kanji_threshold_spin, mode == "kanji_then_components")
        _set_row_visible(
            component_threshold_label, component_threshold_spin, mode == "components_then_kanji"
        )

    kanji_note_type_combo.currentIndexChanged.connect(lambda _=None: _refresh_kanji_note_fields())
    radical_note_type_combo.currentIndexChanged.connect(lambda _=None: _refresh_radical_fields())
    behavior_combo.currentIndexChanged.connect(lambda _=None: _refresh_kanji_mode_ui())
    kanji_vocab_note_type_model.itemChanged.connect(lambda _item: _refresh_kanji_vocab_config())

    _refresh_kanji_vocab_config()
    _refresh_kanji_mode_ui()

    tabs.addTab(kanji_tab, "Kanji Gate")

    jlpt_tab = QWidget()
    jlpt_layout = QVBoxLayout()
    jlpt_tab.setLayout(jlpt_layout)
    jlpt_form = QFormLayout()
    jlpt_layout.addLayout(jlpt_form)

    jlpt_deck_combo, jlpt_deck_model = _make_checkable_combo(
        deck_names, list(config.JLPT_TAGGER_DECKS or [])
    )
    jlpt_form.addRow("Decks", jlpt_deck_combo)

    note_type_items = _merge_note_type_items(
        _get_note_type_items(),
        list((config.JLPT_TAGGER_NOTE_TYPES or [])) + list((config.FAMILY_NOTE_TYPES or {}).keys()),
    )
    jlpt_note_type_combo, jlpt_note_type_model = _make_checkable_combo(
        note_type_items, list(config.JLPT_TAGGER_NOTE_TYPES or [])
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
        for nt_id, widgets in note_type_fields_widgets.items():
            vocab_combo, reading_combo = widgets
            fields_state[nt_id] = {
                "vocab_field": _combo_value(vocab_combo),
                "reading_field": _combo_value(reading_combo),
            }

    def _refresh_note_type_fields() -> None:
        _capture_fields_state()
        _clear_layout(fields_container_layout)
        note_type_fields_widgets.clear()

        selected_types = _checked_items(jlpt_note_type_model)
        for nt_id in selected_types:
            field_names = _get_fields_for_note_type(nt_id)
            cfg_fields = fields_state.get(nt_id, {})
            vocab_combo = QComboBox()
            reading_combo = QComboBox()
            _populate_field_combo(vocab_combo, field_names, cfg_fields.get("vocab_field", ""))
            _populate_field_combo(reading_combo, field_names, cfg_fields.get("reading_field", ""))

            group = QGroupBox(_note_type_label(nt_id))
            group_form = QFormLayout()
            group_form.addRow("Vocab field", vocab_combo)
            group_form.addRow("Reading field", reading_combo)
            group.setLayout(group_form)

            fields_container_layout.addWidget(group)
            note_type_fields_widgets[nt_id] = (vocab_combo, reading_combo)

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

    card_sorter_note_type_items = _merge_note_type_items(
        _get_note_type_items(), list((config.CARD_SORTER_NOTE_TYPES or {}).keys())
    )
    card_sorter_note_type_combo, card_sorter_note_type_model = _make_checkable_combo(
        card_sorter_note_type_items, list((config.CARD_SORTER_NOTE_TYPES or {}).keys())
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
    for nt_id, nt_cfg in (config.CARD_SORTER_NOTE_TYPES or {}).items():
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
        card_sorter_state[str(nt_id)] = {
            "mode": mode,
            "default_deck": default_deck,
            "by_template": by_template,
        }

    card_sorter_note_type_widgets: dict[str, dict[str, Any]] = {}

    def _capture_card_sorter_state() -> None:
        for nt_id, widgets in card_sorter_note_type_widgets.items():
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
            card_sorter_state[nt_id] = {
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
        for nt_id in selected_types:
            cfg = card_sorter_state.get(nt_id)
            if not cfg:
                cfg = {"mode": "by_template", "default_deck": "", "by_template": {}}
                card_sorter_state[nt_id] = cfg

            group = QGroupBox(_note_type_label(nt_id))
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
            template_names = sorted(set(_get_template_names(nt_id)) | set(by_template.keys()))
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
            card_sorter_note_type_widgets[nt_id] = {
                "mode_combo": mode_combo,
                "default_deck_combo": default_deck_combo,
                "template_combos": template_combos,
            }

        card_sorter_rules_container_layout.addStretch(1)

    _refresh_card_sorter_rules()
    card_sorter_note_type_model.itemChanged.connect(lambda _item: _refresh_card_sorter_rules())

    tabs.addTab(card_sorter_tab, "Card Sorter")

    note_linker_tab = QWidget()
    note_linker_layout = QVBoxLayout()
    note_linker_tab.setLayout(note_linker_layout)
    note_linker_form = QFormLayout()
    note_linker_layout.addLayout(note_linker_form)

    note_linker_enabled_cb = QCheckBox()
    note_linker_enabled_cb.setChecked(config.NOTE_LINKER_ENABLED)
    note_linker_form.addRow("Auto links enabled", note_linker_enabled_cb)

    copy_label_field_combo = QComboBox()
    all_fields = _get_all_field_names()
    cur_copy_label = str(config.NOTE_LINKER_COPY_LABEL_FIELD or "").strip()
    if cur_copy_label and cur_copy_label not in all_fields:
        all_fields.append(cur_copy_label)
    _populate_field_combo(copy_label_field_combo, all_fields, cur_copy_label)
    note_linker_form.addRow("Copy label field", copy_label_field_combo)

    note_linker_note_type_items = _merge_note_type_items(
        _get_note_type_items(), list((config.NOTE_LINKER_RULES or {}).keys())
    )
    note_linker_note_type_combo, note_linker_note_type_model = _make_checkable_combo(
        note_linker_note_type_items, list((config.NOTE_LINKER_RULES or {}).keys())
    )
    note_linker_form.addRow("Note types", note_linker_note_type_combo)

    note_linker_rules_group = QGroupBox("Rules per note type")
    note_linker_rules_layout = QVBoxLayout()
    note_linker_rules_group.setLayout(note_linker_rules_layout)
    note_linker_layout.addWidget(note_linker_rules_group)

    note_linker_rules_scroll = QScrollArea()
    note_linker_rules_scroll.setWidgetResizable(True)
    note_linker_rules_container = QWidget()
    note_linker_rules_container_layout = QVBoxLayout()
    note_linker_rules_container.setLayout(note_linker_rules_container_layout)
    note_linker_rules_scroll.setWidget(note_linker_rules_container)
    note_linker_rules_layout.addWidget(note_linker_rules_scroll)

    note_linker_state: dict[str, dict[str, Any]] = {}
    for nt_id, nt_cfg in (config.NOTE_LINKER_RULES or {}).items():
        if isinstance(nt_cfg, dict):
            note_linker_state[str(nt_id)] = {
                "target_field": str(nt_cfg.get("target_field", "")).strip(),
                "templates": [str(x) for x in (nt_cfg.get("templates") or [])],
                "side": str(nt_cfg.get("side", "both")).lower().strip() or "both",
                "tag": str(nt_cfg.get("tag", "")).strip(),
                "label_field": str(nt_cfg.get("label_field", "")).strip(),
            }

    note_linker_note_type_widgets: dict[str, dict[str, Any]] = {}

    def _capture_note_linker_state() -> None:
        for nt_id, widgets in note_linker_note_type_widgets.items():
            note_linker_state[nt_id] = {
                "target_field": _combo_value(widgets["target_field_combo"]),
                "templates": _checked_items(widgets["templates_model"]),
                "side": _combo_value(widgets["side_combo"]),
                "tag": widgets["tag_edit"].text().strip(),
                "label_field": _combo_value(widgets["label_field_combo"]),
            }

    def _clear_note_linker_layout() -> None:
        while note_linker_rules_container_layout.count():
            item = note_linker_rules_container_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    def _refresh_note_linker_rules() -> None:
        _capture_note_linker_state()
        _clear_note_linker_layout()
        note_linker_note_type_widgets.clear()

        selected_types = _checked_items(note_linker_note_type_model)
        for nt_id in selected_types:
            cfg = note_linker_state.get(nt_id)
            if not cfg:
                cfg = {
                    "target_field": "",
                    "templates": [],
                    "side": "both",
                    "tag": "",
                    "label_field": "",
                }
                note_linker_state[nt_id] = cfg

            group = QGroupBox(_note_type_label(nt_id))
            group_layout = QVBoxLayout()
            group.setLayout(group_layout)

            form = QFormLayout()
            group_layout.addLayout(form)

            field_names = list(_get_fields_for_note_type(nt_id))
            for extra in (cfg.get("target_field", ""), cfg.get("label_field", "")):
                if extra and extra not in field_names:
                    field_names.append(extra)
            field_names = sorted(set(field_names))

            target_field_combo = QComboBox()
            _populate_field_combo(target_field_combo, field_names, cfg.get("target_field", ""))
            form.addRow("Target field", target_field_combo)

            label_field_combo = QComboBox()
            _populate_field_combo(label_field_combo, field_names, cfg.get("label_field", ""))
            form.addRow("Label field", label_field_combo)

            template_names = sorted(
                set(_get_template_names(nt_id)) | set(cfg.get("templates", []) or [])
            )
            templates_combo, templates_model = _make_checkable_combo(
                template_names, list(cfg.get("templates", []) or [])
            )
            form.addRow("Templates", templates_combo)

            side_combo = QComboBox()
            side_combo.addItem("Front", "front")
            side_combo.addItem("Back", "back")
            side_combo.addItem("Both", "both")
            side_val = str(cfg.get("side", "both")).lower().strip()
            side_idx = side_combo.findData(side_val)
            if side_idx < 0:
                side_idx = side_combo.findData("both")
            if side_idx < 0:
                side_idx = 0
            side_combo.setCurrentIndex(side_idx)
            form.addRow("Side", side_combo)

            tag_edit = QLineEdit()
            tag_edit.setText(str(cfg.get("tag", "") or ""))
            form.addRow("Tag", tag_edit)

            note_linker_rules_container_layout.addWidget(group)
            note_linker_note_type_widgets[nt_id] = {
                "target_field_combo": target_field_combo,
                "label_field_combo": label_field_combo,
                "templates_model": templates_model,
                "side_combo": side_combo,
                "tag_edit": tag_edit,
            }

        note_linker_rules_container_layout.addStretch(1)

    _refresh_note_linker_rules()
    note_linker_note_type_model.itemChanged.connect(lambda _item: _refresh_note_linker_rules())

    tabs.addTab(note_linker_tab, "Auto NoteLinks")

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

    tabs.addTab(info_tab, "Info")

    def _sync_installer_buttons() -> None:
        has_pkg = bool(menu._notetypes_package_path())
        install_btn.setEnabled(has_pkg and not config.NOTETYPES_INSTALLED)
        install_btn.setVisible(not config.NOTETYPES_INSTALLED)

    _sync_installer_buttons()

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

        kanji_behavior = _combo_value(behavior_combo) or "kanji_only"
        kanji_stab_agg = _combo_value(kanji_agg_combo) or "min"
        kanji_note_type = _combo_value(kanji_note_type_combo)
        kanji_field = _combo_value(kanji_field_combo)
        kanji_alt_field = _combo_value(kanji_alt_field_combo)
        kanji_components_field = _combo_value(kanji_components_field_combo)
        kanji_kanji_radical_field = _combo_value(kanji_radical_field_combo)
        kanji_radical_note_type = _combo_value(radical_note_type_combo)
        kanji_radical_field = _combo_value(radical_field_combo)
        kanji_threshold = float(kanji_threshold_spin.value())
        component_threshold = float(component_threshold_spin.value())

        _capture_kanji_vocab_state()
        kanji_vocab_note_types = _checked_items(kanji_vocab_note_type_model)
        kanji_vocab_cfg: dict[str, dict[str, Any]] = {}

        if kanji_enabled_cb.isChecked():
            if kanji_behavior not in (
                "kanji_only",
                "kanji_then_components",
                "components_then_kanji",
                "kanji_and_components",
            ):
                errors.append("Kanji Gate: behavior invalid.")
            if kanji_stab_agg not in ("min", "max", "avg"):
                errors.append("Kanji Gate: stability aggregation invalid.")
            if not kanji_note_type:
                errors.append("Kanji Gate: kanji note type missing.")
            if not kanji_field:
                errors.append("Kanji Gate: kanji field missing.")
            if not kanji_vocab_note_types:
                errors.append("Kanji Gate: vocab note types missing.")

            uses_components = kanji_behavior in (
                "kanji_then_components",
                "components_then_kanji",
                "kanji_and_components",
            )
            if uses_components and not kanji_components_field:
                errors.append("Kanji Gate: components field missing.")

            has_any_radical_cfg = bool(
                kanji_kanji_radical_field or kanji_radical_note_type or kanji_radical_field
            )
            if uses_components and has_any_radical_cfg:
                if not kanji_kanji_radical_field:
                    errors.append("Kanji Gate: kanji radical field missing.")
                if not kanji_radical_note_type:
                    errors.append("Kanji Gate: radical note type missing.")
                if not kanji_radical_field:
                    errors.append("Kanji Gate: radical field missing.")

        for nt_id in kanji_vocab_note_types:
            cfg_state = kanji_vocab_state.get(nt_id, {})
            furigana_field = str(cfg_state.get("furigana_field", "")).strip()
            base_templates = [
                str(x).strip() for x in (cfg_state.get("base_templates") or []) if str(x).strip()
            ]
            kanji_templates = [
                str(x).strip() for x in (cfg_state.get("kanji_templates") or []) if str(x).strip()
            ]
            base_threshold = float(
                cfg_state.get("base_threshold", config.STABILITY_DEFAULT_THRESHOLD)
            )

            kanji_vocab_cfg[nt_id] = {
                "furigana_field": furigana_field,
                "base_templates": base_templates,
                "kanji_templates": kanji_templates,
                "base_threshold": base_threshold,
            }

            if kanji_enabled_cb.isChecked():
                if not furigana_field:
                    errors.append(
                        f"Kanji Gate: vocab field missing for note type: {_note_type_label(nt_id)}"
                    )
                if not base_templates:
                    errors.append(
                        f"Kanji Gate: base templates missing for note type: {_note_type_label(nt_id)}"
                    )
                if not kanji_templates:
                    errors.append(
                        f"Kanji Gate: kanjiform templates missing for note type: {_note_type_label(nt_id)}"
                    )

        _capture_family_state()
        family_note_types = _checked_items(family_note_type_model)
        family_note_types_cfg: dict[str, Any] = {}
        for nt_id in family_note_types:
            stages = family_state.get(nt_id, [])
            if not stages:
                errors.append(
                    f"Family Gate: no stages defined for note type: {_note_type_label(nt_id)}"
                )
                continue
            stage_cfgs: list[dict[str, Any]] = []
            for s_idx, st in enumerate(stages):
                tmpls = [str(x) for x in (st.get("templates") or []) if str(x)]
                if not tmpls:
                    errors.append(
                        f"Family Gate: stage {s_idx} has no templates ({_note_type_label(nt_id)})"
                    )
                    continue
                thr = float(st.get("threshold", config.STABILITY_DEFAULT_THRESHOLD))
                stage_cfgs.append({"templates": tmpls, "threshold": thr})
            if stage_cfgs:
                family_note_types_cfg[nt_id] = {"stages": stage_cfgs}

        watch_nids, bad_tokens = _parse_watch_nids(watch_nids_edit.toPlainText())
        if bad_tokens:
            errors.append("Watch NIDs invalid: " + ", ".join(bad_tokens))

        _capture_fields_state()
        jlpt_decks = _checked_items(jlpt_deck_model)
        jlpt_note_types = _checked_items(jlpt_note_type_model)
        jlpt_fields: dict[str, dict[str, str]] = dict(fields_state)

        for nt_id in jlpt_note_types:
            cfg_fields = jlpt_fields.get(nt_id, {})
            vocab_field = str(cfg_fields.get("vocab_field", "")).strip()
            reading_field = str(cfg_fields.get("reading_field", "")).strip()
            if not vocab_field or not reading_field:
                errors.append(
                    f"JLPT fields missing for note type: {_note_type_label(nt_id)}"
                )
            else:
                jlpt_fields[nt_id] = {
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
        for nt_id in card_sorter_note_types:
            cfg_state = card_sorter_state.get(nt_id, {})
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
                    errors.append(
                        f"Card Sorter: default deck missing for note type: {_note_type_label(nt_id)}"
                    )
                    continue
                card_sorter_cfg[nt_id] = {"mode": "all", "default_deck": default_deck}
            else:
                if not by_template:
                    errors.append(
                        f"Card Sorter: no template mapping for note type: {_note_type_label(nt_id)}"
                    )
                    continue
                payload = {"mode": "by_template", "by_template": by_template}
                if default_deck:
                    payload["default_deck"] = default_deck
                card_sorter_cfg[nt_id] = payload

        card_sorter_exclude_decks = _checked_items(card_sorter_exclude_decks_model)
        card_sorter_exclude_tags = _parse_list_entries(card_sorter_exclude_tags_edit.toPlainText())

        _capture_note_linker_state()
        note_linker_note_types = _checked_items(note_linker_note_type_model)
        note_linker_rules_cfg: dict[str, Any] = {}
        for nt_id in note_linker_note_types:
            cfg_state = note_linker_state.get(nt_id, {})
            target_field = str(cfg_state.get("target_field", "")).strip()
            templates = [
                str(x).strip() for x in (cfg_state.get("templates") or []) if str(x).strip()
            ]
            side = str(cfg_state.get("side", "both")).lower().strip() or "both"
            tag = str(cfg_state.get("tag", "")).strip()
            label_field = str(cfg_state.get("label_field", "")).strip()

            if note_linker_enabled_cb.isChecked():
                if not target_field:
                    errors.append(
                        f"Note Linker: target field missing for note type: {_note_type_label(nt_id)}"
                    )
                if not tag:
                    errors.append(
                        f"Note Linker: tag missing for note type: {_note_type_label(nt_id)}"
                    )
                if side not in ("front", "back", "both"):
                    errors.append(
                        f"Note Linker: side invalid for note type: {_note_type_label(nt_id)}"
                    )

            payload: dict[str, Any] = {}
            if target_field:
                payload["target_field"] = target_field
            if templates:
                payload["templates"] = templates
            if side:
                payload["side"] = side
            if tag:
                payload["tag"] = tag
            if label_field:
                payload["label_field"] = label_field
            if payload:
                note_linker_rules_cfg[nt_id] = payload

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

        config._cfg_set(cfg, "kanji_gate.enabled", bool(kanji_enabled_cb.isChecked()))
        config._cfg_set(cfg, "kanji_gate.behavior", kanji_behavior)
        config._cfg_set(cfg, "kanji_gate.stability_aggregation", kanji_stab_agg)
        config._cfg_set(cfg, "kanji_gate.kanji_note_type", kanji_note_type)
        config._cfg_set(cfg, "kanji_gate.kanji_field", kanji_field)
        config._cfg_set(cfg, "kanji_gate.kanji_alt_field", kanji_alt_field)
        config._cfg_set(cfg, "kanji_gate.components_field", kanji_components_field)
        config._cfg_set(cfg, "kanji_gate.kanji_radical_field", kanji_kanji_radical_field)
        config._cfg_set(cfg, "kanji_gate.radical_note_type", kanji_radical_note_type)
        config._cfg_set(cfg, "kanji_gate.radical_field", kanji_radical_field)
        config._cfg_set(cfg, "kanji_gate.kanji_threshold", float(kanji_threshold))
        config._cfg_set(cfg, "kanji_gate.component_threshold", float(component_threshold))
        config._cfg_set(cfg, "kanji_gate.vocab_note_types", kanji_vocab_cfg)

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

        config._cfg_set(cfg, "note_linker.enabled", bool(note_linker_enabled_cb.isChecked()))
        config._cfg_set(
            cfg,
            "note_linker.copy_label_field",
            str(_combo_value(copy_label_field_combo) or "").strip(),
        )
        config._cfg_set(cfg, "note_linker.rules", note_linker_rules_cfg)

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

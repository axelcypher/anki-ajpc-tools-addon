from __future__ import annotations

import json
import os
import time
from typing import Any

from anki.cards import Card
from aqt import gui_hooks, mw
from aqt.qt import (
    QAction,
    QApplication,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QStandardItem,
    QStandardItemModel,
    QTabWidget,
    Qt,
    QVBoxLayout,
    QWidget,
)
from aqt.utils import tooltip

from .. import logging as core_logging
from . import ModuleSpec
from .link_core import LinkPayload, LinkRef, ProviderContext, WrapperSpec

ADDON_DIR = os.path.dirname(os.path.dirname(__file__))
CONFIG_PATH = os.path.join(ADDON_DIR, "config.json")

CFG: dict[str, Any] = {}
DEBUG = False
MASS_LINKER_ENABLED = True
MASS_LINKER_RULES: dict[str, Any] = {}
MASS_LINKER_LABEL_FIELD = ""


def _load_config() -> dict[str, Any]:
    if not os.path.exists(CONFIG_PATH):
        return {}
    with open(CONFIG_PATH, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def cfg_get(path: str, default: Any = None) -> Any:
    cur: Any = CFG
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return default
        cur = cur[part]
    return cur


def _cfg_set(cfg: dict[str, Any], path: str, value: Any) -> None:
    cur: dict[str, Any] = cfg
    parts = path.split(".")
    for part in parts[:-1]:
        nxt = cur.get(part)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[part] = nxt
        cur = nxt
    cur[parts[-1]] = value


def reload_config() -> None:
    global CFG, DEBUG
    global MASS_LINKER_ENABLED, MASS_LINKER_RULES, MASS_LINKER_LABEL_FIELD

    CFG = _load_config()

    _dbg = CFG.get("debug", {})
    if isinstance(_dbg, dict):
        DEBUG = bool(_dbg.get("enabled", False))
    else:
        DEBUG = bool(_dbg)

    MASS_LINKER_ENABLED = bool(cfg_get("mass_linker.enabled", True))
    MASS_LINKER_RULES = cfg_get("mass_linker.rules", {}) or {}
    MASS_LINKER_LABEL_FIELD = str(
        cfg_get("mass_linker.label_field", cfg_get("mass_linker.copy_label_field", ""))
    ).strip()

    try:
        from aqt import mw  # type: ignore
    except Exception:
        mw = None  # type: ignore

    def _note_type_id_from_ident(col, ident: Any) -> str:
        if ident is None:
            return ""
        s = str(ident).strip()
        if not s:
            return ""
        if s.isdigit():
            try:
                mid = int(s)
            except Exception:
                return ""
            return str(mid)
        try:
            model = col.models.by_name(s)
        except Exception:
            model = None
        if not model:
            return s
        try:
            return str(int(model.get("id")))
        except Exception:
            return s

    def _map_dict_keys(col, raw: dict[str, Any]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for k, v in raw.items():
            key = _note_type_id_from_ident(col, k)
            if not key:
                continue
            out[key] = v
        return out

    if mw is not None and getattr(mw, "col", None):
        col = mw.col
        if col:
            MASS_LINKER_RULES = _map_dict_keys(col, MASS_LINKER_RULES)


reload_config()


class _ConfigProxy:
    def __getattr__(self, name: str):
        if name in globals():
            return globals()[name]
        raise AttributeError(name)

    def __setattr__(self, name: str, value: Any) -> None:
        globals()[name] = value

    def reload_config(self) -> None:
        reload_config()

    def _cfg_set(self, cfg: dict[str, Any], path: str, value: Any) -> None:
        _cfg_set(cfg, path, value)


config = _ConfigProxy()


DEBUG_LOG_PATH = os.path.join(ADDON_DIR, "ajpc_debug.log")


def dbg(*a: Any) -> None:
    core_logging.trace(*a, source="mass_linker")


def log_info(*a: Any) -> None:
    core_logging.info(*a, source="mass_linker")


def log_warn(*a: Any) -> None:
    core_logging.warn(*a, source="mass_linker")


def log_error(*a: Any) -> None:
    core_logging.error(*a, source="mass_linker")


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


def _get_sort_field_for_note_type(note_type_id: str) -> str:
    if mw is None or not getattr(mw, "col", None):
        return ""
    try:
        mid = int(str(note_type_id))
        model = mw.col.models.get(mid)
    except Exception:
        model = None
    if not model or not isinstance(model, dict):
        return ""
    try:
        sortf = int(model.get("sortf", 0))
    except Exception:
        sortf = 0
    fields = model.get("flds", []) or []
    if sortf < 0 or sortf >= len(fields):
        sortf = 0
    if not fields:
        return ""
    fld = fields[sortf]
    if isinstance(fld, dict):
        return str(fld.get("name") or "").strip()
    return str(getattr(fld, "name", "") or "").strip()


def _get_template_items(note_type_id: str) -> list[tuple[str, str]]:
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
    out: list[tuple[str, str]] = []
    for i, t in enumerate(tmpls):
        if isinstance(t, dict):
            name = t.get("name")
        else:
            name = getattr(t, "name", None)
        label = str(name) if name else f"<template {i}>"
        out.append((str(i), label))
    return out


def _merge_template_items(
    base: list[tuple[str, str]], extra_values: list[str]
) -> list[tuple[str, str]]:
    out = list(base)
    seen = {str(k) for k, _ in base}
    for raw in extra_values:
        val = str(raw).strip()
        if not val or val in seen:
            continue
        out.append((val, f"<missing {val}>"))
        seen.add(val)
    return out


def _template_ord_from_value(note_type_id: str, value: Any) -> str:
    s = str(value).strip()
    if not s:
        return ""
    if s.isdigit():
        return s
    if mw is None or not getattr(mw, "col", None):
        return ""
    try:
        mid = int(str(note_type_id))
        model = mw.col.models.get(mid)
    except Exception:
        model = None
    if not model:
        return ""
    tmpls = model.get("tmpls", []) if isinstance(model, dict) else []
    for i, t in enumerate(tmpls):
        if isinstance(t, dict):
            name = t.get("name")
        else:
            name = getattr(t, "name", None)
        if name and str(name) == s:
            return str(i)
    return ""


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


def _sync_checkable_combo_text(combo: QComboBox, model: QStandardItemModel) -> None:
    labels: list[str] = []
    for i in range(model.rowCount()):
        item = model.item(i)
        if item and item.checkState() == Qt.CheckState.Checked:
            labels.append(item.text())
    if labels:
        text = ", ".join(labels[:3])
        if len(labels) > 3:
            text += f" (+{len(labels) - 3})"
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


def _combo_value(combo: QComboBox) -> str:
    data = combo.currentData()
    if data is None:
        return str(combo.currentText() or "").strip()
    return str(data).strip()


def _tip_label(text: str, tip: str) -> QLabel:
    label = QLabel(text)
    label.setToolTip(tip)
    label.setWhatsThis(tip)
    return label

def _note_type_rules() -> dict[str, dict[str, Any]]:
    raw = config.MASS_LINKER_RULES
    if not isinstance(raw, dict):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for nt_id, cfg in raw.items():
        if not isinstance(cfg, dict):
            continue
        if "templates" in cfg:
            templates = [
                _template_ord_from_value(str(nt_id), x) for x in (cfg.get("templates") or [])
            ]
            cfg = dict(cfg)
            cfg["templates"] = [t for t in templates if t]
        out[str(nt_id)] = cfg
    return out


def _dbg(*args: Any) -> None:
    dbg(*args)


def _template_ord(card: Card) -> str:
    try:
        ord_val = getattr(card, "ord", None)
        if ord_val is None:
            return ""
        return str(int(ord_val))
    except Exception:
        return ""


def _label_for_note(note, label_field: str) -> str:
    if label_field and label_field in note:
        return str(note[label_field] or "")
    # fallback: first field
    try:
        return str(note.fields[0] or "")
    except Exception:
        return ""


def _copy_note_link_for_browser(browser) -> None:
    if mw is None or not getattr(mw, "col", None):
        tooltip("No collection loaded", period=2500)
        return
    nids: list[int] = []
    try:
        nids = list(browser.selectedNotes() or [])
    except Exception:
        nids = []
    if not nids:
        try:
            card = getattr(browser, "card", None)
            if card:
                nids = [int(card.note().id)]
        except Exception:
            nids = []
    if not nids:
        tooltip("No note selected", period=2500)
        return
    nid = int(nids[0])
    try:
        note = mw.col.get_note(nid)
    except Exception:
        tooltip("Note not found", period=2500)
        return

    label_field = str(config.MASS_LINKER_LABEL_FIELD or "").strip()
    label = _label_for_note(note, label_field).strip()
    label = label.replace("[", "\\[").replace("]", "\\]")
    link = f"[{label}|nid{nid}]"
    try:
        QApplication.clipboard().setText(link)
        tooltip("Copied note link", period=2500)
        _dbg("browser copy", nid, "label_field", label_field)
    except Exception:
        log_warn("mass_linker: failed to copy note link", nid)
        tooltip("Failed to copy note link", period=2500)


def _browser_context_menu(browser, menu, *_args) -> None:
    try:
        action = QAction("Copy current note link and label", menu)
        action.triggered.connect(lambda: _copy_note_link_for_browser(browser))
        menu.addAction(action)
    except Exception:
        return


def _link_refs_for_tag(tag: str, label_field: str) -> list[LinkRef]:
    if mw is None or not getattr(mw, "col", None):
        return []
    if not tag:
        return []
    try:
        nids = mw.col.find_notes(f"tag:{tag}")
    except Exception as exc:
        log_warn("mass_linker: tag search failed", tag, repr(exc))
        return []
    _dbg("tag search", tag, "matches", len(nids))
    links: list[LinkRef] = []
    for nid in nids:
        try:
            note = mw.col.get_note(nid)
        except Exception:
            continue
        label = _label_for_note(note, label_field)
        links.append(LinkRef(label=label, kind="nid", target_id=int(nid)))
    return links


def _mass_link_provider(ctx: ProviderContext) -> list[LinkPayload]:
    try:
        config.reload_config()
    except Exception:
        pass
    if not config.MASS_LINKER_ENABLED:
        return []
    if mw is None or not getattr(mw, "col", None):
        return []

    note = ctx.note
    card = ctx.card
    nt_id = str(note.mid)
    rules = _note_type_rules()
    rule = rules.get(nt_id)
    if not rule:
        return []

    side = str(rule.get("side", "both")).lower()
    if ctx.kind == "reviewQuestion" and side not in ("front", "both"):
        return []
    if ctx.kind != "reviewQuestion" and side not in ("back", "both"):
        return []

    wanted_templates = {str(x) for x in (rule.get("templates") or []) if str(x).strip()}
    tmpl_ord = _template_ord(card)
    if wanted_templates and tmpl_ord not in wanted_templates:
        return []

    tag = str(rule.get("tag", "")).strip()
    if not tag:
        return []

    label_field = str(rule.get("label_field", "")).strip()
    refs = _link_refs_for_tag(tag, label_field)
    if not refs:
        return []

    seen_nids = set(ctx.existing_nids or set())
    out_refs: list[LinkRef] = []
    for ref in refs:
        if ref.kind == "nid" and int(ref.target_id) in seen_nids:
            continue
        out_refs.append(ref)
        if ref.kind == "nid":
            seen_nids.add(int(ref.target_id))

    if not out_refs:
        return []

    return [
        LinkPayload(
            mode="flat",
            wrapper=WrapperSpec(classes=["ajpc-auto-links"]),
            links=out_refs,
            order=100,
        )
    ]


def _install_mass_linker_ui_hooks() -> None:
    if mw is None:
        _dbg("mass linker hooks skipped: no mw")
        return
    if getattr(mw, "_ajpc_mass_linker_ui_installed", False):
        _dbg("mass linker hooks skipped: already installed")
        return
    gui_hooks.browser_will_show_context_menu.append(_browser_context_menu)
    mw._ajpc_mass_linker_ui_installed = True
    _dbg("installed mass linker ui hooks")


def _build_settings(ctx):
    mass_linker_tab = QWidget()
    mass_linker_layout = QVBoxLayout()
    mass_linker_tab.setLayout(mass_linker_layout)
    mass_linker_tabs = QTabWidget()
    mass_linker_layout.addWidget(mass_linker_tabs)

    general_tab = QWidget()
    general_layout = QVBoxLayout()
    general_tab.setLayout(general_layout)
    mass_linker_form = QFormLayout()
    general_layout.addLayout(mass_linker_form)

    mass_linker_enabled_cb = QCheckBox()
    mass_linker_enabled_cb.setChecked(config.MASS_LINKER_ENABLED)
    mass_linker_form.addRow(
        _tip_label("Enabled", "Enable or disable Mass Linker."),
        mass_linker_enabled_cb,
    )

    copy_label_field_combo = QComboBox()
    all_fields = _get_all_field_names()
    cur_copy_label = str(config.MASS_LINKER_LABEL_FIELD or "").strip()
    if cur_copy_label and cur_copy_label not in all_fields:
        all_fields.append(cur_copy_label)
    _populate_field_combo(copy_label_field_combo, all_fields, cur_copy_label)
    mass_linker_form.addRow(
        _tip_label("Label field", "Default source field for generated link labels."),
        copy_label_field_combo,
    )

    mass_linker_note_type_items = _merge_note_type_items(
        _get_note_type_items(), list((config.MASS_LINKER_RULES or {}).keys())
    )
    mass_linker_note_type_combo, mass_linker_note_type_model = _make_checkable_combo(
        mass_linker_note_type_items, list((config.MASS_LINKER_RULES or {}).keys())
    )
    mass_linker_form.addRow(
        _tip_label("Note types", "Only selected note types are processed by Mass Linker."),
        mass_linker_note_type_combo,
    )

    general_layout.addStretch(1)

    mass_linker_tabs.addTab(general_tab, "General")

    rules_tab = QWidget()
    rules_layout = QVBoxLayout()
    rules_tab.setLayout(rules_layout)

    mass_linker_rules_empty_label = QLabel("Select note types in General tab.")
    rules_layout.addWidget(mass_linker_rules_empty_label)

    mass_linker_rule_tabs = QTabWidget()
    rules_layout.addWidget(mass_linker_rule_tabs)

    rules_layout.addStretch(1)

    mass_linker_tabs.addTab(rules_tab, "Rules")

    mass_linker_state: dict[str, dict[str, str | list[str]]] = {}
    for nt_id, nt_cfg in (config.MASS_LINKER_RULES or {}).items():
        if isinstance(nt_cfg, dict):
            templates = [
                _template_ord_from_value(str(nt_id), x) or str(x).strip()
                for x in (nt_cfg.get("templates") or [])
            ]
            templates = [t for t in templates if t]
            mass_linker_state[str(nt_id)] = {
                "templates": templates,
                "side": str(nt_cfg.get("side", "both")).lower().strip() or "both",
                "tag": str(nt_cfg.get("tag", "")).strip(),
                "label_field": str(nt_cfg.get("label_field", "")).strip(),
            }

    mass_linker_note_type_widgets: dict[str, dict[str, object]] = {}

    def _capture_mass_linker_state() -> None:
        for nt_id, widgets in mass_linker_note_type_widgets.items():
            mass_linker_state[nt_id] = {
                "templates": _checked_items(widgets["templates_model"]),
                "side": _combo_value(widgets["side_combo"]),
                "tag": widgets["tag_edit"].text().strip(),
                "label_field": _combo_value(widgets["label_field_combo"]),
            }

    def _clear_mass_linker_layout() -> None:
        while mass_linker_rule_tabs.count():
            w = mass_linker_rule_tabs.widget(0)
            mass_linker_rule_tabs.removeTab(0)
            if w is not None:
                w.deleteLater()

    def _refresh_mass_linker_rules() -> None:
        _capture_mass_linker_state()
        _clear_mass_linker_layout()
        mass_linker_note_type_widgets.clear()

        selected_types = _checked_items(mass_linker_note_type_model)
        mass_linker_rules_empty_label.setVisible(not bool(selected_types))
        mass_linker_rule_tabs.setVisible(bool(selected_types))
        for nt_id in selected_types:
            cfg = mass_linker_state.get(nt_id)
            if not cfg:
                default_label_field = _get_sort_field_for_note_type(nt_id)
                cfg = {
                    "templates": [],
                    "side": "both",
                    "tag": "",
                    "label_field": default_label_field,
                }
                mass_linker_state[nt_id] = cfg
            elif not str(cfg.get("label_field", "")).strip():
                cfg["label_field"] = _get_sort_field_for_note_type(nt_id)

            tab = QWidget()
            tab_layout = QVBoxLayout()
            tab.setLayout(tab_layout)

            form = QFormLayout()
            tab_layout.addLayout(form)

            field_names = list(_get_fields_for_note_type(nt_id))
            for extra in (cfg.get("label_field", ""),):
                if extra and extra not in field_names:
                    field_names.append(extra)
            field_names = sorted(set(field_names))

            label_field_combo = QComboBox()
            _populate_field_combo(label_field_combo, field_names, cfg.get("label_field", ""))
            form.addRow(
                _tip_label("Label field", "Field copied into the link label text."),
                label_field_combo,
            )

            template_items = _merge_template_items(
                _get_template_items(nt_id), list(cfg.get("templates", []) or [])
            )
            templates_combo, templates_model = _make_checkable_combo(
                template_items, list(cfg.get("templates", []) or [])
            )
            form.addRow(
                _tip_label("Templates", "Selected templates (card ords) where this rule applies."),
                templates_combo,
            )

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
            form.addRow(
                _tip_label("Side", "Card side restriction for link generation (front/back/both)."),
                side_combo,
            )

            tag_edit = QLineEdit()
            tag_edit.setText(str(cfg.get("tag", "") or ""))
            form.addRow(
                _tip_label("Tag", "Notes with this tag become link targets for this rule."),
                tag_edit,
            )
            tab_layout.addStretch(1)
            mass_linker_rule_tabs.addTab(tab, _note_type_label(nt_id))
            mass_linker_note_type_widgets[nt_id] = {
                "label_field_combo": label_field_combo,
                "templates_model": templates_model,
                "side_combo": side_combo,
                "tag_edit": tag_edit,
            }

    _refresh_mass_linker_rules()
    mass_linker_note_type_model.itemChanged.connect(lambda _item: _refresh_mass_linker_rules())

    ctx.add_tab(mass_linker_tab, "Mass Linker")

    def _save(cfg: dict, errors: list[str]) -> None:
        _capture_mass_linker_state()
        mass_linker_note_types = _checked_items(mass_linker_note_type_model)
        mass_linker_rules_cfg: dict[str, object] = {}
        for nt_id in mass_linker_note_types:
            cfg_state = mass_linker_state.get(nt_id, {})
            templates = [
                str(x).strip() for x in (cfg_state.get("templates") or []) if str(x).strip()
            ]
            templates = [t for t in templates if t.isdigit()]
            side = str(cfg_state.get("side", "both")).lower().strip() or "both"
            tag = str(cfg_state.get("tag", "")).strip()
            label_field = str(cfg_state.get("label_field", "")).strip()

            if mass_linker_enabled_cb.isChecked():
                if not tag:
                    errors.append(
                        f"Mass Linker: tag missing for note type: {_note_type_label(nt_id)}"
                    )
                if side not in ("front", "back", "both"):
                    errors.append(
                        f"Mass Linker: side invalid for note type: {_note_type_label(nt_id)}"
                    )

            payload: dict[str, object] = {}
            if templates:
                payload["templates"] = templates
            if side:
                payload["side"] = side
            if tag:
                payload["tag"] = tag
            if label_field:
                payload["label_field"] = label_field
            if payload:
                mass_linker_rules_cfg[nt_id] = payload

        config._cfg_set(cfg, "mass_linker.enabled", bool(mass_linker_enabled_cb.isChecked()))
        config._cfg_set(
            cfg,
            "mass_linker.label_field",
            str(_combo_value(copy_label_field_combo) or "").strip(),
        )
        config._cfg_set(cfg, "mass_linker.rules", mass_linker_rules_cfg)

    return _save


def _init() -> None:
    from . import link_core

    link_core.install_link_core()
    link_core.register_provider("mass_linker", _mass_link_provider, order=100)
    _install_mass_linker_ui_hooks()


MODULE = ModuleSpec(
    id="mass_linker",
    label="Mass Linker",
    order=60,
    init=_init,
    build_settings=_build_settings,
)


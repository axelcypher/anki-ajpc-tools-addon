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
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
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
from .link_core import LinkGroup, LinkPayload, LinkRef, ProviderContext, WrapperSpec

ADDON_DIR = os.path.dirname(os.path.dirname(__file__))
CONFIG_PATH = os.path.join(ADDON_DIR, "config.json")

CFG: dict[str, Any] = {}
DEBUG = False
MASS_LINKER_ENABLED = True
MASS_LINKER_RULES: list[dict[str, Any]] = []


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


def _normalize_mass_linker_rules(raw: Any, col=None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if isinstance(raw, list):
        for i, rule in enumerate(raw):
            if not isinstance(rule, dict):
                continue
            item = dict(rule)
            item["id"] = str(item.get("id") or f"rule_{i + 1}")
            item["name"] = str(item.get("name") or f"Rule {i + 1}")
            item["mode"] = str(item.get("mode") or "basic").strip().lower()
            item["enabled"] = bool(item.get("enabled", True))
            item["side"] = str(item.get("side") or "both").strip().lower()
            item["group_name"] = str(item.get("group_name") or "").strip()
            item["target_mode"] = str(item.get("target_mode") or "note").strip().lower()
            item["selector_separator"] = str(item.get("selector_separator") or "::")
            item["target_note_types"] = [str(x).strip() for x in (item.get("target_note_types") or []) if str(x).strip()]
            item["target_templates"] = [str(x).strip() for x in (item.get("target_templates") or []) if str(x).strip()]
            item["source_templates"] = [str(x).strip() for x in (item.get("source_templates") or []) if str(x).strip()]
            item["target_conditions"] = [x for x in (item.get("target_conditions") or []) if isinstance(x, dict)]
            item["source_conditions"] = [x for x in (item.get("source_conditions") or []) if isinstance(x, dict)]
            item["source_template_mappings"] = [
                x for x in (item.get("source_template_mappings") or []) if isinstance(x, dict)
            ]
            if col is not None:
                item["target_note_types"] = [
                    _note_type_id_from_ident(col, x) for x in item["target_note_types"]
                ]
                item["target_note_types"] = [x for x in item["target_note_types"] if x]
                src_nt = str(item.get("source_note_type") or "").strip()
                if src_nt:
                    item["source_note_type"] = _note_type_id_from_ident(col, src_nt)
            out.append(item)
        return out
    if not isinstance(raw, dict):
        return out

    # Hard-cut conversion of legacy dict rules keyed by target note type id.
    for i, (nt_id, cfg) in enumerate(raw.items()):
        if not isinstance(cfg, dict):
            continue
        target_nt = str(nt_id).strip()
        name = f"Rule {i + 1}"
        out.append(
            {
                "id": f"rule_{i + 1}",
                "name": f"{name}",
                "enabled": True,
                "mode": "basic",
                "group_name": "Mass Linker",
                "side": str(cfg.get("side", "both")).strip().lower() or "both",
                "source_tag": str(cfg.get("tag", "")).strip(),
                "source_label_field": str(cfg.get("label_field", "")).strip(),
                "target_note_types": [target_nt] if target_nt else [],
                "target_templates": [str(x).strip() for x in (cfg.get("templates") or []) if str(x).strip()],
                "target_conditions": [],
                "source_conditions": [],
                "selector_separator": "::",
                "target_mode": "note",
                "source_templates": [],
                "source_template_mappings": [],
            }
        )
    return out


def reload_config() -> None:
    global CFG, DEBUG
    global MASS_LINKER_ENABLED, MASS_LINKER_RULES

    CFG = _load_config()

    _dbg = CFG.get("debug", {})
    if isinstance(_dbg, dict):
        DEBUG = bool(_dbg.get("enabled", False))
    else:
        DEBUG = bool(_dbg)

    MASS_LINKER_ENABLED = bool(cfg_get("mass_linker.enabled", True))
    MASS_LINKER_RULES = _normalize_mass_linker_rules(cfg_get("mass_linker.rules", []) or [])

    try:
        from aqt import mw  # type: ignore
    except Exception:
        mw = None  # type: ignore

    if mw is not None and getattr(mw, "col", None):
        col = mw.col
        if col:
            MASS_LINKER_RULES = _normalize_mass_linker_rules(MASS_LINKER_RULES, col=col)


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


def _fill_checkable_model(
    model: QStandardItemModel,
    items: list[Any],
    selected: list[str],
) -> None:
    selected_set = {str(x) for x in (selected or [])}
    model.clear()
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


def _make_checkable_combo(items: list[Any], selected: list[str]) -> tuple[QComboBox, QStandardItemModel]:
    combo = QComboBox()
    combo.setEditable(True)
    if combo.lineEdit() is not None:
        combo.lineEdit().setReadOnly(True)
    model = QStandardItemModel(combo)
    _fill_checkable_model(model, items, selected)
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


def _split_csv(value: str) -> list[str]:
    parts = [p.strip() for p in str(value or "").split(",")]
    out: list[str] = []
    for p in parts:
        if not p:
            continue
        if p not in out:
            out.append(p)
    return out

def _rule_tabs() -> list[dict[str, Any]]:
    raw = config.MASS_LINKER_RULES
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for i, rule in enumerate(raw):
        if not isinstance(rule, dict):
            continue
        item = dict(rule)
        item["id"] = str(item.get("id") or f"rule_{i + 1}")
        item["name"] = str(item.get("name") or f"Rule {i + 1}")
        item["enabled"] = bool(item.get("enabled", True))
        item["mode"] = str(item.get("mode", "basic")).strip().lower() or "basic"
        item["side"] = str(item.get("side", "both")).strip().lower() or "both"
        item["group_name"] = str(item.get("group_name", "")).strip()
        item["target_mode"] = str(item.get("target_mode", "note")).strip().lower() or "note"
        item["selector_separator"] = str(item.get("selector_separator", "::"))
        item["target_note_types"] = [str(x).strip() for x in (item.get("target_note_types") or []) if str(x).strip()]
        item["target_templates"] = [str(x).strip() for x in (item.get("target_templates") or []) if str(x).strip()]
        item["source_templates"] = [str(x).strip() for x in (item.get("source_templates") or []) if str(x).strip()]
        item["target_conditions"] = [x for x in (item.get("target_conditions") or []) if isinstance(x, dict)]
        item["source_conditions"] = [x for x in (item.get("source_conditions") or []) if isinstance(x, dict)]
        item["source_template_mappings"] = [
            x for x in (item.get("source_template_mappings") or []) if isinstance(x, dict)
        ]
        out.append(item)
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


def _card_note_type_id(card: Card) -> str:
    try:
        return str(int(card.note().mid))
    except Exception:
        return ""


def _note_tags(note: Any) -> set[str]:
    tags_raw = getattr(note, "tags", None)
    if not tags_raw:
        return set()
    return {str(t).strip() for t in tags_raw if str(t).strip()}


def _field_text(note: Any, field_name: str) -> str:
    f = str(field_name or "").strip()
    if not f:
        return ""
    try:
        if f in note:
            return str(note[f] or "")
    except Exception:
        pass
    return ""


def _match_text(actual: str, op: str, expected: str) -> bool:
    a = str(actual or "")
    b = str(expected or "")
    op_l = str(op or "contains").strip().lower()
    if op_l in ("any",):
        return True
    if op_l in ("exists",):
        return bool(a.strip())
    if op_l in ("equals", "eq"):
        return a == b
    if op_l in ("starts_with", "startswith"):
        return a.startswith(b)
    if op_l in ("ends_with", "endswith"):
        return a.endswith(b)
    if op_l in ("regex", "re"):
        try:
            import re

            return bool(re.search(b, a))
        except Exception:
            return False
    return b in a


def _eval_single_condition(note: Any, cond: dict[str, Any]) -> bool:
    kind = str(cond.get("kind", "field")).strip().lower()
    op = str(cond.get("op", "contains")).strip().lower()
    value = str(cond.get("value", ""))
    if op == "any":
        return True
    if kind == "tag":
        tags = _note_tags(note)
        if op in ("has", "equals", "eq"):
            return value in tags
        joined = " ".join(sorted(tags))
        return _match_text(joined, op, value)
    field = str(cond.get("field", "")).strip()
    actual = _field_text(note, field)
    return _match_text(actual, op, value)


def _eval_conditions(note: Any, conditions: list[dict[str, Any]]) -> bool:
    if not conditions:
        return True
    result: bool | None = None
    for cond in conditions:
        if not isinstance(cond, dict):
            continue
        connector = str(cond.get("connector", "AND")).strip().upper()
        negate = bool(cond.get("negate", False))
        cond_result = _eval_single_condition(note, cond)
        if negate:
            cond_result = not cond_result
        if result is None:
            result = cond_result
            continue
        if connector == "OR":
            result = bool(result or cond_result)
        elif connector == "ANY":
            result = True
        else:
            result = bool(result and cond_result)
    return bool(result) if result is not None else True


def _find_notes_by_tag(tag: str) -> list[int]:
    if mw is None or not getattr(mw, "col", None):
        return []
    q = str(tag or "").strip()
    if not q:
        return []
    try:
        return list(mw.col.find_notes(f"tag:{q}"))
    except Exception as exc:
        log_warn("mass_linker: tag search failed", q, repr(exc))
        return []


def _find_notes_by_mid(mid_str: str) -> list[int]:
    if mw is None or not getattr(mw, "col", None):
        return []
    try:
        mid = int(str(mid_str).strip())
    except Exception:
        return []
    try:
        return list(mw.col.db.list("select id from notes where mid = ?", mid))
    except Exception:
        return []


def _refs_from_nids(nids: list[int], label_field: str) -> list[LinkRef]:
    out: list[LinkRef] = []
    for nid in nids:
        try:
            note = mw.col.get_note(int(nid))
        except Exception:
            continue
        label = _label_for_note(note, label_field)
        out.append(LinkRef(label=label, kind="nid", target_id=int(nid)))
    return out


def _refs_from_notes_with_card_targets(
    source_nids: list[int],
    *,
    target_note: Any,
    target_card: Card,
    rule: dict[str, Any],
    label_field: str,
) -> list[LinkRef]:
    refs: list[LinkRef] = []
    target_mode = str(rule.get("target_mode", "note")).strip().lower() or "note"
    if target_mode != "card":
        return _refs_from_nids(source_nids, label_field)

    fallback_templates = {str(x).strip() for x in (rule.get("source_templates") or []) if str(x).strip()}
    mapping_field = str(rule.get("mapping_field", "")).strip()
    mapping_value = _field_text(target_note, mapping_field) if mapping_field else ""
    mappings = [m for m in (rule.get("source_template_mappings") or []) if isinstance(m, dict)]

    selected_templates: set[str] = set()
    for mp in mappings:
        sel = str(mp.get("selector", "")).strip()
        if not sel:
            continue
        if mapping_value == sel:
            vals = [str(x).strip() for x in (mp.get("source_templates") or []) if str(x).strip()]
            selected_templates.update(vals)
    if not selected_templates:
        selected_templates = set(fallback_templates)
    if not selected_templates:
        return []

    for nid in source_nids:
        try:
            src_note = mw.col.get_note(int(nid))
            src_cards = src_note.cards()
        except Exception:
            continue
        label = _label_for_note(src_note, label_field)
        for c in src_cards:
            ord_val = _template_ord(c)
            if ord_val not in selected_templates:
                continue
            refs.append(LinkRef(label=label, kind="cid", target_id=int(c.id)))
    return refs


def _label_for_note(note, label_field: str) -> str:
    if label_field and label_field in note:
        return str(note[label_field] or "")
    # default fallback: sort field of the note type
    try:
        sort_field = _get_sort_field_for_note_type(str(getattr(note, "mid", "")))
        if sort_field and sort_field in note:
            return str(note[sort_field] or "")
    except Exception:
        pass
    # final fallback: first field
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

    label = _label_for_note(note, "").strip()
    label = label.replace("[", "\\[").replace("]", "\\]")
    link = f"[{label}|nid{nid}]"
    try:
        QApplication.clipboard().setText(link)
        tooltip("Copied note link", period=2500)
        _dbg("browser copy", nid, "label_field", "sort_field(default)")
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
    nids = _find_notes_by_tag(tag)
    _dbg("tag search", tag, "matches", len(nids))
    return _refs_from_nids([int(x) for x in nids], label_field)


def _rule_matches_target(rule: dict[str, Any], ctx: ProviderContext) -> bool:
    mode = str(rule.get("mode", "basic")).strip().lower() or "basic"
    side = str(rule.get("side", "both")).lower()
    if ctx.kind == "reviewQuestion" and side not in ("front", "both"):
        return False
    if ctx.kind != "reviewQuestion" and side not in ("back", "both"):
        return False

    target_nt = {str(x).strip() for x in (rule.get("target_note_types") or []) if str(x).strip()}
    if target_nt and str(ctx.note.mid) not in target_nt:
        return False

    wanted_templates = {str(x).strip() for x in (rule.get("target_templates") or []) if str(x).strip()}
    tmpl_ord = _template_ord(ctx.card)
    if wanted_templates and tmpl_ord not in wanted_templates:
        return False

    if mode != "basic":
        target_conditions = [x for x in (rule.get("target_conditions") or []) if isinstance(x, dict)]
        if target_conditions and not _eval_conditions(ctx.note, target_conditions):
            return False
    return True


def _source_note_passes(rule: dict[str, Any], note: Any) -> bool:
    mode = str(rule.get("mode", "basic")).strip().lower() or "basic"
    if mode == "basic":
        return True
    source_conditions = [x for x in (rule.get("source_conditions") or []) if isinstance(x, dict)]
    if not source_conditions:
        return True
    return _eval_conditions(note, source_conditions)


def _refs_for_rule(rule: dict[str, Any], ctx: ProviderContext) -> list[LinkRef]:
    mode = str(rule.get("mode", "basic")).strip().lower() or "basic"
    label_field = str(rule.get("source_label_field", "")).strip()

    if mode == "advanced_tag":
        base = str(rule.get("source_tag_base", "")).strip()
        if not base:
            return []
        sep = str(rule.get("selector_separator", "::"))
        selector_field = str(rule.get("selector_field", "")).strip()
        selector_value = _field_text(ctx.note, selector_field).strip() if selector_field else ""
        search_tag = f"{base}{sep}{selector_value}" if selector_value else base
        nids = _find_notes_by_tag(search_tag)
        refs: list[LinkRef] = []
        for nid in nids:
            try:
                src_note = mw.col.get_note(int(nid))
            except Exception:
                continue
            if not _source_note_passes(rule, src_note):
                continue
            label = _label_for_note(src_note, label_field)
            refs.append(LinkRef(label=label, kind="nid", target_id=int(nid)))
        return refs

    if mode == "advanced_notetype":
        src_nt = str(rule.get("source_note_type", "")).strip()
        if not src_nt:
            return []
        source_nids = _find_notes_by_mid(src_nt)
        filtered_nids: list[int] = []
        for nid in source_nids:
            try:
                src_note = mw.col.get_note(int(nid))
            except Exception:
                continue
            if _source_note_passes(rule, src_note):
                filtered_nids.append(int(nid))
        return _refs_from_notes_with_card_targets(
            filtered_nids,
            target_note=ctx.note,
            target_card=ctx.card,
            rule=rule,
            label_field=label_field,
        )

    # basic
    tag = str(rule.get("source_tag", "")).strip()
    if not tag:
        return []
    return _link_refs_for_tag(tag, label_field)


def _mass_link_provider(ctx: ProviderContext) -> list[LinkPayload]:
    try:
        config.reload_config()
    except Exception:
        pass
    if not config.MASS_LINKER_ENABLED:
        return []
    if mw is None or not getattr(mw, "col", None):
        return []

    rules = _rule_tabs()
    if not rules:
        return []

    seen_nids = set(ctx.existing_nids or set())
    seen_cids = set(ctx.existing_cids or set())
    payloads: list[LinkPayload] = []
    for idx, rule in enumerate(rules):
        if not bool(rule.get("enabled", True)):
            continue
        if not _rule_matches_target(rule, ctx):
            continue

        refs = _refs_for_rule(rule, ctx)
        if not refs:
            continue

        unique_refs: list[LinkRef] = []
        for ref in refs:
            target = int(ref.target_id)
            if str(ref.kind).lower() == "cid":
                if target in seen_cids:
                    continue
                seen_cids.add(target)
            else:
                if target in seen_nids:
                    continue
                seen_nids.add(target)
            unique_refs.append(ref)
        if not unique_refs:
            continue

        group_name = str(rule.get("group_name", "")).strip() or str(rule.get("name", "")).strip() or "Mass Linker"
        payloads.append(
            LinkPayload(
                mode="grouped",
                wrapper=WrapperSpec(classes=["ajpc-auto-links", "ajpc-auto-links-mass-linker"]),
                groups=[LinkGroup(key=group_name, links=unique_refs)],
                order=100 + idx,
            )
        )

    return payloads


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

    general_layout.addStretch(1)

    mass_linker_tabs.addTab(general_tab, "General")

    rules_tab = QWidget()
    rules_layout = QVBoxLayout()
    rules_tab.setLayout(rules_layout)

    rules_toolbar = QHBoxLayout()
    add_rule_btn = QPushButton("+ Rule")
    remove_rule_btn = QPushButton("- Rule")
    rules_toolbar.addWidget(add_rule_btn)
    rules_toolbar.addWidget(remove_rule_btn)
    rules_toolbar.addStretch(1)
    rules_layout.addLayout(rules_toolbar)

    mass_linker_rule_tabs = QTabWidget()
    rules_layout.addWidget(mass_linker_rule_tabs)
    rules_layout.addStretch(1)
    mass_linker_tabs.addTab(rules_tab, "Rules")

    note_type_items_base = _get_note_type_items()
    all_field_names = _get_all_field_names()
    rule_widgets: dict[QWidget, dict[str, Any]] = {}

    def _rule_title(name: str, idx: int) -> str:
        s = str(name or "").strip()
        return s or f"Rule {idx + 1}"

    def _make_condition_editor(
        *,
        title: str,
        initial: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        wrapper = QWidget()
        wrap_layout = QVBoxLayout()
        wrap_layout.setContentsMargins(0, 0, 0, 0)
        wrapper.setLayout(wrap_layout)

        rows_host = QWidget()
        rows_layout = QVBoxLayout()
        rows_layout.setContentsMargins(0, 0, 0, 0)
        rows_host.setLayout(rows_layout)
        wrap_layout.addWidget(rows_host)

        add_btn = QPushButton("Add condition")
        wrap_layout.addWidget(add_btn)

        rows: list[dict[str, Any]] = []

        def _refresh_connector_visibility() -> None:
            for idx, st in enumerate(rows):
                combo = st["connector"]
                is_first = idx == 0
                combo.setVisible(not is_first)
                combo.setEnabled(not is_first)

        def _add_row(data: dict[str, Any] | None = None) -> None:
            row = QWidget()
            row_l = QHBoxLayout()
            row_l.setContentsMargins(0, 0, 0, 0)
            row.setLayout(row_l)

            connector_combo = QComboBox()
            connector_combo.addItem("AND", "AND")
            connector_combo.addItem("OR", "OR")
            connector_combo.addItem("ANY", "ANY")

            negate_cb = QCheckBox("NOT")
            kind_combo = QComboBox()
            kind_combo.addItem("Field", "field")
            kind_combo.addItem("Tag", "tag")

            field_combo = QComboBox()
            _populate_field_combo(field_combo, all_field_names, "")
            field_combo.setMinimumWidth(130)

            op_combo = QComboBox()
            for lbl, val in (
                ("contains", "contains"),
                ("equals", "equals"),
                ("starts_with", "starts_with"),
                ("ends_with", "ends_with"),
                ("regex", "regex"),
                ("exists", "exists"),
                ("has(tag)", "has"),
                ("any", "any"),
            ):
                op_combo.addItem(lbl, val)

            value_edit = QLineEdit()
            value_edit.setPlaceholderText("value")
            value_edit.setMinimumWidth(140)

            remove_btn = QPushButton("x")
            remove_btn.setMaximumWidth(28)

            row_l.addWidget(connector_combo)
            row_l.addWidget(negate_cb)
            row_l.addWidget(kind_combo)
            row_l.addWidget(field_combo)
            row_l.addWidget(op_combo)
            row_l.addWidget(value_edit)
            row_l.addWidget(remove_btn)

            state = {
                "row": row,
                "connector": connector_combo,
                "negate": negate_cb,
                "kind": kind_combo,
                "field": field_combo,
                "op": op_combo,
                "value": value_edit,
            }
            rows.append(state)
            rows_layout.addWidget(row)

            def _update_kind() -> None:
                is_tag = str(kind_combo.currentData() or "field") == "tag"
                field_combo.setEnabled(not is_tag)

            kind_combo.currentIndexChanged.connect(lambda _i: _update_kind())
            _update_kind()

            def _remove() -> None:
                if state in rows:
                    rows.remove(state)
                rows_layout.removeWidget(row)
                row.deleteLater()
                _refresh_connector_visibility()

            remove_btn.clicked.connect(_remove)

            cfg = data or {}
            c_idx = connector_combo.findData(str(cfg.get("connector", "AND")).upper())
            if c_idx >= 0:
                connector_combo.setCurrentIndex(c_idx)
            negate_cb.setChecked(bool(cfg.get("negate", False)))
            k_idx = kind_combo.findData(str(cfg.get("kind", "field")).lower())
            if k_idx >= 0:
                kind_combo.setCurrentIndex(k_idx)
            _populate_field_combo(field_combo, all_field_names, str(cfg.get("field", "")).strip())
            o_idx = op_combo.findData(str(cfg.get("op", "contains")).lower())
            if o_idx >= 0:
                op_combo.setCurrentIndex(o_idx)
            value_edit.setText(str(cfg.get("value", "")))
            _refresh_connector_visibility()

        add_btn.clicked.connect(lambda: _add_row(None))
        for cond in (initial or []):
            if isinstance(cond, dict):
                _add_row(cond)

        def _collect() -> list[dict[str, Any]]:
            out: list[dict[str, Any]] = []
            for idx, r in enumerate(rows):
                out.append(
                    {
                        "connector": "AND" if idx == 0 else str(r["connector"].currentData() or "AND"),
                        "negate": bool(r["negate"].isChecked()),
                        "kind": str(r["kind"].currentData() or "field"),
                        "field": str(_combo_value(r["field"])).strip(),
                        "op": str(r["op"].currentData() or "contains"),
                        "value": str(r["value"].text() or ""),
                    }
                )
            return out

        return {"collect": _collect, "widget": wrapper}

    def _make_mapping_editor(
        *,
        initial: list[dict[str, Any]] | None = None,
        template_items_provider=None,
    ) -> dict[str, Any]:
        wrapper = QWidget()
        wrap_layout = QVBoxLayout()
        wrap_layout.setContentsMargins(0, 0, 0, 0)
        wrapper.setLayout(wrap_layout)

        rows_layout = QVBoxLayout()
        rows_layout.setContentsMargins(0, 0, 0, 0)
        wrap_layout.addLayout(rows_layout)

        add_btn = QPushButton("Add mapping")
        wrap_layout.addWidget(add_btn)

        rows: list[dict[str, Any]] = []

        def _get_items(extra_values: list[str] | None = None) -> list[tuple[str, str]]:
            if callable(template_items_provider):
                try:
                    items = template_items_provider() or []
                except Exception:
                    items = []
            else:
                items = []
            return _merge_template_items(list(items), list(extra_values or []))

        def _add_row(data: dict[str, Any] | None = None) -> None:
            row = QWidget()
            row_l = QHBoxLayout()
            row_l.setContentsMargins(0, 0, 0, 0)
            row.setLayout(row_l)

            selector_edit = QLineEdit()
            selector_edit.setPlaceholderText("selector value")
            source_template_combo = QComboBox()
            source_template_combo.setEditable(False)
            source_template_combo.addItem("", "")
            cfg = data or {}
            preselected_templates = [str(x).strip() for x in (cfg.get("source_templates") or []) if str(x).strip()]
            preselected_template = preselected_templates[0] if preselected_templates else ""
            for val, label in _get_items(extra_values=[preselected_template] if preselected_template else []):
                source_template_combo.addItem(label, val)
            if preselected_template:
                idx = source_template_combo.findData(preselected_template)
                if idx >= 0:
                    source_template_combo.setCurrentIndex(idx)
            remove_btn = QPushButton("x")
            remove_btn.setMaximumWidth(28)

            row_l.addWidget(selector_edit)
            row_l.addWidget(source_template_combo)
            row_l.addWidget(remove_btn)
            rows_layout.addWidget(row)

            state = {
                "row": row,
                "selector": selector_edit,
                "source_template_combo": source_template_combo,
            }
            rows.append(state)

            def _remove() -> None:
                if state in rows:
                    rows.remove(state)
                rows_layout.removeWidget(row)
                row.deleteLater()

            remove_btn.clicked.connect(_remove)

            selector_edit.setText(str(cfg.get("selector", "")))

        add_btn.clicked.connect(lambda: _add_row(None))
        for m in (initial or []):
            if isinstance(m, dict):
                _add_row(m)

        def _collect() -> list[dict[str, Any]]:
            out: list[dict[str, Any]] = []
            for r in rows:
                selector = str(r["selector"].text() or "").strip()
                selected_template = str(r["source_template_combo"].currentData() or "").strip()
                if not selector and not selected_template:
                    continue
                payload: dict[str, Any] = {"selector": selector}
                if selected_template:
                    payload["source_templates"] = [selected_template]
                out.append(
                    payload
                )
            return out

        def _refresh_templates() -> None:
            for r in rows:
                combo = r["source_template_combo"]
                cur = str(combo.currentData() or "").strip()
                combo.clear()
                combo.addItem("", "")
                for val, label in _get_items(extra_values=[cur] if cur else []):
                    combo.addItem(label, val)
                if cur:
                    idx = combo.findData(cur)
                    if idx >= 0:
                        combo.setCurrentIndex(idx)

        return {"collect": _collect, "widget": wrapper, "refresh_templates": _refresh_templates}

    def _default_rule(idx: int) -> dict[str, Any]:
        return {
            "id": f"rule_{int(time.time() * 1000)}_{idx}",
            "name": f"Rule {idx + 1}",
            "enabled": True,
            "group_name": "Mass Linker",
            "mode": "basic",
            "side": "both",
            "target_mode": "note",
            "source_tag": "",
            "source_tag_base": "",
            "selector_separator": "::",
            "selector_field": "",
            "source_note_type": "",
            "mapping_field": "",
            "source_label_field": "",
            "target_note_types": [],
            "target_templates": [],
            "source_templates": [],
            "target_conditions": [],
            "source_conditions": [],
            "source_template_mappings": [],
        }

    def _make_source_note_type_combo(current_value: str) -> QComboBox:
        combo = QComboBox()
        combo.setEditable(False)
        combo.addItem("", "")
        items = _merge_note_type_items(note_type_items_base, [current_value] if current_value else [])
        for val, label in items:
            combo.addItem(label, val)
        idx = combo.findData(str(current_value or "").strip())
        if idx >= 0:
            combo.setCurrentIndex(idx)
        return combo

    def _template_items_for_note_types(
        note_type_ids: list[str],
        *,
        extra_values: list[str] | None = None,
    ) -> list[tuple[str, str]]:
        ids = [str(x).strip() for x in (note_type_ids or []) if str(x).strip()]
        if not ids:
            # No selected note type scope -> no template options.
            # This avoids cross-rule/global leakage when creating a fresh rule tab.
            return _merge_template_items([], list(extra_values or []))
        by_ord: dict[str, list[str]] = {}
        for nt_id in ids:
            nt_name = _note_type_label(nt_id)
            for ord_val, tmpl_name in _get_template_items(nt_id):
                key = str(ord_val).strip()
                if not key:
                    continue
                lbl = f"{tmpl_name} [{nt_name}]"
                by_ord.setdefault(key, []).append(lbl)
        out: list[tuple[str, str]] = []
        for ord_val, labels in by_ord.items():
            uniq = []
            for lbl in labels:
                if lbl not in uniq:
                    uniq.append(lbl)
            if len(uniq) == 1:
                out.append((ord_val, f"{ord_val}: {uniq[0]}"))
            else:
                shown = " | ".join(uniq[:3])
                if len(uniq) > 3:
                    shown += f" (+{len(uniq)-3})"
                out.append((ord_val, f"{ord_val}: {shown}"))
        out.sort(key=lambda x: int(x[0]) if str(x[0]).isdigit() else 999999)
        return _merge_template_items(out, list(extra_values or []))

    def _add_rule_tab(rule: dict[str, Any]) -> None:
        tab = QWidget()
        tab_layout = QVBoxLayout()
        tab.setLayout(tab_layout)
        form = QFormLayout()
        tab_layout.addLayout(form)

        rule_id = str(rule.get("id", "")).strip() or f"rule_{int(time.time() * 1000)}"
        name_edit = QLineEdit(str(rule.get("name", "")))
        enabled_cb = QCheckBox()
        enabled_cb.setChecked(bool(rule.get("enabled", True)))
        group_name_edit = QLineEdit(str(rule.get("group_name", "Mass Linker")))

        mode_combo = QComboBox()
        mode_combo.addItem("Basic", "basic")
        mode_combo.addItem("Advanced: Tag source", "advanced_tag")
        mode_combo.addItem("Advanced: NoteType source", "advanced_notetype")

        side_combo = QComboBox()
        side_combo.addItem("Front", "front")
        side_combo.addItem("Back", "back")
        side_combo.addItem("Both", "both")

        target_mode_combo = QComboBox()
        target_mode_combo.addItem("Note (nid)", "note")
        target_mode_combo.addItem("Card (cid)", "card")

        source_label_field_combo = QComboBox()
        _populate_field_combo(
            source_label_field_combo, all_field_names, str(rule.get("source_label_field", "")).strip()
        )

        target_note_type_items = _merge_note_type_items(
            note_type_items_base, list(rule.get("target_note_types") or [])
        )
        target_note_types_combo, target_note_types_model = _make_checkable_combo(
            target_note_type_items, list(rule.get("target_note_types") or [])
        )
        initial_target_templates = [str(x).strip() for x in (rule.get("target_templates") or []) if str(x).strip()]
        target_template_items = _template_items_for_note_types(
            list(rule.get("target_note_types") or []),
            extra_values=initial_target_templates,
        )
        target_templates_combo, target_templates_model = _make_checkable_combo(
            target_template_items,
            initial_target_templates,
        )

        source_tag_edit = QLineEdit(str(rule.get("source_tag", "")))

        source_tag_base_edit = QLineEdit(str(rule.get("source_tag_base", "")))
        separator_edit = QLineEdit(str(rule.get("selector_separator", "::")))
        selector_field_combo = QComboBox()
        _populate_field_combo(selector_field_combo, all_field_names, str(rule.get("selector_field", "")))

        source_note_type_combo = _make_source_note_type_combo(str(rule.get("source_note_type", "")))
        mapping_field_combo = QComboBox()
        _populate_field_combo(mapping_field_combo, all_field_names, str(rule.get("mapping_field", "")))
        initial_source_templates = [str(x).strip() for x in (rule.get("source_templates") or []) if str(x).strip()]
        source_template_items = _template_items_for_note_types(
            [str(_combo_value(source_note_type_combo) or "").strip()],
            extra_values=initial_source_templates,
        )
        source_templates_combo, source_templates_model = _make_checkable_combo(
            source_template_items,
            initial_source_templates,
        )

        rule_row_widget = QWidget()
        rule_row_layout = QHBoxLayout()
        rule_row_layout.setContentsMargins(0, 0, 0, 0)
        rule_row_widget.setLayout(rule_row_layout)
        name_edit.setPlaceholderText("Rule name")
        group_name_edit.setPlaceholderText("Group name")
        enabled_cb.setText("Enabled")
        rule_row_layout.addWidget(name_edit, 2)
        rule_row_layout.addWidget(group_name_edit, 2)
        rule_row_layout.addWidget(enabled_cb, 0)
        form.addRow(
            _tip_label(
                "Rule",
                "Rule Name | Group Name | Enabled",
            ),
            rule_row_widget,
        )
        mode_label = _tip_label("Mode", "Basic or advanced source mode.")
        form.addRow(mode_label, mode_combo)
        form.addRow(QLabel("<b>Target settings</b>"))
        target_side_label = _tip_label("Target side", "Front/back/both restriction on the target card side.")
        form.addRow(target_side_label, side_combo)
        target_note_types_label = _tip_label(
            "Target note types",
            "Optional scope for target notes. If empty, only target conditions are used.",
        )
        form.addRow(
            target_note_types_label,
            target_note_types_combo,
        )
        target_templates_label = _tip_label(
            "Target card templates",
            "Optional target card template filter.",
        )
        form.addRow(
            target_templates_label,
            target_templates_combo,
        )
        target_cond_editor = _make_condition_editor(
            title="Target conditions (AND/OR/ANY + NOT)",
            initial=[x for x in (rule.get("target_conditions") or []) if isinstance(x, dict)],
        )
        target_cond_scroll = QScrollArea()
        target_cond_scroll.setWidgetResizable(True)
        target_cond_scroll.setWidget(target_cond_editor["widget"])
        target_cond_scroll.setMaximumHeight(180)
        form.addRow(
            _tip_label("Target conditions", "Conditions evaluated against the current target note."),
            target_cond_scroll,
        )
        form.addRow(QLabel("<b>Source settings</b>"))
        source_label_field_label = _tip_label(
            "Source label field",
            "Field copied from source note into link label text.",
        )
        form.addRow(source_label_field_label, source_label_field_combo)
        basic_source_tag_label = _tip_label(
            "Basic source tag", "Basic mode: notes with this tag are linked as nid."
        )
        form.addRow(basic_source_tag_label, source_tag_edit)
        tag_base_label = _tip_label("Tag base", "Advanced tag mode: base tag before selector suffix.")
        form.addRow(
            tag_base_label,
            source_tag_base_edit,
        )
        selector_separator_label = _tip_label(
            "Selector separator", "Free separator between <tag base> and <selector>."
        )
        form.addRow(
            selector_separator_label,
            separator_edit,
        )
        selector_field_label = _tip_label(
            "Selector field", "Target note field used as selector suffix in advanced tag mode."
        )
        form.addRow(
            selector_field_label,
            selector_field_combo,
        )
        source_note_type_label = _tip_label(
            "Source note type", "Advanced NoteType mode source note type."
        )
        form.addRow(source_note_type_label, source_note_type_combo)
        target_mode_label = _tip_label(
            "Link target kind", "Advanced NoteType output kind: note (`nid`) or card (`cid`)."
        )
        form.addRow(target_mode_label, target_mode_combo)
        mapping_field_label = _tip_label(
            "Mapping field", "Target note field whose value is matched against mapping selector."
        )
        form.addRow(
            mapping_field_label,
            mapping_field_combo,
        )
        source_cond_editor = _make_condition_editor(
            title="Source conditions (AND/OR/ANY + NOT)",
            initial=[x for x in (rule.get("source_conditions") or []) if isinstance(x, dict)],
        )
        source_cond_scroll = QScrollArea()
        source_cond_scroll.setWidgetResizable(True)
        source_cond_scroll.setWidget(source_cond_editor["widget"])
        source_cond_scroll.setMaximumHeight(180)
        form.addRow(
            _tip_label("Source conditions", "Conditions evaluated against candidate source notes."),
            source_cond_scroll,
        )
        mapping_editor = _make_mapping_editor(
            initial=[x for x in (rule.get("source_template_mappings") or []) if isinstance(x, dict)],
            template_items_provider=lambda: _template_items_for_note_types(
                [str(_combo_value(source_note_type_combo) or "").strip()]
            ),
        )
        mapping_scroll = QScrollArea()
        mapping_scroll.setWidgetResizable(True)
        mapping_scroll.setWidget(mapping_editor["widget"])
        mapping_scroll.setMaximumHeight(160)
        form.addRow(
            _tip_label(
                "Card mappings",
                "Exact mapping: selector value -> source card template.",
            ),
            mapping_scroll,
        )
        fallback_templates_label = _tip_label(
            "Fallback source card templates",
            "Used only when no selector mapping matches. Choose fallback source card templates.",
        )
        form.addRow(
            fallback_templates_label,
            source_templates_combo,
        )
        tab_layout.addStretch(1)

        def _set_form_row_visible(field_widget: QWidget, visible: bool) -> None:
            label_widget = form.labelForField(field_widget)
            if label_widget is not None:
                label_widget.setVisible(visible)
            field_widget.setVisible(visible)

        def _update_mode_visibility() -> None:
            mode = str(mode_combo.currentData() or "basic")
            is_basic = mode == "basic"
            is_adv_tag = mode == "advanced_tag"
            is_adv_nt = mode == "advanced_notetype"
            is_card_target = str(target_mode_combo.currentData() or "note") == "card"
            _set_form_row_visible(source_tag_edit, is_basic)
            _set_form_row_visible(source_tag_base_edit, is_adv_tag)
            _set_form_row_visible(separator_edit, is_adv_tag)
            _set_form_row_visible(selector_field_combo, is_adv_tag)
            _set_form_row_visible(source_note_type_combo, is_adv_nt)
            _set_form_row_visible(target_mode_combo, is_adv_nt)
            _set_form_row_visible(mapping_field_combo, is_adv_nt and is_card_target)
            _set_form_row_visible(source_templates_combo, is_adv_nt and is_card_target)
            _set_form_row_visible(target_cond_scroll, not is_basic)
            _set_form_row_visible(source_cond_scroll, not is_basic)
            _set_form_row_visible(mapping_scroll, is_adv_nt and is_card_target)

        def _refresh_target_template_options() -> None:
            selected_templates = _checked_items(target_templates_model)
            selected_target_nts = _checked_items(target_note_types_model)
            items = _template_items_for_note_types(
                selected_target_nts,
                extra_values=selected_templates,
            )
            _fill_checkable_model(target_templates_model, items, selected_templates)
            _sync_checkable_combo_text(target_templates_combo, target_templates_model)

        def _refresh_source_template_options() -> None:
            selected_templates = _checked_items(source_templates_model)
            src_nt = str(_combo_value(source_note_type_combo) or "").strip()
            items = _template_items_for_note_types([src_nt], extra_values=selected_templates)
            _fill_checkable_model(source_templates_model, items, selected_templates)
            _sync_checkable_combo_text(source_templates_combo, source_templates_model)
            mapping_editor["refresh_templates"]()

        mode_idx = mode_combo.findData(str(rule.get("mode", "basic")))
        if mode_idx >= 0:
            mode_combo.setCurrentIndex(mode_idx)
        side_idx = side_combo.findData(str(rule.get("side", "both")))
        if side_idx >= 0:
            side_combo.setCurrentIndex(side_idx)
        tmode_idx = target_mode_combo.findData(str(rule.get("target_mode", "note")))
        if tmode_idx >= 0:
            target_mode_combo.setCurrentIndex(tmode_idx)
        mode_combo.currentIndexChanged.connect(lambda _i: _update_mode_visibility())
        target_mode_combo.currentIndexChanged.connect(lambda _i: _update_mode_visibility())
        target_note_types_model.itemChanged.connect(lambda _item: _refresh_target_template_options())
        source_note_type_combo.currentIndexChanged.connect(lambda _i: _refresh_source_template_options())
        _refresh_target_template_options()
        _refresh_source_template_options()
        _update_mode_visibility()

        tab_index = mass_linker_rule_tabs.addTab(tab, _rule_title(name_edit.text(), mass_linker_rule_tabs.count()))
        mass_linker_rule_tabs.setCurrentIndex(tab_index)

        def _retitle() -> None:
            idx = mass_linker_rule_tabs.indexOf(tab)
            if idx >= 0:
                mass_linker_rule_tabs.setTabText(idx, _rule_title(name_edit.text(), idx))

        name_edit.textChanged.connect(lambda _t: _retitle())

        rule_widgets[tab] = {
            "id": rule_id,
            "name_edit": name_edit,
            "enabled_cb": enabled_cb,
            "group_name_edit": group_name_edit,
            "mode_combo": mode_combo,
            "side_combo": side_combo,
            "source_label_field_combo": source_label_field_combo,
            "target_note_types_model": target_note_types_model,
            "target_templates_model": target_templates_model,
            "source_tag_edit": source_tag_edit,
            "source_tag_base_edit": source_tag_base_edit,
            "separator_edit": separator_edit,
            "selector_field_combo": selector_field_combo,
            "source_note_type_combo": source_note_type_combo,
            "target_mode_combo": target_mode_combo,
            "mapping_field_combo": mapping_field_combo,
            "source_templates_model": source_templates_model,
            "target_cond_editor": target_cond_editor,
            "source_cond_editor": source_cond_editor,
            "mapping_editor": mapping_editor,
        }

    initial_rules = _rule_tabs()
    if not initial_rules:
        _add_rule_tab(_default_rule(0))
    else:
        for idx, rule in enumerate(initial_rules):
            if not isinstance(rule, dict):
                continue
            merged = _default_rule(idx)
            merged.update(rule)
            _add_rule_tab(merged)

    def _add_new_rule() -> None:
        _add_rule_tab(_default_rule(mass_linker_rule_tabs.count()))

    def _remove_current_rule() -> None:
        idx = mass_linker_rule_tabs.currentIndex()
        if idx < 0:
            return
        tab = mass_linker_rule_tabs.widget(idx)
        mass_linker_rule_tabs.removeTab(idx)
        if tab is not None:
            rule_widgets.pop(tab, None)
            tab.deleteLater()
        if mass_linker_rule_tabs.count() == 0:
            _add_new_rule()

    add_rule_btn.clicked.connect(_add_new_rule)
    remove_rule_btn.clicked.connect(_remove_current_rule)

    ctx.add_tab(mass_linker_tab, "Mass Linker")

    def _save(cfg: dict, errors: list[str]) -> None:
        rules_out: list[dict[str, Any]] = []
        for i in range(mass_linker_rule_tabs.count()):
            tab = mass_linker_rule_tabs.widget(i)
            if tab is None:
                continue
            widgets = rule_widgets.get(tab)
            if not isinstance(widgets, dict):
                continue
            mode = str(widgets["mode_combo"].currentData() or "basic")
            side = str(widgets["side_combo"].currentData() or "both")
            rule_out: dict[str, Any] = {
                "id": str(widgets.get("id") or f"rule_{i + 1}"),
                "name": str(widgets["name_edit"].text() or "").strip() or f"Rule {i + 1}",
                "enabled": bool(widgets["enabled_cb"].isChecked()),
                "group_name": str(widgets["group_name_edit"].text() or "").strip() or "Mass Linker",
                "mode": mode,
                "side": side,
                "target_mode": str(widgets["target_mode_combo"].currentData() or "note"),
                "source_label_field": str(_combo_value(widgets["source_label_field_combo"]) or "").strip(),
                "target_note_types": _checked_items(widgets["target_note_types_model"]),
                "target_templates": _checked_items(widgets["target_templates_model"]),
                "target_conditions": widgets["target_cond_editor"]["collect"](),
                "source_conditions": widgets["source_cond_editor"]["collect"](),
                "source_tag": str(widgets["source_tag_edit"].text() or "").strip(),
                "source_tag_base": str(widgets["source_tag_base_edit"].text() or "").strip(),
                "selector_separator": str(widgets["separator_edit"].text() or "::"),
                "selector_field": str(_combo_value(widgets["selector_field_combo"]) or "").strip(),
                "source_note_type": str(_combo_value(widgets["source_note_type_combo"]) or "").strip(),
                "mapping_field": str(_combo_value(widgets["mapping_field_combo"]) or "").strip(),
                "source_templates": _checked_items(widgets["source_templates_model"]),
                "source_template_mappings": widgets["mapping_editor"]["collect"](),
            }
            if mode == "basic":
                rule_out["target_conditions"] = []
                rule_out["source_conditions"] = []

            if mass_linker_enabled_cb.isChecked() and bool(rule_out.get("enabled", True)):
                if side not in ("front", "back", "both"):
                    errors.append(f"Mass Linker: invalid side in rule '{rule_out['name']}'")
                if mode == "basic" and not str(rule_out.get("source_tag", "")).strip():
                    errors.append(f"Mass Linker: basic rule '{rule_out['name']}' needs a source tag")
                if mode == "advanced_tag" and not str(rule_out.get("source_tag_base", "")).strip():
                    errors.append(f"Mass Linker: advanced tag rule '{rule_out['name']}' needs a tag base")
                if mode == "advanced_notetype" and not str(rule_out.get("source_note_type", "")).strip():
                    errors.append(f"Mass Linker: advanced notetype rule '{rule_out['name']}' needs source note type")

            rules_out.append(rule_out)

        config._cfg_set(cfg, "mass_linker.enabled", bool(mass_linker_enabled_cb.isChecked()))
        config._cfg_set(cfg, "mass_linker.rules", rules_out)

    return _save


def _init() -> None:
    from . import link_core

    link_core.install_link_core()
    link_core.register_provider("mass_linker", _mass_link_provider, order=100, name="Mass Linker")
    _install_mass_linker_ui_hooks()


MODULE = ModuleSpec(
    id="mass_linker",
    label="Mass Linker",
    order=60,
    init=_init,
    build_settings=_build_settings,
)


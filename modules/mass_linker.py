from __future__ import annotations

import json
import os
import re
import time
import traceback
import unicodedata
from dataclasses import dataclass
from typing import Any

from anki.cards import Card
from aqt import gui_hooks, mw
from aqt.browser.previewer import Previewer
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

from . import ModuleSpec
from ._link_renderer import (
    convert_links as _convert_links,
    existing_link_targets as _existing_link_targets,
    wrap_anl_links as _wrap_anl_links,
)

ADDON_DIR = os.path.dirname(os.path.dirname(__file__))
CONFIG_PATH = os.path.join(ADDON_DIR, "config.json")

CFG: dict[str, Any] = {}
DEBUG = False
NOTE_LINKER_ENABLED = True
NOTE_LINKER_RULES: dict[str, Any] = {}
NOTE_LINKER_COPY_LABEL_FIELD = ""

FAMILY_LINK_ENABLED = False
FAMILY_LINK_CSS_SELECTOR = ""
FAMILY_FIELD = "FamilyID"
FAMILY_SEP = ";"
FAMILY_DEFAULT_PRIO = 0


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
    global NOTE_LINKER_ENABLED, NOTE_LINKER_RULES, NOTE_LINKER_COPY_LABEL_FIELD
    global FAMILY_LINK_ENABLED, FAMILY_LINK_CSS_SELECTOR, FAMILY_FIELD, FAMILY_SEP, FAMILY_DEFAULT_PRIO

    CFG = _load_config()

    _dbg = CFG.get("debug", {})
    if isinstance(_dbg, dict):
        DEBUG = bool(_dbg.get("enabled", False))
    else:
        DEBUG = bool(_dbg)

    NOTE_LINKER_ENABLED = bool(cfg_get("note_linker.enabled", True))
    NOTE_LINKER_RULES = cfg_get("note_linker.rules", {}) or {}
    NOTE_LINKER_COPY_LABEL_FIELD = str(cfg_get("note_linker.copy_label_field", "")).strip()

    FAMILY_LINK_ENABLED = bool(cfg_get("family_gate.link_family_member", False))
    FAMILY_LINK_CSS_SELECTOR = str(cfg_get("family_gate.link_css_selector", "")).strip()
    FAMILY_FIELD = str(cfg_get("family_gate.family.field", "FamilyID"))
    FAMILY_SEP = str(cfg_get("family_gate.family.separator", ";"))
    FAMILY_DEFAULT_PRIO = int(cfg_get("family_gate.family.default_prio", 0))

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
            NOTE_LINKER_RULES = _map_dict_keys(col, NOTE_LINKER_RULES)


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
    if not config.DEBUG:
        return

    try:
        ts = time.strftime("%H:%M:%S")
    except Exception:
        ts = ""

    line = " ".join(str(x) for x in a)
    msg = f"[MassLinker {ts}] {line}"

    try:
        import threading

        if mw is not None and threading.current_thread() is not threading.main_thread():
            mw.taskman.run_on_main(lambda m=msg: print(m, flush=True))
        else:
            print(msg, flush=True)
    except Exception:
        try:
            print(msg, flush=True)
        except Exception:
            pass

    try:
        with open(DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(msg + "\n")
    except Exception:
        pass


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


def _anki_quote(s: str) -> str:
    return (s or "").replace("\\", "\\\\").replace('"', '\\"')


@dataclass(frozen=True)
class FamilyRef:
    fid: str
    prio: int


def parse_family_field(raw: str) -> list[FamilyRef]:
    out: list[FamilyRef] = []
    if not raw:
        return out

    for part in raw.split(config.FAMILY_SEP):
        p = part.strip()
        if not p:
            continue
        if "@" in p:
            left, right = p.rsplit("@", 1)
            fid = unicodedata.normalize("NFC", left.strip())
            if not fid:
                continue
            try:
                prio = int(right.strip())
            except Exception:
                prio = config.FAMILY_DEFAULT_PRIO
            out.append(FamilyRef(fid=fid, prio=prio))
        else:
            fid = unicodedata.normalize("NFC", p)
            if fid:
                out.append(FamilyRef(fid=fid, prio=config.FAMILY_DEFAULT_PRIO))

    return out

_VOID_TAGS = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}


def _is_note_linker_installed() -> bool:
    if mw is None or not getattr(mw, "addonManager", None):
        return False
    try:
        mgr = mw.addonManager
        if hasattr(mgr, "all_addon_meta"):
            for meta in mgr.all_addon_meta():
                if getattr(meta, "dir_name", None) == "1077002392" and getattr(
                    meta, "enabled", True
                ):
                    return True
            return False
        if hasattr(mgr, "allAddons"):
            return "1077002392" in set(mgr.allAddons() or [])
    except Exception:
        return False
    return False


def _note_type_name_from_id(note_type_id: str) -> str:
    if mw is None or not getattr(mw, "col", None):
        return note_type_id
    try:
        mid = int(str(note_type_id))
    except Exception:
        return note_type_id
    model = mw.col.models.get(mid)
    if not model:
        return note_type_id
    return str(model.get("name", note_type_id))


def _note_type_rules() -> dict[str, dict[str, Any]]:
    raw = config.NOTE_LINKER_RULES
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


def _template_html(card: Card, kind: str) -> str:
    if mw is None or not getattr(mw, "col", None):
        return ""
    try:
        model = mw.col.models.get(card.note().mid)
        tmpls = model.get("tmpls", []) if model else []
        ord_val = getattr(card, "ord", None)
        if ord_val is None or ord_val >= len(tmpls):
            return ""
        tmpl = tmpls[ord_val]
        if not isinstance(tmpl, dict):
            return ""
        is_question = "Question" in kind
        key = "qfmt" if is_question else "afmt"
        return str(tmpl.get(key, "") or "")
    except Exception:
        return ""


def _derive_parent_selector(template_html: str, field_name: str) -> tuple[str, str] | None:
    if not template_html or not field_name:
        return None
    field_re = re.compile(r"{{[^}]*\b" + re.escape(field_name) + r"\b[^}]*}}")
    tag_re = re.compile(r"<[^>]+>")

    stack: list[str] = []
    pos = 0
    for m in tag_re.finditer(template_html):
        text_segment = template_html[pos : m.start()]
        if field_re.search(text_segment):
            if stack:
                return _selector_from_tag(stack[-1])
            return None
        tag = m.group(0)
        pos = m.end()
        if tag.startswith("<!--"):
            continue
        if tag.startswith("</"):
            tag_name = re.sub(r"[</>\s].*", "", tag[2:]).lower()
            while stack:
                open_tag = stack.pop()
                open_name = re.sub(r"[<\s].*", "", open_tag[1:]).lower()
                if open_name == tag_name:
                    break
            continue
        tag_name = re.sub(r"[<>\s].*", "", tag[1:]).lower()
        is_self = tag.endswith("/>") or tag_name in _VOID_TAGS
        if not is_self:
            stack.append(tag)

    if field_re.search(template_html[pos:]):
        if stack:
            return _selector_from_tag(stack[-1])
    return None


def _selector_from_tag(tag: str) -> tuple[str, str] | None:
    if not tag:
        return None
    m = re.search(r'\bid=["\']([^"\']+)["\']', tag, re.IGNORECASE)
    if m:
        return ("id", m.group(1))
    m = re.search(r'\bclass=["\']([^"\']+)["\']', tag, re.IGNORECASE)
    if m:
        first_class = (m.group(1).strip().split() or [""])[0]
        if first_class:
            return ("class", first_class)
    return None


def _note_field_value(note, field_name: str) -> str:
    if not field_name:
        return ""
    if field_name not in note:
        return ""
    return str(note[field_name] or "")


def _label_for_note(note, label_field: str) -> str:
    if label_field and label_field in note:
        return str(note[label_field] or "")
    # fallback: first field
    try:
        return str(note.fields[0] or "")
    except Exception:
        return ""


def _parse_simple_selector(selector: str) -> tuple[str, str] | None:
    s = (selector or "").strip()
    if not s:
        return None
    if s.startswith("./"):
        s = s[2:].strip()
    if s.startswith("#") and len(s) > 1:
        return ("id", s[1:])
    if s.startswith(".") and len(s) > 1:
        return ("class", s[1:])
    if re.match(r"^[A-Za-z][A-Za-z0-9_-]*$", s):
        return ("tag", s)
    return None


def _inject_links_by_selector(html: str, rendered: str, selector: str) -> str:
    if not rendered:
        return html
    sel = _parse_simple_selector(selector)
    if not sel:
        _dbg("inject: selector invalid", selector)
        return html + rendered

    sel_type, sel_value = sel
    if sel_type == "id":
        pat = re.compile(
            rf'(<[^>]*\bid=["\']{re.escape(sel_value)}["\'][^>]*>)',
            re.IGNORECASE,
        )
    elif sel_type == "class":
        pat = re.compile(
            rf'(<[^>]*\bclass=["\'][^"\']*\b{re.escape(sel_value)}\b[^"\']*["\'][^>]*>)',
            re.IGNORECASE,
        )
    else:
        pat = re.compile(rf"(<{re.escape(sel_value)}\b[^>]*>)", re.IGNORECASE)

    m = pat.search(html)
    if m:
        _dbg("inject: matched selector", selector)
        return html[: m.end(1)] + rendered + html[m.end(1) :]

    _dbg("inject: selector not found", selector)
    return html + rendered
def _family_find_nids(field: str, fid: str) -> list[int]:
    if not field or not fid:
        return []
    pattern = ".*" + re.escape(fid) + ".*"
    q = f"{field}:re:{pattern}"
    try:
        return list(mw.col.find_notes(q))
    except Exception:
        _dbg("family link search failed", q)
        return []


def _html_attr_value(value: str) -> str:
    return (value or "").replace("&", "&amp;").replace('"', "&quot;")


def _note_sort_field_value(note) -> str:
    if mw is None or not getattr(mw, "col", None):
        return ""
    try:
        model = mw.col.models.get(note.mid)
    except Exception:
        model = None
    if not model:
        return ""
    sortf = model.get("sortf")
    try:
        idx = int(sortf)
    except Exception:
        return ""
    try:
        fields = getattr(note, "fields", None)
        if not fields or idx < 0 or idx >= len(fields):
            return ""
        return str(fields[idx] or "")
    except Exception:
        return ""


@dataclass
class _FamilyLinkGroup:
    fid: str
    primary: list[str]
    secondary: list[str]


def _family_links_for_note(
    note,
    existing_nids: set[int],
    existing_cids: set[int],
) -> list[_FamilyLinkGroup]:
    if mw is None or not getattr(mw, "col", None):
        return []
    field = str(config.FAMILY_FIELD or "").strip()
    if not field or field not in note:
        return []

    refs = parse_family_field(str(note[field] or ""))
    fids: list[str] = []
    seen_fids: set[str] = set()
    for r in refs:
        fid = r.fid
        if not fid or fid in seen_fids:
            continue
        seen_fids.add(fid)
        fids.append(fid)
    if not fids:
        return []

    label_field = str(config.NOTE_LINKER_COPY_LABEL_FIELD or "").strip()

    groups: list[_FamilyLinkGroup] = []
    seen_nids: set[int] = set(existing_nids or set())
    seen_cids: set[int] = set(existing_cids or set())

    for fid in fids:
        primary_links: list[str] = []
        secondary_links: list[str] = []
        seen: set[int] = set()
        nids = _family_find_nids(field, fid)
        if not nids:
            continue

        for nid in nids:
            if nid == note.id or nid in seen or nid in seen_nids:
                continue
            try:
                other = mw.col.get_note(nid)
            except Exception:
                continue
            if field not in other:
                continue
            if seen_cids:
                try:
                    if any(c.id in seen_cids for c in other.cards()):
                        continue
                except Exception:
                    pass
            other_refs = parse_family_field(str(other[field] or ""))
            if not any(r.fid == fid for r in other_refs):
                continue

            label = _label_for_note(other, label_field).strip() or f"nid{nid}"
            label = label.replace("[", "\\[")
            link = f"[{label}|nid{nid}]"
            if _note_sort_field_value(other) == fid:
                primary_links.append(link)
            else:
                secondary_links.append(link)
            seen.add(nid)
            seen_nids.add(nid)
            try:
                for c in other.cards():
                    seen_cids.add(c.id)
            except Exception:
                pass

        groups.append(
            _FamilyLinkGroup(
                fid=fid,
                primary=primary_links,
                secondary=secondary_links,
            )
        )

    return groups


def _copy_note_link_for_browser(browser) -> None:
    if mw is None or not getattr(mw, "col", None):
        tooltip("No collection loaded")
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
        tooltip("No note selected")
        return
    nid = int(nids[0])
    try:
        note = mw.col.get_note(nid)
    except Exception:
        tooltip("Note not found")
        return

    label_field = str(config.NOTE_LINKER_COPY_LABEL_FIELD or "").strip()
    label = _label_for_note(note, label_field).strip()
    label = label.replace("[", "\\[").replace("]", "\\]")
    link = f"[{label}|nid{nid}]"
    try:
        QApplication.clipboard().setText(link)
        tooltip("Copied note link")
        _dbg("browser copy", nid, "label_field", label_field)
    except Exception:
        tooltip("Failed to copy note link")


def _browser_context_menu(browser, menu, *_args) -> None:
    try:
        action = QAction("Copy current note link and label", menu)
        action.triggered.connect(lambda: _copy_note_link_for_browser(browser))
        menu.addAction(action)
    except Exception:
        return


def _links_for_tag(tag: str, label_field: str) -> list[str]:
    if mw is None or not getattr(mw, "col", None):
        return []
    if not tag:
        return []
    try:
        nids = mw.col.find_notes(f"tag:{tag}")
    except Exception:
        return []
    _dbg("tag search", tag, "matches", len(nids))
    links: list[str] = []
    for nid in nids:
        try:
            note = mw.col.get_note(nid)
        except Exception:
            continue
        label = _label_for_note(note, label_field)
        label = label.replace("[", "\\[")
        links.append(f"[{label}|nid{nid}]")
    return links


def _inject_links_into_field(
    html: str,
    field_value: str,
    rendered: str,
    field_name: str,
    parent_selector: tuple[str, str] | None,
) -> str:
    if not rendered:
        return html
    if field_value and field_value in html:
        _dbg("inject: matched field value", field_name)
        return html.replace(field_value, rendered + field_value, 1)

    marker = f"<!--AJPC:{field_name}-->" if field_name else ""
    if marker and marker in html:
        _dbg("inject: matched marker", marker)
        return html.replace(marker, rendered, 1)

    if parent_selector:
        sel_type, sel_value = parent_selector
        if sel_type == "id":
            id_pat = re.compile(
                rf'(<[^>]*\bid=["\']{re.escape(sel_value)}["\'][^>]*>)',
                re.IGNORECASE,
            )
            m = id_pat.search(html)
            if m:
                _dbg("inject: matched parent id", sel_value)
                return html[: m.end(1)] + rendered + html[m.end(1) :]
        elif sel_type == "class":
            class_pat = re.compile(
                rf'(<[^>]*\bclass=["\'][^"\']*\b{re.escape(sel_value)}\b[^"\']*["\'][^>]*>)',
                re.IGNORECASE,
            )
            m = class_pat.search(html)
            if m:
                _dbg("inject: matched parent class", sel_value)
                return html[: m.end(1)] + rendered + html[m.end(1) :]

    if field_name:
        escaped = re.escape(field_name)
        id_pat = re.compile(rf'(<[^>]*\bid=["\']{escaped}["\'][^>]*>)', re.IGNORECASE)
        m = id_pat.search(html)
        if m:
            _dbg("inject: matched id", field_name)
            return html[: m.end(1)] + rendered + html[m.end(1) :]

        class_pat = re.compile(
            rf'(<[^>]*\bclass=["\'][^"\']*\b{escaped}\b[^"\']*["\'][^>]*>)',
            re.IGNORECASE,
        )
        m = class_pat.search(html)
        if m:
            _dbg("inject: matched class", field_name)
            return html[: m.end(1)] + rendered + html[m.end(1) :]

    _dbg("inject: appended")
    return html + rendered


def _render_auto_links(card: Card, kind: str, html: str) -> str:
    if not config.NOTE_LINKER_ENABLED:
        return html
    if mw is None or not getattr(mw, "col", None):
        return html

    note = card.note()
    nt_id = str(note.mid)
    rules = _note_type_rules()
    rule = rules.get(nt_id)
    if not rule:
        _dbg("no rule for note type", nt_id, _note_type_name_from_id(nt_id))
        return html

    side = str(rule.get("side", "both")).lower()
    if kind == "reviewQuestion" and side not in ("front", "both"):
        _dbg("skip side front", side)
        return html
    if kind != "reviewQuestion" and side not in ("back", "both"):
        _dbg("skip side back", side)
        return html

    wanted_templates = {str(x) for x in (rule.get("templates") or []) if str(x).strip()}
    tmpl_ord = _template_ord(card)
    if wanted_templates and tmpl_ord not in wanted_templates:
        _dbg("template ord not in set", tmpl_ord, "wanted", wanted_templates)
        return html

    tag = str(rule.get("tag", "")).strip()
    if not tag:
        _dbg("missing tag for note type", nt_id, _note_type_name_from_id(nt_id))
        return html

    label_field = str(rule.get("label_field", "")).strip()
    target_field = str(rule.get("target_field", "")).strip()

    links = _links_for_tag(tag, label_field)
    if not links:
        _dbg("no links for tag", tag)
        return html

    # build raw ANL-style link tags so ANL can still convert them
    rendered_links = '<div class="ajpc-auto-links">' + " ".join(links) + "</div>"
    _dbg("auto links injected", len(links), "tag", tag)

    field_value = _note_field_value(note, target_field)
    template_html = _template_html(card, kind)
    parent_selector = _derive_parent_selector(template_html, target_field)
    if parent_selector:
        _dbg("derived parent selector", parent_selector)
    return _inject_links_into_field(
        html, field_value, rendered_links, target_field, parent_selector
    )


def _render_family_links(card: Card, kind: str, html: str) -> str:
    if not config.FAMILY_LINK_ENABLED:
        return html
    if mw is None or not getattr(mw, "col", None):
        return html
    selector = str(config.FAMILY_LINK_CSS_SELECTOR or "").strip()
    if not selector:
        _dbg("family links: selector missing")
        return html

    note = card.note()
    existing_nids, existing_cids = _existing_link_targets(html)
    groups = _family_links_for_note(note, existing_nids, existing_cids)
    if not groups:
        _dbg("family links: none")
        return html

    rendered_blocks: list[str] = []
    total_links = 0
    total_details = 0
    for grp in groups:
        links = list(grp.primary or []) + list(grp.secondary or [])
        if not links:
            continue
        total_links += len(links)
        fid_attr = _html_attr_value(grp.fid)

        summary = ""
        body_links: list[str] = []

        if grp.primary:
            summary = f"<summary>{grp.primary[0]}</summary>"
            body_links = list(grp.primary[1:] + grp.secondary)
        else:
            summary = (
                f"<summary><div class=\"link\">{_html_attr_value(grp.fid)}</div></summary>"
            )
            body_links = list(grp.secondary)

        details_html = "<details>" + summary
        if body_links:
            details_html += " ".join(body_links)
        details_html += "</details>"
        total_details += 1

        rendered_blocks.append(
            f'<div class="ajpc-auto-links ajpc-family-links" data-familyid="{fid_attr}">' +
            details_html +
            "</div>"
        )

    rendered_links = "".join(rendered_blocks)
    _dbg(
        "family links injected",
        total_links,
        "families",
        len(rendered_blocks),
        "details",
        total_details,
        "selector",
        selector,
    )
    return _inject_links_by_selector(html, rendered_links, selector)


def _handle_pycmd(handled: tuple[bool, Any], message: str, context: Any):
    if not isinstance(message, str):
        return handled
    if message.startswith("AJPCNoteLinker-openPreview"):
        nid = message[len("AJPCNoteLinker-openPreview") :]
        if not nid.isdigit():
            return True, None
        try:
            note = mw.col.get_note(int(nid))
        except Exception:
            tooltip("Linked note not found")
            return True, None
        cards = note.cards()
        if not cards:
            tooltip("Linked note has no cards")
            return True, None
        card = cards[0]

        class _SingleCardPreviewer(Previewer):
            def __init__(self, card: Card, mw, on_close):
                self._card = card
                super().__init__(parent=None, mw=mw, on_close=on_close)

            def card(self) -> Card | None:
                return self._card

            def card_changed(self) -> bool:
                return False

        previewers = getattr(mw, "_ajpc_note_linker_previewers", None)
        if not isinstance(previewers, list):
            previewers = []
            mw._ajpc_note_linker_previewers = previewers

        previewer: _SingleCardPreviewer | None = None

        def _on_close() -> None:
            if previewer in previewers:
                previewers.remove(previewer)

        previewer = _SingleCardPreviewer(card, mw, _on_close)
        previewers.append(previewer)
        previewer.open()
        return True, None
    if message.startswith("AJPCNoteLinker-openEditor"):
        nid = message[len("AJPCNoteLinker-openEditor") :]
        if not nid.isdigit():
            return True, None
        try:
            from aqt import dialogs
            from aqt.editor import Editor
            from anki.notes import NoteId

            ed = dialogs.open("EditCurrent", mw, NoteId(int(nid)))
            if isinstance(ed, Editor):
                ed.activateWindow()
        except Exception:
            tooltip("Failed to open note")
        return True, None
    return handled


def _inject_auto_links(text: str, card: Card, kind: str) -> str:
    try:
        config.reload_config()
    except Exception:
        pass
    if not config.NOTE_LINKER_ENABLED and not config.FAMILY_LINK_ENABLED:
        return text
    html = _render_auto_links(card, kind, text)
    html = _render_family_links(card, kind, html)
    _dbg(
        "inject",
        "card",
        getattr(card, "id", None),
        "kind",
        kind,
    )
    return html


def _postprocess_links(text: str, card: Card, kind: str) -> str:
    html = text
    anl_installed = _is_note_linker_installed()
    _dbg(
        "render",
        "card",
        getattr(card, "id", None),
        "kind",
        kind,
        "anl",
        anl_installed,
        "auto",
        config.NOTE_LINKER_ENABLED,
    )
    if anl_installed:
        html, wrapped = _wrap_anl_links(html)
        if wrapped:
            _dbg("anl wrapped", wrapped)
    else:
        html, converted = _convert_links(html, use_anl=False)
        if converted:
            _dbg("fallback converted", converted)
    return html


def install_note_linker() -> None:
    if mw is None:
        _dbg("install skipped: no mw")
        return
    if getattr(mw, "_ajpc_note_linker_installed", False):
        _dbg("install skipped: already installed")
        return
    hooks = gui_hooks.card_will_show
    try:
        hooks._hooks.insert(0, _inject_auto_links)
    except Exception:
        hooks.append(_inject_auto_links)
    hooks.append(_postprocess_links)
    gui_hooks.webview_did_receive_js_message.append(_handle_pycmd)
    gui_hooks.browser_will_show_context_menu.append(_browser_context_menu)
    mw._ajpc_note_linker_installed = True
    _dbg("installed hooks")


def _build_settings(ctx):
    note_linker_tab = QWidget()
    note_linker_layout = QVBoxLayout()
    note_linker_tab.setLayout(note_linker_layout)
    note_linker_tabs = QTabWidget()
    note_linker_layout.addWidget(note_linker_tabs)

    general_tab = QWidget()
    general_layout = QVBoxLayout()
    general_tab.setLayout(general_layout)
    note_linker_form = QFormLayout()
    general_layout.addLayout(note_linker_form)

    note_linker_enabled_cb = QCheckBox()
    note_linker_enabled_cb.setChecked(config.NOTE_LINKER_ENABLED)
    note_linker_form.addRow("Enabled", note_linker_enabled_cb)

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

    note_linker_tabs.addTab(general_tab, "General")

    rules_tab = QWidget()
    rules_layout = QVBoxLayout()
    rules_tab.setLayout(rules_layout)

    note_linker_rules_empty_label = QLabel("Select note types in General tab.")
    rules_layout.addWidget(note_linker_rules_empty_label)

    note_linker_rule_tabs = QTabWidget()
    rules_layout.addWidget(note_linker_rule_tabs)

    note_linker_tabs.addTab(rules_tab, "Rules")

    note_linker_state: dict[str, dict[str, str | list[str]]] = {}
    for nt_id, nt_cfg in (config.NOTE_LINKER_RULES or {}).items():
        if isinstance(nt_cfg, dict):
            templates = [
                _template_ord_from_value(str(nt_id), x) or str(x).strip()
                for x in (nt_cfg.get("templates") or [])
            ]
            templates = [t for t in templates if t]
            note_linker_state[str(nt_id)] = {
                "target_field": str(nt_cfg.get("target_field", "")).strip(),
                "templates": templates,
                "side": str(nt_cfg.get("side", "both")).lower().strip() or "both",
                "tag": str(nt_cfg.get("tag", "")).strip(),
                "label_field": str(nt_cfg.get("label_field", "")).strip(),
            }

    note_linker_note_type_widgets: dict[str, dict[str, object]] = {}

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
        while note_linker_rule_tabs.count():
            w = note_linker_rule_tabs.widget(0)
            note_linker_rule_tabs.removeTab(0)
            if w is not None:
                w.deleteLater()

    def _refresh_note_linker_rules() -> None:
        _capture_note_linker_state()
        _clear_note_linker_layout()
        note_linker_note_type_widgets.clear()

        selected_types = _checked_items(note_linker_note_type_model)
        note_linker_rules_empty_label.setVisible(not bool(selected_types))
        note_linker_rule_tabs.setVisible(bool(selected_types))
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

            tab = QWidget()
            tab_layout = QVBoxLayout()
            tab.setLayout(tab_layout)

            form = QFormLayout()
            tab_layout.addLayout(form)

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

            template_items = _merge_template_items(
                _get_template_items(nt_id), list(cfg.get("templates", []) or [])
            )
            templates_combo, templates_model = _make_checkable_combo(
                template_items, list(cfg.get("templates", []) or [])
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

            tab_layout.addStretch(1)
            note_linker_rule_tabs.addTab(tab, _note_type_label(nt_id))
            note_linker_note_type_widgets[nt_id] = {
                "target_field_combo": target_field_combo,
                "label_field_combo": label_field_combo,
                "templates_model": templates_model,
                "side_combo": side_combo,
                "tag_edit": tag_edit,
            }

    _refresh_note_linker_rules()
    note_linker_note_type_model.itemChanged.connect(lambda _item: _refresh_note_linker_rules())

    ctx.add_tab(note_linker_tab, "Mass Linker")

    def _save(cfg: dict, errors: list[str]) -> None:
        _capture_note_linker_state()
        note_linker_note_types = _checked_items(note_linker_note_type_model)
        note_linker_rules_cfg: dict[str, object] = {}
        for nt_id in note_linker_note_types:
            cfg_state = note_linker_state.get(nt_id, {})
            target_field = str(cfg_state.get("target_field", "")).strip()
            templates = [
                str(x).strip() for x in (cfg_state.get("templates") or []) if str(x).strip()
            ]
            templates = [t for t in templates if t.isdigit()]
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

            payload: dict[str, object] = {}
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

        config._cfg_set(cfg, "note_linker.enabled", bool(note_linker_enabled_cb.isChecked()))
        config._cfg_set(
            cfg,
            "note_linker.copy_label_field",
            str(_combo_value(copy_label_field_combo) or "").strip(),
        )
        config._cfg_set(cfg, "note_linker.rules", note_linker_rules_cfg)

    return _save


def _init() -> None:
    install_note_linker()


MODULE = ModuleSpec(
    id="mass_linker",
    label="Mass Linker",
    order=60,
    init=_init,
    build_settings=_build_settings,
)


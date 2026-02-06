from __future__ import annotations

import json
import os
import re
import time
import traceback
import unicodedata
from dataclasses import dataclass
from typing import Any, Iterable

from anki.collection import Collection, OpChanges
from anki.errors import InvalidInput
from aqt import mw
from aqt.operations import CollectionOp
from aqt.qt import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStandardItem,
    QStandardItemModel,
    QTabWidget,
    Qt,
    QVBoxLayout,
    QWidget,
)
from aqt.utils import showInfo, show_info, tooltip

from . import ModuleSpec

ADDON_DIR = os.path.dirname(os.path.dirname(__file__))
CONFIG_PATH = os.path.join(ADDON_DIR, "config.json")

CFG: dict[str, Any] = {}
DEBUG = False
DEBUG_VERIFY_SUSPENSION = False
RUN_ON_SYNC = True
RUN_ON_UI = True
STICKY_UNLOCK = True
STABILITY_DEFAULT_THRESHOLD = 2.5
STABILITY_AGG = "min"
WATCH_NIDS: set[int] = set()

FAMILY_GATE_ENABLED = True
FAMILY_FIELD = "FamilyID"
FAMILY_SEP = ";"
FAMILY_DEFAULT_PRIO = 0
FAMILY_NOTE_TYPES: dict[str, Any] = {}
FAMILY_LINK_ENABLED = False
FAMILY_LINK_CSS_SELECTOR = ""


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
    global CFG, DEBUG, DEBUG_VERIFY_SUSPENSION
    global RUN_ON_SYNC, RUN_ON_UI, STICKY_UNLOCK
    global STABILITY_DEFAULT_THRESHOLD, STABILITY_AGG
    global WATCH_NIDS
    global FAMILY_GATE_ENABLED, FAMILY_FIELD, FAMILY_SEP, FAMILY_DEFAULT_PRIO, FAMILY_NOTE_TYPES
    global FAMILY_LINK_ENABLED, FAMILY_LINK_CSS_SELECTOR

    CFG = _load_config()

    _dbg = CFG.get("debug", {})
    if isinstance(_dbg, dict):
        DEBUG = bool(_dbg.get("enabled", False))
        DEBUG_VERIFY_SUSPENSION = bool(_dbg.get("verify_suspension", False))
    else:
        DEBUG = bool(_dbg)
        DEBUG_VERIFY_SUSPENSION = False

    try:
        WATCH_NIDS = set(
            int(x)
            for x in (cfg_get("debug.watch_nids", None) or cfg_get("debug.watch_nids", []) or [])
        )
    except Exception:
        WATCH_NIDS = set()

    RUN_ON_SYNC = bool(cfg_get("run_on_sync", True))
    RUN_ON_UI = bool(cfg_get("run_on_ui", True))
    STICKY_UNLOCK = bool(cfg_get("sticky_unlock", True))
    STABILITY_DEFAULT_THRESHOLD = float(cfg_get("stability.default_threshold", 2.5))
    STABILITY_AGG = str(cfg_get("stability.aggregation", "min")).lower().strip()

    FAMILY_GATE_ENABLED = bool(cfg_get("family_gate.enabled", True))
    FAMILY_LINK_ENABLED = bool(cfg_get("family_gate.link_family_member", False))
    FAMILY_LINK_CSS_SELECTOR = str(cfg_get("family_gate.link_css_selector", "")).strip()
    FAMILY_FIELD = str(cfg_get("family_gate.family.field", "FamilyID"))
    FAMILY_SEP = str(cfg_get("family_gate.family.separator", ";"))
    FAMILY_DEFAULT_PRIO = int(cfg_get("family_gate.family.default_prio", 0))
    FAMILY_NOTE_TYPES = cfg_get("family_gate.note_types", {}) or {}

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
            FAMILY_NOTE_TYPES = _map_dict_keys(col, FAMILY_NOTE_TYPES)


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
    msg = f"[FamilyGate {ts}] {line}"

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


DEFAULT_STICKY_TAG_BASE = "_intern::family_gate::unlocked"
DEFAULT_STAGE_TAG_PREFIX = "_intern::family_gate::unlocked::stage"
_LOGGED_TEMPLATE_MISS: set[tuple[str, int]] = set()


def stage_tag(stage_index: int) -> str:
    return f"{DEFAULT_STAGE_TAG_PREFIX}{stage_index}"


def _memory_state(card):
    try:
        ms_attr = getattr(card, "memory_state", None)
    except Exception:
        return None

    if ms_attr is None:
        return None

    try:
        return ms_attr() if callable(ms_attr) else ms_attr
    except Exception:
        return None


def card_stability(card) -> float | None:
    ms = _memory_state(card)
    stab = getattr(ms, "stability", None) if ms is not None else None
    if stab is None:
        return None
    try:
        return float(stab)
    except Exception:
        return None


def agg(vals: list[float]) -> float | None:
    if not vals:
        return None
    if config.STABILITY_AGG == "max":
        return max(vals)
    if config.STABILITY_AGG == "avg":
        return sum(vals) / len(vals)
    return min(vals)


def _dbg_card_state(card, tmpl_name: str) -> str:
    try:
        ms = _memory_state(card)
        ms_s = getattr(ms, "stability", None) if ms is not None else None
        ms_d = getattr(ms, "difficulty", None) if ms is not None else None
    except Exception as e:
        ms = None
        ms_s = None
        ms_d = None
        ms_err = repr(e)
    else:
        ms_err = ""

    try:
        return (
            f"cid={card.id} ord={getattr(card,'ord',None)} tmpl={tmpl_name!r} "
            f"queue={getattr(card,'queue',None)} type={getattr(card,'type',None)} "
            f"reps={getattr(card,'reps',None)} lapses={getattr(card,'lapses',None)} "
            f"ivl={getattr(card,'ivl',None)} due={getattr(card,'due',None)} "
            f"ms_stab={ms_s} ms_diff={ms_d}"
            + (f" ms_err={ms_err}" if ms_err else "")
        )
    except Exception as e:
        return f"cid={getattr(card,'id',None)} tmpl={tmpl_name!r} _dbg_fail={repr(e)}"


def _chunks(items: Iterable[int], size: int = 1000) -> Iterable[list[int]]:
    buf: list[int] = []
    for x in items:
        buf.append(x)
        if len(buf) >= size:
            yield buf
            buf = []
    if buf:
        yield buf


def suspend_cards(col: Collection, cids: list[int]) -> None:
    if not cids:
        return
    try:
        for chunk in _chunks(cids, 1000):
            col.sched.suspend_cards(chunk)
        return
    except Exception:
        pass

    for cid in cids:
        try:
            c = col.get_card(cid)
            if c.queue != -1:
                c.queue = -1
                col.update_card(c)
        except Exception:
            continue


def unsuspend_cards(col: Collection, cids: list[int]) -> None:
    if not cids:
        return
    try:
        for chunk in _chunks(cids, 1000):
            col.sched.unsuspend_cards(chunk)
        return
    except Exception:
        pass

    for cid in cids:
        try:
            c = col.get_card(cid)
            if c.queue == -1:
                c.queue = 0
                col.update_card(c)
        except Exception:
            continue


def _verify_suspended(col: Collection, cids: list[int], *, label: str) -> None:
    if not config.DEBUG or not config.DEBUG_VERIFY_SUSPENSION or not cids:
        return

    suspended = 0
    total = 0

    for chunk in _chunks(cids, 400):
        qmarks = ",".join(["?"] * len(chunk))
        rows = col.db.all(f"select queue from cards where id in ({qmarks})", *chunk)
        total += len(rows)
        suspended += sum(1 for (q,) in rows if q == -1)

    dbg(
        "verify",
        label,
        "targets=",
        len(cids),
        "rows=",
        total,
        "suspended_now=",
        suspended,
        "not_suspended_now=",
        total - suspended,
    )


@dataclass(frozen=True)
class StageCfg:
    templates: list[str]
    threshold: float


def get_stage_cfg_for_note_type(note_type_id: int | str) -> list[StageCfg]:
    key = str(note_type_id)
    nt = config.FAMILY_NOTE_TYPES.get(key) or {}
    if not nt and not key.isdigit():
        nt = config.FAMILY_NOTE_TYPES.get(str(note_type_id)) or {}
    stages = nt.get("stages") or []
    out: list[StageCfg] = []

    for st in stages:
        if isinstance(st, dict):
            tmpls = [
                _template_ord_from_value(str(note_type_id), x)
                for x in (st.get("templates") or [])
            ]
            tmpls = [t for t in tmpls if t]
            thr = float(st.get("threshold", config.STABILITY_DEFAULT_THRESHOLD))
            out.append(StageCfg(templates=tmpls, threshold=thr))
        elif isinstance(st, list):
            tmpls = [_template_ord_from_value(str(note_type_id), x) for x in st]
            tmpls = [t for t in tmpls if t]
            out.append(
                StageCfg(
                    templates=tmpls,
                    threshold=config.STABILITY_DEFAULT_THRESHOLD,
                )
            )

    return out


def _tmpl_by_ord(col: Collection, note) -> dict[int, str]:
    out: dict[int, str] = {}
    try:
        model = col.models.get(note.mid)
        tmpls = model.get("tmpls", [])
        for i, t in enumerate(tmpls):
            out[i] = str(t.get("name", ""))
    except Exception:
        pass
    return out


def compute_stage_stabilities(col: Collection, note, note_type_id: int | str) -> list[float | None]:
    stages = get_stage_cfg_for_note_type(note_type_id)
    if not stages:
        return []

    cards = note.cards()
    stabs: list[float | None] = []
    for st in stages:
        wanted = set(st.templates)
        vals: list[float] = []
        saw_any = False
        has_unknown = False

        for c in cards:
            if str(c.ord) in wanted:
                saw_any = True
                s = card_stability(c)
                if s is None:
                    has_unknown = True
                else:
                    vals.append(s)

        if not saw_any:
            stabs.append(None)
        elif has_unknown:
            stabs.append(None)
        else:
            stabs.append(agg(vals))

    return stabs


def stage_is_ready(note_type_id: int | str, stage_index: int, stage_stab: float | None) -> bool:
    stages = get_stage_cfg_for_note_type(note_type_id)
    if stage_index < 0 or stage_index >= len(stages):
        return False
    if stage_stab is None:
        return False
    return stage_stab >= float(stages[stage_index].threshold)


def stage_card_ids(col: Collection, note, note_type_id: int | str, stage_index: int) -> list[int]:
    stages = get_stage_cfg_for_note_type(note_type_id)
    if stage_index < 0 or stage_index >= len(stages):
        return []

    wanted = set(stages[stage_index].templates)

    cids: list[int] = []
    for c in note.cards():
        if str(c.ord) in wanted:
            cids.append(c.id)

    if config.DEBUG and not cids:
        key = (note_type_id, stage_index)
        if key not in _LOGGED_TEMPLATE_MISS:
            _LOGGED_TEMPLATE_MISS.add(key)
            avail = []
            try:
                model = col.models.get(int(str(note_type_id)))
            except Exception:
                model = None
            if model:
                tmpls = model.get("tmpls", []) if isinstance(model, dict) else []
                avail = [str(t.get("name", "")) for t in tmpls if str(t.get("name", ""))]
            dbg(
                "stage_card_ids: no cards matched stage",
                "note_type_id=",
                note_type_id,
                "stage=",
                stage_index,
                "wanted=",
                sorted(wanted),
                "available_templates=",
                avail,
            )

    return cids


def debug_template_coverage(col: Collection) -> None:
    if not config.DEBUG:
        return
    for nt_id in config.FAMILY_NOTE_TYPES.keys():
        try:
            mid = int(nt_id)
        except Exception:
            mid = None
        m = col.models.get(mid) if mid is not None else None
        if not m:
            dbg("coverage", nt_id, "model_not_found")
            continue

        tmpls = m.get("tmpls") or []
        ord_to_name: dict[str, str] = {}
        for i, t in enumerate(tmpls):
            name = str(t.get("name", "")) if isinstance(t, dict) else ""
            ord_to_name[str(i)] = name or f"<template {i}>"
        cfg_names: set[str] = set()
        for st in get_stage_cfg_for_note_type(nt_id):
            cfg_names |= set(st.templates)

        missing = [ord_to_name[k] for k in ord_to_name.keys() if k not in cfg_names]
        extra = [k for k in sorted(cfg_names) if k not in ord_to_name]

        if missing or extra:
            dbg(
                "coverage",
                nt_id,
                "missing_from_cfg=",
                [repr(x) for x in missing],
                "cfg_unknown=",
                [repr(x) for x in extra],
            )


def _anki_quote(s: str) -> str:
    return (s or "").replace("\\", "\\\\").replace('"', '\\"')


def _note_type_id_from_identifier(col: Collection, ident: Any) -> int | None:
    if ident is None:
        return None
    if isinstance(ident, int):
        return ident
    s = str(ident).strip()
    if not s:
        return None
    if s.isdigit():
        try:
            mid = int(s)
        except Exception:
            return None
        return mid
    return None


def note_ids_for_note_types(col: Collection, note_types: list[Any]) -> list[int]:
    nids: list[int] = []
    for nt in note_types:
        mid = _note_type_id_from_identifier(col, nt)
        if mid is None:
            if config.DEBUG:
                dbg("note_ids_for_note_types skipped (not an id)", nt)
            continue
        q = f"mid:{mid}"
        if config.DEBUG:
            dbg("note_ids_for_note_types", nt, "->", q)
        try:
            found = col.find_notes(q)
            if config.DEBUG:
                dbg("note_ids_for_note_types count", nt, len(found))
            nids.extend(found)
        except Exception:
            if config.DEBUG:
                dbg("note_ids_for_note_types failed", nt)
                dbg(traceback.format_exc())
            continue
    return nids


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


@dataclass
class NoteInFamily:
    nid: int
    note_type_id: int
    prio: int


def family_gate_apply(col: Collection, ui_set, counters: dict[str, int]) -> None:
    if not config.FAMILY_GATE_ENABLED:
        dbg("family_gate disabled")
        return

    note_types = list(config.FAMILY_NOTE_TYPES.keys())
    if not note_types:
        dbg("family_gate: no note_types configured")
        return

    nids = note_ids_for_note_types(col, note_types)
    dbg("family_gate: candidate notes", len(nids))
    debug_template_coverage(col)

    fam_map: dict[str, list[NoteInFamily]] = {}
    note_refs: dict[int, tuple[int, list]] = {}

    for i, nid in enumerate(nids):
        try:
            note = col.get_note(nid)
            nt_id = int(note.mid)

            if config.FAMILY_FIELD not in note:
                continue

            refs = parse_family_field(str(note[config.FAMILY_FIELD] or ""))
            if not refs:
                continue

            note_refs[nid] = (nt_id, refs)

            for r in refs:
                fam_map.setdefault(r.fid, []).append(
                    NoteInFamily(nid=nid, note_type_id=nt_id, prio=r.prio)
                )

            if i % 250 == 0:
                ui_set(
                    f"FamilyGate: index families... {i}/{len(nids)} (families={len(fam_map)})",
                    i,
                    len(nids),
                )
        except Exception:
            dbg("family_gate: exception indexing nid", nid)
            dbg(traceback.format_exc())

    dbg("family_gate: unique families", len(fam_map))

    note_stage_stabs: dict[int, list[float | None]] = {}
    note_stage0_ready: dict[int, bool] = {}

    for i, (nid, (nt_id, _refs)) in enumerate(note_refs.items()):
        try:
            note = col.get_note(nid)
            stages = get_stage_cfg_for_note_type(nt_id)
            if not stages:
                note_stage_stabs[nid] = []
                note_stage0_ready[nid] = True
                continue

            stabs = compute_stage_stabilities(col, note, nt_id)
            note_stage_stabs[nid] = stabs
            s0 = stabs[0] if stabs else None
            note_stage0_ready[nid] = stage_is_ready(nt_id, 0, s0)
        except Exception:
            note_stage_stabs[nid] = []
            note_stage0_ready[nid] = False

        if i % 400 == 0:
            ui_set(
                f"FamilyGate: compute stability... {i}/{len(note_refs)}",
                i,
                len(note_refs),
            )

    family_gate_open: dict[str, dict[int, bool]] = {}

    for fid, items in fam_map.items():
        items.sort(key=lambda x: x.prio)

        groups: list[list[NoteInFamily]] = []
        cur: list[NoteInFamily] = []
        last_prio: int | None = None
        for it in items:
            if last_prio is None or it.prio != last_prio:
                if cur:
                    groups.append(cur)
                cur = [it]
                last_prio = it.prio
            else:
                cur.append(it)
        if cur:
            groups.append(cur)

        prev_groups_ready = True

        for g_i, g_notes in enumerate(groups):
            prio = g_notes[0].prio
            gate_open = True if g_i == 0 else prev_groups_ready
            family_gate_open.setdefault(fid, {})[prio] = gate_open

            group_stage0_ready_all = True
            for ninfo in g_notes:
                group_stage0_ready_all = group_stage0_ready_all and bool(
                    note_stage0_ready.get(ninfo.nid, False)
                )

            prev_groups_ready = prev_groups_ready and group_stage0_ready_all

    to_suspend: list[int] = []
    to_unsuspend: list[int] = []

    note_items = list(note_refs.items())
    for i, (nid, (nt_id, refs)) in enumerate(note_items):
        try:
            note = col.get_note(nid)
            stages = get_stage_cfg_for_note_type(nt_id)
            if not stages:
                continue

            effective_gate_open = True
            gate_parts: list[str] = []
            for r in refs:
                ok = bool(family_gate_open.get(r.fid, {}).get(r.prio, False))
                effective_gate_open = effective_gate_open and ok
                if config.DEBUG and nid in config.WATCH_NIDS:
                    gate_parts.append(f"{r.fid}@{r.prio}={ok}")

            stabs = note_stage_stabs.get(nid, [])
            prev_stage_ok = True

            for st_idx in range(len(stages)):
                st_cids = stage_card_ids(col, note, nt_id, st_idx)
                if not st_cids:
                    continue

                should_open = effective_gate_open if st_idx == 0 else (
                    effective_gate_open and prev_stage_ok
                )

                stab_val = stabs[st_idx] if st_idx < len(stabs) else None
                this_stage_ready = stage_is_ready(nt_id, st_idx, stab_val)

                st_tag = stage_tag(st_idx)
                st_sticky = config.STICKY_UNLOCK and (st_tag in note.tags)

                if config.DEBUG and nid in config.WATCH_NIDS:
                    dbg(
                        "WATCH",
                        "nid=",
                        nid,
                        "refs=",
                        " | ".join(gate_parts),
                        "stage=",
                        st_idx,
                        "gate_all=",
                        effective_gate_open,
                        "should_open=",
                        should_open,
                        "sticky=",
                        st_sticky,
                        "ready=",
                        this_stage_ready,
                        "stab=",
                        stab_val,
                        "cids=",
                        len(st_cids),
                    )

                    cards = note.cards()
                    wanted_set = set(stages[st_idx].templates)

                    for c in cards:
                        ord_str = str(c.ord)
                        if ord_str in wanted_set:
                            tn = _tmpl_by_ord(col, note).get(c.ord) or ""
                            dbg("WATCH_CARD", "nid=", nid, _dbg_card_state(c, tn))

                if should_open or st_sticky:
                    to_unsuspend.extend(st_cids)
                    if config.STICKY_UNLOCK and this_stage_ready and st_tag not in note.tags:
                        note.add_tag(DEFAULT_STICKY_TAG_BASE)
                        note.add_tag(st_tag)
                        note.flush()
                        counters["notes_tagged"] += 1
                else:
                    to_suspend.extend(st_cids)

                prev_stage_ok = this_stage_ready

        except Exception:
            dbg("family_gate: exception applying nid", nid)
            dbg(traceback.format_exc())

        if i % 400 == 0:
            ui_set(
                f"FamilyGate: apply... {i}/{len(note_items)} | unsusp={len(to_unsuspend)} susp={len(to_suspend)}",
                i,
                len(note_items),
            )

    if to_suspend:
        sus = list(set(to_suspend))
        suspend_cards(col, sus)
        counters["cards_suspended"] += len(sus)
        _verify_suspended(col, sus, label="family_suspend")

    if to_unsuspend:
        uns = list(set(to_unsuspend))
        unsuspend_cards(col, uns)
        counters["cards_unsuspended"] += len(uns)
        _verify_suspended(col, uns, label="family_unsuspend")


def _notify_info(msg: str, *, reason: str = "manual") -> None:
    if reason == "sync":
        tooltip(msg)
    else:
        show_info(msg)


def _notify_error(msg: str, *, reason: str = "manual") -> None:
    if reason == "sync":
        tooltip(msg)
    else:
        showInfo(msg)


def run_family_gate(*, reason: str = "manual") -> None:
    config.reload_config()
    dbg(
        "reloaded config",
        "debug=",
        config.DEBUG,
        "run_on_sync=",
        config.RUN_ON_SYNC,
        "run_on_ui=",
        config.RUN_ON_UI,
    )

    if not mw or not mw.col:
        _notify_error("No collection loaded.", reason=reason)
        return

    if reason == "sync" and not config.RUN_ON_SYNC:
        dbg("family_gate: skip (run_on_sync disabled)")
        return
    if reason == "manual" and not config.RUN_ON_UI:
        dbg("family_gate: skip (run_on_ui disabled)")
        return

    def ui_set(label: str, value: int, maxv: int) -> None:
        def _do() -> None:
            try:
                if mw.progress.want_cancel():
                    dbg("family_gate: cancelled")
                    return
                mw.progress.update(label=label, value=value, max=maxv)
            except Exception:
                return

        mw.taskman.run_on_main(_do)

    def op(col: Collection):
        undo_entry = col.add_custom_undo_entry("AJpC Family Gate")

        counters = {
            "cards_suspended": 0,
            "cards_unsuspended": 0,
            "notes_tagged": 0,
        }

        ui_set("FamilyGate: start...", 0, 1)
        family_gate_apply(col, ui_set, counters)

        class _Result:
            def __init__(self, changes, counts: dict[str, int]):
                self.changes = changes
                self.counts = counts

        try:
            changes = col.merge_undo_entries(undo_entry)
        except InvalidInput:
            if config.DEBUG:
                dbg("merge_undo_entries skipped: target undo op not found", undo_entry)
            changes = OpChanges()

        if changes is None:
            changes = OpChanges()

        return _Result(changes, counters)

    def on_success(result) -> None:
        if reason == "sync":
            return
        c = getattr(result, "counts", {}) or {}
        msg = (
            "Family Gate finished.\n"
            f"unsuspended={c.get('cards_unsuspended', 0)} "
            f"suspended={c.get('cards_suspended', 0)} "
            f"tagged_notes={c.get('notes_tagged', 0)}"
        )
        if config.DEBUG:
            dbg("RESULT", msg)
        _notify_info(msg, reason=reason)

    def on_failure(err: Exception) -> None:
        tb = "".join(traceback.format_exception(type(err), err, err.__traceback__))
        if config.DEBUG:
            dbg("FAILURE", repr(err))
            dbg(tb)
        _notify_error("Family Gate failed:\n" + tb, reason=reason)

    CollectionOp(parent=mw, op=op).success(on_success).failure(on_failure).run_in_background()


def _build_settings(ctx):
    family_tab = QWidget()
    family_layout = QVBoxLayout()
    family_tab.setLayout(family_layout)
    family_tabs = QTabWidget()
    family_layout.addWidget(family_tabs)

    general_tab = QWidget()
    general_layout = QVBoxLayout()
    general_tab.setLayout(general_layout)
    family_form = QFormLayout()
    general_layout.addLayout(family_form)

    family_enabled_cb = QCheckBox()
    family_enabled_cb.setChecked(config.FAMILY_GATE_ENABLED)
    family_form.addRow("Enabled", family_enabled_cb)

    family_link_cb = QCheckBox()
    family_link_cb.setChecked(config.FAMILY_LINK_ENABLED)
    family_form.addRow("Link family member", family_link_cb)

    family_field_edit = QLineEdit()
    family_field_edit.setText(config.FAMILY_FIELD)
    family_form.addRow("Family field", family_field_edit)

    family_link_css_edit = QLineEdit()
    family_link_css_edit.setText(config.FAMILY_LINK_CSS_SELECTOR)
    family_link_css_label = QLabel("Link css selector")
    family_form.addRow(family_link_css_label, family_link_css_edit)

    def _toggle_family_link_selector() -> None:
        visible = bool(family_link_cb.isChecked())
        family_link_css_label.setVisible(visible)
        family_link_css_edit.setVisible(visible)

    family_link_cb.stateChanged.connect(lambda _=None: _toggle_family_link_selector())
    _toggle_family_link_selector()

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

    family_tabs.addTab(general_tab, "General")

    stages_tab = QWidget()
    stages_layout = QVBoxLayout()
    stages_tab.setLayout(stages_layout)

    stages_empty_label = QLabel("Select note types in General tab.")
    stages_layout.addWidget(stages_empty_label)

    family_stage_tabs = QTabWidget()
    stages_layout.addWidget(family_stage_tabs)

    family_tabs.addTab(stages_tab, "Stages")

    family_state: dict[str, list[dict]] = {}
    for nt_id, nt_cfg in (config.FAMILY_NOTE_TYPES or {}).items():
        stages = nt_cfg.get("stages") if isinstance(nt_cfg, dict) else None
        out_stages: list[dict] = []
        if isinstance(stages, list):
            for st in stages:
                if isinstance(st, dict):
                    tmpls = [
                        _template_ord_from_value(str(nt_id), x) or str(x).strip()
                        for x in (st.get("templates") or [])
                    ]
                    tmpls = [t for t in tmpls if t]
                    thr = float(st.get("threshold", config.STABILITY_DEFAULT_THRESHOLD))
                    out_stages.append({"templates": tmpls, "threshold": thr})
                elif isinstance(st, list):
                    tmpls = [
                        _template_ord_from_value(str(nt_id), x) or str(x).strip()
                        for x in st
                    ]
                    tmpls = [t for t in tmpls if t]
                    out_stages.append(
                        {"templates": tmpls, "threshold": config.STABILITY_DEFAULT_THRESHOLD}
                    )
        family_state[str(nt_id)] = out_stages

    family_note_type_widgets: dict[str, list[dict]] = {}

    def _capture_family_state() -> None:
        for nt_id, stages in family_note_type_widgets.items():
            out: list[dict] = []
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

    def _clear_family_tabs() -> None:
        while family_stage_tabs.count():
            w = family_stage_tabs.widget(0)
            family_stage_tabs.removeTab(0)
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
        _clear_family_tabs()
        family_note_type_widgets.clear()

        selected_types = _checked_items(family_note_type_model)
        stages_empty_label.setVisible(not bool(selected_types))
        family_stage_tabs.setVisible(bool(selected_types))
        for nt_id in selected_types:
            stages = family_state.get(nt_id, [])
            family_note_type_widgets[nt_id] = []

            tab = QWidget()
            tab_layout = QVBoxLayout()
            tab.setLayout(tab_layout)

            add_btn = QPushButton("Add stage")
            add_btn.clicked.connect(lambda _=None, n=nt_id: _add_family_stage(n))
            tab_layout.addWidget(add_btn)

            extra_templates: list[str] = []
            for st in stages:
                for t in st.get("templates", []) or []:
                    extra_templates.append(str(t))
            template_items = _merge_template_items(
                _get_template_items(nt_id), extra_templates
            )

            stages_scroll = QScrollArea()
            stages_scroll.setWidgetResizable(True)
            stages_container = QWidget()
            stages_container_layout = QVBoxLayout()
            stages_container.setLayout(stages_container_layout)
            stages_scroll.setWidget(stages_container)
            tab_layout.addWidget(stages_scroll)

            for idx, st in enumerate(stages):
                stage_box = QGroupBox(f"Stage {idx}")
                stage_form = QFormLayout()
                stage_box.setLayout(stage_form)

                templates_combo, templates_model = _make_checkable_combo(
                    template_items, list(st.get("templates", []) or [])
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

                stages_container_layout.addWidget(stage_box)
                family_note_type_widgets[nt_id].append(
                    {
                        "templates_model": templates_model,
                        "threshold_spin": threshold_spin,
                    }
                )

            stages_container_layout.addStretch(1)

            family_stage_tabs.addTab(tab, _note_type_label(nt_id))

    _refresh_family_stages()
    family_note_type_model.itemChanged.connect(lambda _item: _refresh_family_stages())

    ctx.add_tab(family_tab, "Family Gate")

    def _save(cfg: dict, errors: list[str]) -> None:
        fam_sep = family_sep_edit.text().strip()
        if not fam_sep:
            errors.append("Family separator cannot be empty.")

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
                tmpls = [t for t in tmpls if t.isdigit()]
                if not tmpls:
                    errors.append(
                        f"Family Gate: stage {s_idx} has no templates ({_note_type_label(nt_id)})"
                    )
                    continue
                thr = float(st.get("threshold", config.STABILITY_DEFAULT_THRESHOLD))
                stage_cfgs.append({"templates": tmpls, "threshold": thr})
            if stage_cfgs:
                family_note_types_cfg[nt_id] = {"stages": stage_cfgs}

        config._cfg_set(cfg, "family_gate.enabled", bool(family_enabled_cb.isChecked()))
        config._cfg_set(cfg, "family_gate.link_family_member", bool(family_link_cb.isChecked()))
        config._cfg_set(cfg, "family_gate.link_css_selector", family_link_css_edit.text().strip())
        config._cfg_set(cfg, "family_gate.family.field", family_field_edit.text().strip())
        config._cfg_set(cfg, "family_gate.family.separator", fam_sep)
        config._cfg_set(cfg, "family_gate.family.default_prio", int(family_prio_spin.value()))
        config._cfg_set(cfg, "family_gate.note_types", family_note_types_cfg)

    return _save


def _enabled_family() -> bool:
    return bool(config.RUN_ON_UI and config.FAMILY_GATE_ENABLED)


def _init() -> None:
    from aqt import gui_hooks, mw

    def _on_sync_finished() -> None:
        run_family_gate(reason="sync")

    if config.RUN_ON_SYNC:
        if mw is not None and not getattr(mw, "_ajpc_familygate_sync_hook_installed", False):
            gui_hooks.sync_did_finish.append(_on_sync_finished)
            mw._ajpc_familygate_sync_hook_installed = True


MODULE = ModuleSpec(
    id="family_gate",
    label="Family Gate",
    order=20,
    init=_init,
    run_items=[
        {
            "label": "Run Family Gate",
            "callback": lambda: run_family_gate(reason="manual"),
            "enabled_fn": _enabled_family,
            "order": 10,
        }
    ],
    build_settings=_build_settings,
)

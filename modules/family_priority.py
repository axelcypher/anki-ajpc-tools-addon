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
    QFormLayout,
    QFrame,
    QLabel,
    QLineEdit,
    QSpinBox,
    QStandardItem,
    QStandardItemModel,
    Qt,
    QVBoxLayout,
    QWidget,
)
from aqt.utils import tooltip

from .. import logging as core_logging
from . import ModuleSpec
from ._widgets.deck_stats_registry import count_unsuspended_cards, register_provider
from .link_core import LinkGroup, LinkPayload, LinkRef, ProviderContext, WrapperSpec

ADDON_DIR = os.path.dirname(os.path.dirname(__file__))
CONFIG_PATH = os.path.join(ADDON_DIR, "config.json")

CFG: dict[str, Any] = {}
CFG_MTIME: float | None = None
DEBUG = False
DEBUG_VERIFY_SUSPENSION = False
RUN_ON_SYNC = True
RUN_ON_UI = True
STICKY_UNLOCK = True
STABILITY_DEFAULT_THRESHOLD = 14.0
STABILITY_AGG = "min"
WATCH_NIDS: set[int] = set()

FAMILY_PRIORITY_ENABLED = True
FAMILY_FIELD = "FamilyID"
FAMILY_SEP = ";"
FAMILY_DEFAULT_PRIO = 0
FAMILY_NOTE_TYPES: dict[str, Any] = {}
FAMILY_RUN_ON_SYNC = True
FAMILY_LINK_ENABLED = False
MASS_LINKER_LABEL_FIELD = ""

FAMILY_LOOKUP_TTL_SECONDS = 10.0
FAMILY_LOOKUP_CACHE: dict[tuple[int, str, str], tuple[float, list[int]]] = {}


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
    global CFG, CFG_MTIME, DEBUG, DEBUG_VERIFY_SUSPENSION
    global RUN_ON_SYNC, RUN_ON_UI, STICKY_UNLOCK
    global STABILITY_DEFAULT_THRESHOLD, STABILITY_AGG
    global WATCH_NIDS
    global FAMILY_PRIORITY_ENABLED, FAMILY_FIELD, FAMILY_SEP, FAMILY_DEFAULT_PRIO, FAMILY_NOTE_TYPES
    global FAMILY_RUN_ON_SYNC, FAMILY_LINK_ENABLED, MASS_LINKER_LABEL_FIELD

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
    STABILITY_DEFAULT_THRESHOLD = 14.0
    STABILITY_AGG = "min"

    FAMILY_PRIORITY_ENABLED = bool(cfg_get("family_priority.enabled", True))
    FAMILY_RUN_ON_SYNC = bool(cfg_get("family_priority.run_on_sync", True))
    FAMILY_LINK_ENABLED = bool(cfg_get("family_priority.link_family_member", False))
    MASS_LINKER_LABEL_FIELD = str(
        cfg_get("mass_linker.label_field", cfg_get("mass_linker.copy_label_field", ""))
    ).strip()
    FAMILY_FIELD = str(cfg_get("family_priority.family.field", "FamilyID"))
    FAMILY_SEP = str(cfg_get("family_priority.family.separator", ";"))
    FAMILY_DEFAULT_PRIO = int(cfg_get("family_priority.family.default_prio", 0))
    FAMILY_NOTE_TYPES = cfg_get("family_priority.note_types", {}) or {}

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

    try:
        CFG_MTIME = os.path.getmtime(CONFIG_PATH)
    except Exception:
        CFG_MTIME = None


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


def _invalidate_family_lookup_cache() -> None:
    FAMILY_LOOKUP_CACHE.clear()


def _maybe_reload_config(*, force: bool = False) -> None:
    if force:
        before = CFG_MTIME
        reload_config()
        if before != CFG_MTIME:
            _invalidate_family_lookup_cache()
        return
    try:
        mtime = os.path.getmtime(CONFIG_PATH)
    except Exception:
        mtime = None
    if mtime is None:
        return
    if CFG_MTIME is None or mtime != CFG_MTIME:
        reload_config()
        _invalidate_family_lookup_cache()


def dbg(*a: Any) -> None:
    core_logging.trace(*a, source="family_priority")


def log_info(*a: Any) -> None:
    core_logging.info(*a, source="family_priority")


def log_warn(*a: Any) -> None:
    core_logging.warn(*a, source="family_priority")


def log_error(*a: Any) -> None:
    core_logging.error(*a, source="family_priority")


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


DEFAULT_STICKY_TAG_BASE = "_intern::family_priority::unlocked"


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


def _family_priority_card_ids(col: Collection, note, note_type_id: int, card_stages_mod) -> list[int]:
    try:
        cards = note.cards()
    except Exception:
        return []

    if card_stages_mod is None:
        return [int(c.id) for c in cards]

    try:
        stages = card_stages_mod.get_stage_cfg_for_note_type(note_type_id)
    except Exception:
        stages = []

    if stages:
        try:
            stabs = card_stages_mod.compute_stage_stabilities(col, note, note_type_id)
        except Exception:
            stabs = []

        out: list[int] = []
        prev_stage_ok = True
        for st_idx in range(len(stages)):
            should_open = True if st_idx == 0 else prev_stage_ok
            st_tag = None
            try:
                st_tag = card_stages_mod.stage_tag(st_idx)
            except Exception:
                st_tag = None
            st_sticky = bool(config.STICKY_UNLOCK and st_tag and (st_tag in getattr(note, "tags", [])))
            if should_open or st_sticky:
                try:
                    out.extend(
                        int(cid) for cid in card_stages_mod.stage_card_ids(note, note_type_id, st_idx)
                    )
                except Exception:
                    return [int(c.id) for c in cards]
            stab_val = stabs[st_idx] if st_idx < len(stabs) else None
            try:
                prev_stage_ok = bool(card_stages_mod.stage_is_ready(note_type_id, st_idx, stab_val))
            except Exception:
                prev_stage_ok = False

        if not out:
            return []
        # De-dupe while preserving order
        seen: set[int] = set()
        deduped: list[int] = []
        for cid in out:
            if cid in seen:
                continue
            seen.add(cid)
            deduped.append(cid)
        return deduped

    return [int(c.id) for c in cards]


def _deck_stats_provider_family_priority() -> dict[str, Any]:
    reload_config()
    enabled = bool(FAMILY_PRIORITY_ENABLED)
    tracked: set[int] = set()
    if enabled and mw is not None and getattr(mw, "col", None):
        note_types = list((FAMILY_NOTE_TYPES or {}).keys())
        nids = note_ids_for_note_types(mw.col, note_types)
        family_field = str(FAMILY_FIELD or "").strip()
        for nid in nids:
            try:
                note = mw.col.get_note(int(nid))
            except Exception:
                continue
            if not family_field or family_field not in note:
                continue
            refs = parse_family_field(str(note[family_field] or ""))
            if not refs:
                continue
            for card in note.cards():
                tracked.add(int(card.id))
    return {
        "label": "Family Priority progression",
        "enabled": enabled,
        "tracked": len(tracked),
        "free": count_unsuspended_cards(tracked),
        "order": 20,
    }


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

    sep = str(config.FAMILY_SEP or ";")
    for part in raw.split(sep):
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


def _label_for_note(note, label_field: str) -> str:
    if label_field and label_field in note:
        return str(note[label_field] or "")
    try:
        return str(note.fields[0] or "")
    except Exception:
        return ""


def _family_find_nids(field: str, fid: str) -> list[int]:
    if mw is None or not getattr(mw, "col", None):
        return []
    field_txt = str(field or "").strip()
    fid_txt = unicodedata.normalize("NFC", str(fid or "").strip())
    if not field_txt or not fid_txt:
        return []
    cache_key = (id(mw.col), field_txt, fid_txt)
    now = time.time()
    cached = FAMILY_LOOKUP_CACHE.get(cache_key)
    if cached is not None:
        ts, nids = cached
        if (now - ts) <= FAMILY_LOOKUP_TTL_SECONDS:
            return list(nids)
    field_term = f'"{field_txt}"' if " " in field_txt else field_txt
    pattern = ".*" + re.escape(fid_txt) + ".*"
    quoted_pattern = pattern.replace('"', '\\"')
    queries = [
        f'{field_term}:re:"{quoted_pattern}"',
        f"{field_term}:re:{pattern}",
    ]
    failed_queries: list[str] = []
    for q in queries:
        try:
            nids = list(mw.col.find_notes(q))
            FAMILY_LOOKUP_CACHE[cache_key] = (now, nids)
            return nids
        except Exception:
            failed_queries.append(q)
            dbg("family link search attempt failed", q)
            log_warn("family link search attempt failed", q)
    if failed_queries:
        log_error(
            "family link search failed (all attempts)",
            f"field={field_txt}",
            f"fid={fid_txt}",
            f"queries={failed_queries}",
        )
    return []


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
    primary: list[LinkRef]
    secondary: list[LinkRef]


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

    label_field = str(config.MASS_LINKER_LABEL_FIELD or "").strip()
    groups: list[_FamilyLinkGroup] = []
    seen_nids: set[int] = set(existing_nids or set())
    seen_cids: set[int] = set(existing_cids or set())

    for fid in fids:
        primary_links: list[LinkRef] = []
        secondary_links: list[LinkRef] = []
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
            link = LinkRef(label=label, kind="nid", target_id=int(nid))
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


def _family_link_provider(ctx: ProviderContext) -> list[LinkPayload]:
    _maybe_reload_config()
    if not config.FAMILY_LINK_ENABLED:
        return []
    groups = _family_links_for_note(ctx.note, ctx.existing_nids, ctx.existing_cids)
    if not groups:
        return []

    payload_groups: list[LinkGroup] = []
    for grp in groups:
        if not grp.primary and not grp.secondary:
            continue
        summary_ref: LinkRef | None = None
        secondary: list[LinkRef] = []
        if grp.primary:
            summary_ref = grp.primary[0]
            secondary.extend(grp.primary[1:])
        secondary.extend(grp.secondary)
        payload_groups.append(
            LinkGroup(
                key=grp.fid,
                summary=summary_ref,
                links=secondary,
                data_attrs={"familyid": grp.fid},
            )
        )

    if not payload_groups:
        return []

    return [
        LinkPayload(
            mode="grouped",
            wrapper=WrapperSpec(classes=["ajpc-auto-links", "ajpc-family-links"]),
            groups=payload_groups,
            order=200,
        )
    ]


@dataclass
class NoteInFamily:
    nid: int
    note_type_id: int
    prio: int


def _get_card_stages_module_if_enabled():
    try:
        from . import card_stages as card_stages_mod  # type: ignore
    except Exception:
        return None
    try:
        if not bool(getattr(card_stages_mod.config, "CARD_STAGES_ENABLED", False)):
            return None
    except Exception:
        return None
    return card_stages_mod


def compute_family_priority_open_map(
    col: Collection,
    *,
    card_stages_mod=None,
    ui_set=None,
) -> dict[int, bool] | None:
    _maybe_reload_config()
    if not config.FAMILY_PRIORITY_ENABLED:
        return None

    note_types = list(config.FAMILY_NOTE_TYPES.keys())
    if not note_types:
        return None

    nids = note_ids_for_note_types(col, note_types)
    dbg("family_priority: candidate notes", len(nids))

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

            if ui_set and i % 250 == 0:
                ui_set(
                    f"Family Priority: index families... {i}/{len(nids)} (families={len(fam_map)})",
                    i,
                    len(nids),
                )
        except Exception:
            dbg("family_priority: exception indexing nid", nid)
            dbg(traceback.format_exc())
            log_warn("family_priority: exception indexing nid", nid)

    dbg("family_priority: unique families", len(fam_map))

    note_stage0_ready: dict[int, bool] = {}
    if card_stages_mod is None:
        card_stages_mod = _get_card_stages_module_if_enabled()

    for i, (nid, (nt_id, _refs)) in enumerate(note_refs.items()):
        try:
            note = col.get_note(nid)
            if card_stages_mod is None:
                note_stage0_ready[nid] = True
            else:
                note_stage0_ready[nid] = bool(card_stages_mod.note_stage0_ready(col, note))
        except Exception:
            note_stage0_ready[nid] = False

        if ui_set and i % 400 == 0:
            ui_set(
                f"Family Priority: compute stability... {i}/{len(note_refs)}",
                i,
                len(note_refs),
            )

    family_priority_open: dict[str, dict[int, bool]] = {}

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
            family_priority_open.setdefault(fid, {})[prio] = gate_open

            group_stage0_ready_all = True
            for ninfo in g_notes:
                group_stage0_ready_all = group_stage0_ready_all and bool(
                    note_stage0_ready.get(ninfo.nid, False)
                )

            prev_groups_ready = prev_groups_ready and group_stage0_ready_all

    gate_map: dict[int, bool] = {}
    for nid, (_nt_id, refs) in note_refs.items():
        effective_gate_open = True
        for r in refs:
            ok = bool(family_priority_open.get(r.fid, {}).get(r.prio, False))
            effective_gate_open = effective_gate_open and ok
        gate_map[nid] = effective_gate_open

    return gate_map


def family_priority_apply(col: Collection, ui_set, counters: dict[str, int]) -> None:
    if not config.FAMILY_PRIORITY_ENABLED:
        log_info("family_priority disabled")
        return

    note_types = list(config.FAMILY_NOTE_TYPES.keys())
    if not note_types:
        log_warn("family_priority: no note_types configured")
        return

    _card_stages = _get_card_stages_module_if_enabled()

    gate_map = compute_family_priority_open_map(col, card_stages_mod=_card_stages, ui_set=ui_set)
    if gate_map is None:
        return

    to_suspend: list[int] = []
    to_unsuspend: list[int] = []

    note_items = list(gate_map.items())
    for i, (nid, effective_gate_open) in enumerate(note_items):
        try:
            note = col.get_note(nid)
            nt_id = int(note.mid)

            cids = _family_priority_card_ids(col, note, nt_id, _card_stages)
            if not cids:
                continue
            if effective_gate_open:
                to_unsuspend.extend(cids)
            else:
                to_suspend.extend(cids)

        except Exception:
            dbg("family_priority: exception applying nid", nid)
            dbg(traceback.format_exc())
            log_warn("family_priority: exception applying nid", nid)

        if i % 400 == 0:
            ui_set(
                f"FamilyPriority: apply... {i}/{len(note_items)} | unsusp={len(to_unsuspend)} susp={len(to_suspend)}",
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
    tooltip(msg, period=2500)


def _notify_error(msg: str, *, reason: str = "manual") -> None:
    tooltip(msg, period=2500)


def run_family_priority(*, reason: str = "manual") -> None:
    config.reload_config()
    dbg(
        "reloaded config",
        "debug=",
        config.DEBUG,
        "run_on_sync=",
        config.RUN_ON_SYNC,
        "family_run_on_sync=",
        config.FAMILY_RUN_ON_SYNC,
        "run_on_ui=",
        config.RUN_ON_UI,
    )

    if not mw or not mw.col:
        log_error("family_priority: no collection loaded")
        _notify_error("No collection loaded.", reason=reason)
        return

    if reason == "sync" and not (config.RUN_ON_SYNC and config.FAMILY_RUN_ON_SYNC):
        log_info("family_priority: skip (run_on_sync disabled)")
        return
    if reason == "manual" and not config.RUN_ON_UI:
        log_info("family_priority: skip (run_on_ui disabled)")
        return

    def ui_set(label: str, value: int, maxv: int) -> None:
        def _do() -> None:
            try:
                if mw.progress.want_cancel():
                    dbg("family_priority: cancelled")
                    return
                mw.progress.update(label=label, value=value, max=maxv)
            except Exception:
                return

        mw.taskman.run_on_main(_do)

    def op(col: Collection):
        undo_entry = col.add_custom_undo_entry("AJpC Family Priority")

        counters = {
            "cards_suspended": 0,
            "cards_unsuspended": 0,
            "notes_tagged": 0,
        }

        ui_set("FamilyPriority: start...", 0, 1)
        family_priority_apply(col, ui_set, counters)

        class _Result:
            def __init__(self, changes, counts: dict[str, int]):
                self.changes = changes
                self.counts = counts

        try:
            changes = col.merge_undo_entries(undo_entry)
        except InvalidInput:
            if config.DEBUG:
                dbg("merge_undo_entries skipped: target undo op not found", undo_entry)
            log_warn("merge_undo_entries skipped: target undo op not found", undo_entry)
            changes = OpChanges()

        if changes is None:
            changes = OpChanges()

        return _Result(changes, counters)

    def on_success(result) -> None:
        c = getattr(result, "counts", {}) or {}
        msg = (
            "Family Priority finished.\n"
            f"unsuspended={c.get('cards_unsuspended', 0)} "
            f"suspended={c.get('cards_suspended', 0)} "
            f"tagged_notes={c.get('notes_tagged', 0)}"
        )
        log_info(
            "Family Priority finished",
            f"unsuspended={c.get('cards_unsuspended', 0)}",
            f"suspended={c.get('cards_suspended', 0)}",
            f"tagged_notes={c.get('notes_tagged', 0)}",
        )
        if config.DEBUG:
            dbg("RESULT", msg)
        _notify_info(msg, reason=reason)

    def on_failure(err: Exception) -> None:
        tb = "".join(traceback.format_exception(type(err), err, err.__traceback__))
        log_error("Family Priority failed", repr(err))
        if config.DEBUG:
            dbg("FAILURE", repr(err))
            dbg(tb)
        _notify_error("Family Priority failed:\n" + tb, reason=reason)

    if reason == "sync":
        try:
            op(mw.col)
        except Exception as err:
            on_failure(err)
        return

    CollectionOp(parent=mw, op=op).success(on_success).failure(on_failure).run_in_background()


def _tip_label(text: str, tip: str) -> QLabel:
    label = QLabel(text)
    label.setToolTip(tip)
    label.setWhatsThis(tip)
    return label


def _build_settings(ctx):
    family_tab = QWidget()
    family_layout = QVBoxLayout()
    family_tab.setLayout(family_layout)
    family_form = QFormLayout()
    family_layout.addLayout(family_form)

    family_enabled_cb = QCheckBox()
    family_enabled_cb.setChecked(config.FAMILY_PRIORITY_ENABLED)
    family_form.addRow(
        _tip_label("Enabled", "Enable or disable Family Priority."),
        family_enabled_cb,
    )

    family_run_on_sync_cb = QCheckBox()
    family_run_on_sync_cb.setChecked(config.FAMILY_RUN_ON_SYNC)
    family_form.addRow(
        _tip_label("Run on sync", "Run Family Priority automatically at sync start."),
        family_run_on_sync_cb,
    )

    family_link_cb = QCheckBox()
    family_link_cb.setChecked(config.FAMILY_LINK_ENABLED)
    family_form.addRow(
        _tip_label("Link family member", "Generate family raw links for Link Core rendering."),
        family_link_cb,
    )

    separator = QFrame()
    separator.setFrameShape(QFrame.Shape.HLine)
    separator.setFrameShadow(QFrame.Shadow.Sunken)

    family_form.addWidget(separator)

    family_field_edit = QLineEdit()
    family_field_edit.setText(config.FAMILY_FIELD)
    family_form.addRow(
        _tip_label("Family field", "Field containing entries like FamilyID@prio."),
        family_field_edit,
    )

    family_sep_edit = QLineEdit()
    family_sep_edit.setText(config.FAMILY_SEP)
    family_form.addRow(
        _tip_label("Family separator", "Separator between multiple family entries in the field."),
        family_sep_edit,
    )

    family_prio_spin = QSpinBox()
    family_prio_spin.setRange(-10000, 10000)
    family_prio_spin.setValue(config.FAMILY_DEFAULT_PRIO)
    family_form.addRow(
        _tip_label("Default prio", "Priority used when '@prio' is omitted."),
        family_prio_spin,
    )

    family_note_type_items = _merge_note_type_items(
        _get_note_type_items(), list((config.FAMILY_NOTE_TYPES or {}).keys())
    )
    family_note_type_combo, family_note_type_model = _make_checkable_combo(
        family_note_type_items, list((config.FAMILY_NOTE_TYPES or {}).keys())
    )
    family_form.addRow(
        _tip_label("Note types", "Only selected note types participate in family unlock checks."),
        family_note_type_combo,
    )
    family_layout.addStretch(1)

    ctx.add_tab(family_tab, "Family Priority")

    def _save(cfg: dict, errors: list[str]) -> None:
        fam_sep = family_sep_edit.text().strip()
        if not fam_sep:
            errors.append("Family separator cannot be empty.")

        family_note_types = _checked_items(family_note_type_model)
        family_note_types_cfg: dict[str, Any] = {str(nt_id): {} for nt_id in family_note_types}

        config._cfg_set(cfg, "family_priority.enabled", bool(family_enabled_cb.isChecked()))
        config._cfg_set(cfg, "family_priority.run_on_sync", bool(family_run_on_sync_cb.isChecked()))
        config._cfg_set(cfg, "family_priority.link_family_member", bool(family_link_cb.isChecked()))
        config._cfg_set(cfg, "family_priority.family.field", family_field_edit.text().strip())
        config._cfg_set(cfg, "family_priority.family.separator", fam_sep)
        config._cfg_set(cfg, "family_priority.family.default_prio", int(family_prio_spin.value()))
        config._cfg_set(cfg, "family_priority.note_types", family_note_types_cfg)

    return _save


def _enabled_family() -> bool:
    return bool(config.RUN_ON_UI and config.FAMILY_PRIORITY_ENABLED)


def _init() -> None:
    from aqt import gui_hooks, mw
    from . import link_core

    register_provider("family_priority", _deck_stats_provider_family_priority, order=20)

    def _on_collection_changed(*_args, **_kwargs) -> None:
        _invalidate_family_lookup_cache()

    def _on_sync_start() -> None:
        _invalidate_family_lookup_cache()
        run_family_priority(reason="sync")

    link_core.install_link_core()
    link_core.register_provider("family_priority", _family_link_provider, order=200, name="Family Priority")

    if mw is not None and not getattr(mw, "_ajpc_family_priority_cache_hooks_installed", False):
        op_hook = getattr(gui_hooks, "operation_did_execute", None)
        if op_hook is not None:
            op_hook.append(_on_collection_changed)
        add_note_hook = getattr(gui_hooks, "add_cards_did_add_note", None)
        if add_note_hook is not None:
            add_note_hook.append(_on_collection_changed)
        mw._ajpc_family_priority_cache_hooks_installed = True

    if mw is not None and not getattr(mw, "_ajpc_family_priority_sync_hook_installed", False):
        gui_hooks.sync_will_start.append(_on_sync_start)
        mw._ajpc_family_priority_sync_hook_installed = True


MODULE = ModuleSpec(
    id="family_priority",
    label="Family Priority",
    order=30,
    init=_init,
    run_items=[
        {
            "label": "Run Family Priority",
            "callback": lambda: run_family_priority(reason="manual"),
            "enabled_fn": _enabled_family,
            "order": 10,
        }
    ],
    build_settings=_build_settings,
)

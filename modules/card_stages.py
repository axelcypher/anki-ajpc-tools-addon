from __future__ import annotations

import json
import os
import time
import traceback
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

ADDON_DIR = os.path.dirname(os.path.dirname(__file__))
CONFIG_PATH = os.path.join(ADDON_DIR, "config.json")

CFG: dict[str, Any] = {}
DEBUG = False
DEBUG_VERIFY_SUSPENSION = False
RUN_ON_SYNC = True
RUN_ON_UI = True
STICKY_UNLOCK = True
STABILITY_DEFAULT_THRESHOLD = 14.0
WATCH_NIDS: set[int] = set()

CARD_STAGES_ENABLED = True
CARD_STAGES_RUN_ON_SYNC = True
CARD_STAGES_NOTE_TYPES: dict[str, Any] = {}


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
    global RUN_ON_SYNC, RUN_ON_UI, STICKY_UNLOCK, STABILITY_DEFAULT_THRESHOLD
    global WATCH_NIDS
    global CARD_STAGES_ENABLED, CARD_STAGES_RUN_ON_SYNC, CARD_STAGES_NOTE_TYPES

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

    CARD_STAGES_ENABLED = bool(cfg_get("card_stages.enabled", True))
    CARD_STAGES_RUN_ON_SYNC = bool(cfg_get("card_stages.run_on_sync", True))
    CARD_STAGES_NOTE_TYPES = (
        cfg_get("card_stages.note_types", cfg_get("family_gate.note_types", {})) or {}
    )

    try:
        from aqt import mw as _mw  # type: ignore
    except Exception:
        _mw = None  # type: ignore

    def _note_type_id_from_ident(col, ident: Any) -> str:
        if ident is None:
            return ""
        s = str(ident).strip()
        if not s:
            return ""
        if s.isdigit():
            return s
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

    if _mw is not None and getattr(_mw, "col", None):
        col = _mw.col
        if col:
            CARD_STAGES_NOTE_TYPES = _map_dict_keys(col, CARD_STAGES_NOTE_TYPES)


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
    core_logging.trace(*a, source="card_stages")


def log_info(*a: Any) -> None:
    core_logging.info(*a, source="card_stages")


def log_warn(*a: Any) -> None:
    core_logging.warn(*a, source="card_stages")


def log_error(*a: Any) -> None:
    core_logging.error(*a, source="card_stages")


def _get_note_type_items() -> list[tuple[str, str]]:
    if mw is None or not getattr(mw, "col", None):
        return []
    items: list[tuple[str, str]] = []
    try:
        for m in mw.col.models.all():
            if not isinstance(m, dict):
                continue
            mid = m.get("id")
            name = m.get("name")
            if mid is None or not name:
                continue
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
        return f"<missing {note_type_id}>"
    model = mw.col.models.get(mid)
    if not model:
        return f"<missing {note_type_id}>"
    return str(model.get("name", note_type_id))


def _merge_note_type_items(base: list[tuple[str, str]], extra_ids: list[str]) -> list[tuple[str, str]]:
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
        model = mw.col.models.get(int(str(note_type_id)))
    except Exception:
        model = None
    if not model:
        return []
    out: list[tuple[str, str]] = []
    for i, t in enumerate(model.get("tmpls", []) or []):
        name = str(t.get("name", "")) if isinstance(t, dict) else ""
        out.append((str(i), name or f"<template {i}>"))
    return out


def _merge_template_items(base: list[tuple[str, str]], extra_values: list[str]) -> list[tuple[str, str]]:
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
        model = mw.col.models.get(int(str(note_type_id)))
    except Exception:
        model = None
    if not model:
        return ""
    for i, t in enumerate(model.get("tmpls", []) or []):
        if isinstance(t, dict) and str(t.get("name", "")) == s:
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
        item.setCheckState(
            Qt.CheckState.Unchecked
            if item.checkState() == Qt.CheckState.Checked
            else Qt.CheckState.Checked
        )
        _sync_checkable_combo_text(combo, model)

    combo.view().pressed.connect(_toggle)
    model.itemChanged.connect(lambda _item: _sync_checkable_combo_text(combo, model))
    _sync_checkable_combo_text(combo, model)
    return combo, model


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
    dbg("verify", label, "targets=", len(cids), "rows=", total, "suspended_now=", suspended)


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


@dataclass(frozen=True)
class StageCfg:
    templates: list[str]
    threshold: float


def get_stage_cfg_for_note_type(note_type_id: int | str) -> list[StageCfg]:
    key = str(note_type_id)
    nt = config.CARD_STAGES_NOTE_TYPES.get(key) or {}
    stages = nt.get("stages") if isinstance(nt, dict) else []
    out: list[StageCfg] = []
    for st in stages or []:
        if isinstance(st, dict):
            tmpls = [_template_ord_from_value(str(note_type_id), x) for x in (st.get("templates") or [])]
            tmpls = [t for t in tmpls if t]
            thr = float(st.get("threshold", config.STABILITY_DEFAULT_THRESHOLD))
            out.append(StageCfg(templates=tmpls, threshold=thr))
        elif isinstance(st, list):
            tmpls = [_template_ord_from_value(str(note_type_id), x) for x in st]
            tmpls = [t for t in tmpls if t]
            out.append(StageCfg(templates=tmpls, threshold=config.STABILITY_DEFAULT_THRESHOLD))
    return out


def compute_stage_stabilities(col: Collection, note, note_type_id: int | str) -> list[float | None]:
    stages = get_stage_cfg_for_note_type(note_type_id)
    if not stages:
        return []
    cards = note.cards()
    out: list[float | None] = []
    for st in stages:
        wanted = set(st.templates)
        vals: list[float] = []
        saw_any = False
        has_unknown = False
        for c in cards:
            if str(c.ord) not in wanted:
                continue
            saw_any = True
            s = card_stability(c)
            if s is None:
                has_unknown = True
            else:
                vals.append(s)
        if not saw_any or has_unknown:
            out.append(None)
        else:
            out.append(agg(vals))
    return out


def stage_is_ready(note_type_id: int | str, stage_index: int, stage_stab: float | None) -> bool:
    stages = get_stage_cfg_for_note_type(note_type_id)
    if stage_index < 0 or stage_index >= len(stages):
        return False
    if stage_stab is None:
        return False
    return float(stage_stab) >= float(stages[stage_index].threshold)


def stage_card_ids(note, note_type_id: int | str, stage_index: int) -> list[int]:
    stages = get_stage_cfg_for_note_type(note_type_id)
    if stage_index < 0 or stage_index >= len(stages):
        return []
    wanted = set(stages[stage_index].templates)
    cids: list[int] = []
    for c in note.cards():
        if str(c.ord) in wanted:
            cids.append(int(c.id))
    return cids


def note_stage0_ready(col: Collection, note) -> bool:
    nt_id = int(note.mid)
    stages = get_stage_cfg_for_note_type(nt_id)
    if not stages:
        return True
    stabs = compute_stage_stabilities(col, note, nt_id)
    s0 = stabs[0] if stabs else None
    return stage_is_ready(nt_id, 0, s0)


def _note_type_id_from_identifier(col: Collection, ident: Any) -> int | None:
    if ident is None:
        return None
    s = str(ident).strip()
    if not s or not s.isdigit():
        return None
    try:
        return int(s)
    except Exception:
        return None


def note_ids_for_note_types(col: Collection, note_types: list[Any]) -> list[int]:
    nids: list[int] = []
    for nt in note_types:
        mid = _note_type_id_from_identifier(col, nt)
        if mid is None:
            continue
        try:
            nids.extend(list(col.find_notes(f"mid:{mid}")))
        except Exception:
            continue
    return nids


DEFAULT_STICKY_TAG_BASE = "_intern::family_gate::unlocked"
DEFAULT_STAGE_TAG_PREFIX = "_intern::family_gate::unlocked::stage"


def stage_tag(stage_index: int) -> str:
    return f"{DEFAULT_STAGE_TAG_PREFIX}{stage_index}"


def card_stages_apply(col: Collection, ui_set, counters: dict[str, int]) -> None:
    if not config.CARD_STAGES_ENABLED:
        log_info("card_stages disabled")
        return
    note_types = list(config.CARD_STAGES_NOTE_TYPES.keys())
    if not note_types:
        log_warn("card_stages: no note_types configured")
        return

    nids = note_ids_for_note_types(col, note_types)
    dbg("card_stages: candidate notes", len(nids))

    to_suspend: list[int] = []
    to_unsuspend: list[int] = []

    for i, nid in enumerate(nids):
        try:
            note = col.get_note(nid)
            nt_id = int(note.mid)
            stages = get_stage_cfg_for_note_type(nt_id)
            if not stages:
                continue
            stabs = compute_stage_stabilities(col, note, nt_id)
            prev_stage_ok = True

            for st_idx in range(len(stages)):
                st_cids = stage_card_ids(note, nt_id, st_idx)
                if not st_cids:
                    continue
                should_open = True if st_idx == 0 else prev_stage_ok
                stab_val = stabs[st_idx] if st_idx < len(stabs) else None
                this_stage_ready = stage_is_ready(nt_id, st_idx, stab_val)
                st_tag = stage_tag(st_idx)
                st_sticky = config.STICKY_UNLOCK and (st_tag in note.tags)

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
            dbg("card_stages: exception applying nid", nid)
            dbg(traceback.format_exc())
            log_warn("card_stages: exception applying nid", nid)

        if i % 400 == 0:
            ui_set(
                f"CardStages: apply... {i}/{len(nids)} | unsusp={len(to_unsuspend)} susp={len(to_suspend)}",
                i,
                len(nids),
            )

    if to_suspend:
        sus = list(set(to_suspend))
        suspend_cards(col, sus)
        counters["cards_suspended"] += len(sus)
        _verify_suspended(col, sus, label="card_stages_suspend")
    if to_unsuspend:
        uns = list(set(to_unsuspend))
        unsuspend_cards(col, uns)
        counters["cards_unsuspended"] += len(uns)
        _verify_suspended(col, uns, label="card_stages_unsuspend")


def _notify_info(msg: str) -> None:
    tooltip(msg, period=2500)


def _notify_error(msg: str) -> None:
    tooltip(msg, period=2500)


def run_card_stages(*, reason: str = "manual") -> None:
    config.reload_config()
    if not mw or not mw.col:
        log_error("card_stages: no collection loaded")
        _notify_error("No collection loaded.")
        return
    if reason == "sync" and not (config.RUN_ON_SYNC and config.CARD_STAGES_RUN_ON_SYNC):
        log_info("card_stages: skip (run_on_sync disabled)")
        return
    if reason == "manual" and not config.RUN_ON_UI:
        log_info("card_stages: skip (run_on_ui disabled)")
        return

    def ui_set(label: str, value: int, maxv: int) -> None:
        def _do() -> None:
            try:
                mw.progress.update(label=label, value=value, max=maxv)
            except Exception:
                return
        mw.taskman.run_on_main(_do)

    def op(col: Collection):
        undo_entry = col.add_custom_undo_entry("AJpC Card Stages")
        counters = {"cards_suspended": 0, "cards_unsuspended": 0, "notes_tagged": 0}
        ui_set("CardStages: start...", 0, 1)
        card_stages_apply(col, ui_set, counters)

        class _Result:
            def __init__(self, changes, counts: dict[str, int]):
                self.changes = changes
                self.counts = counts

        try:
            changes = col.merge_undo_entries(undo_entry)
        except InvalidInput:
            log_warn("merge_undo_entries skipped: target undo op not found", undo_entry)
            changes = OpChanges()
        if changes is None:
            changes = OpChanges()
        return _Result(changes, counters)

    def on_success(result) -> None:
        c = getattr(result, "counts", {}) or {}
        log_info(
            "Card Stages finished",
            f"unsuspended={c.get('cards_unsuspended', 0)}",
            f"suspended={c.get('cards_suspended', 0)}",
            f"tagged_notes={c.get('notes_tagged', 0)}",
        )
        _notify_info(
            "Card Stages finished.\n"
            f"unsuspended={c.get('cards_unsuspended', 0)} "
            f"suspended={c.get('cards_suspended', 0)} "
            f"tagged_notes={c.get('notes_tagged', 0)}"
        )

    def on_failure(err: Exception) -> None:
        tb = "".join(traceback.format_exception(type(err), err, err.__traceback__))
        log_error("Card Stages failed", repr(err))
        dbg(tb)
        _notify_error("Card Stages failed:\n" + tb)

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
    root = QWidget()
    root_layout = QVBoxLayout()
    root.setLayout(root_layout)
    tabs = QTabWidget()
    root_layout.addWidget(tabs)

    general_tab = QWidget()
    general_layout = QVBoxLayout()
    general_tab.setLayout(general_layout)
    general_form = QFormLayout()
    general_layout.addLayout(general_form)

    enabled_cb = QCheckBox()
    enabled_cb.setChecked(config.CARD_STAGES_ENABLED)
    general_form.addRow(
        _tip_label("Enabled", "Enable or disable Card Stages."),
        enabled_cb,
    )

    run_on_sync_cb = QCheckBox()
    run_on_sync_cb.setChecked(config.CARD_STAGES_RUN_ON_SYNC)
    general_form.addRow(
        _tip_label("Run on sync", "Run Card Stages automatically at sync start."),
        run_on_sync_cb,
    )

    note_type_items = _merge_note_type_items(
        _get_note_type_items(), list((config.CARD_STAGES_NOTE_TYPES or {}).keys())
    )
    note_type_combo, note_type_model = _make_checkable_combo(
        note_type_items, list((config.CARD_STAGES_NOTE_TYPES or {}).keys())
    )
    general_form.addRow(
        _tip_label("Note types", "Only selected note types are processed by Card Stages."),
        note_type_combo,
    )
    general_layout.addStretch(1)
    tabs.addTab(general_tab, "General")

    stages_tab = QWidget()
    stages_layout = QVBoxLayout()
    stages_tab.setLayout(stages_layout)
    stages_empty_label = QLabel("Select note types in General tab.")
    stages_layout.addWidget(stages_empty_label)
    stage_tabs = QTabWidget()
    stages_layout.addWidget(stage_tabs)
    stages_layout.addStretch(1)
    tabs.addTab(stages_tab, "Stages")

    state: dict[str, list[dict[str, Any]]] = {}
    for nt_id, nt_cfg in (config.CARD_STAGES_NOTE_TYPES or {}).items():
        stages = nt_cfg.get("stages") if isinstance(nt_cfg, dict) else None
        out_stages: list[dict[str, Any]] = []
        for st in stages or []:
            if isinstance(st, dict):
                tmpls = [
                    _template_ord_from_value(str(nt_id), x) or str(x).strip()
                    for x in (st.get("templates") or [])
                ]
                tmpls = [t for t in tmpls if t]
                out_stages.append({"templates": tmpls, "threshold": float(st.get("threshold", config.STABILITY_DEFAULT_THRESHOLD))})
            elif isinstance(st, list):
                tmpls = [_template_ord_from_value(str(nt_id), x) or str(x).strip() for x in st]
                tmpls = [t for t in tmpls if t]
                out_stages.append({"templates": tmpls, "threshold": float(config.STABILITY_DEFAULT_THRESHOLD)})
        state[str(nt_id)] = out_stages

    widgets: dict[str, list[dict[str, Any]]] = {}

    def _capture_state() -> None:
        for nt_id, stages in widgets.items():
            out: list[dict[str, Any]] = []
            for stage in stages:
                out.append(
                    {
                        "templates": _checked_items(stage["templates_model"]),
                        "threshold": float(stage["threshold_spin"].value()),
                    }
                )
            state[nt_id] = out

    def _clear_tabs() -> None:
        while stage_tabs.count():
            w = stage_tabs.widget(0)
            stage_tabs.removeTab(0)
            if w is not None:
                w.deleteLater()

    def _add_stage(nt_id: str) -> None:
        _capture_state()
        state.setdefault(nt_id, []).append({"templates": [], "threshold": float(config.STABILITY_DEFAULT_THRESHOLD)})
        _refresh_stages(capture=False)

    def _remove_stage(nt_id: str, idx: int) -> None:
        _capture_state()
        stages = state.get(nt_id, [])
        if 0 <= idx < len(stages):
            del stages[idx]
        state[nt_id] = stages
        _refresh_stages(capture=False)

    def _refresh_stages(*, capture: bool = True) -> None:
        if capture:
            _capture_state()
        _clear_tabs()
        widgets.clear()
        selected_types = _checked_items(note_type_model)
        stages_empty_label.setVisible(not bool(selected_types))
        stage_tabs.setVisible(bool(selected_types))
        for nt_id in selected_types:
            stages = state.get(nt_id, [])
            widgets[nt_id] = []

            tab = QWidget()
            tab_layout = QVBoxLayout()
            tab.setLayout(tab_layout)
            add_btn = QPushButton("Add stage")
            add_btn.clicked.connect(lambda _=None, n=nt_id: _add_stage(n))
            tab_layout.addWidget(add_btn)

            extra_templates: list[str] = []
            for st in stages:
                for t in st.get("templates", []) or []:
                    extra_templates.append(str(t))
            template_items = _merge_template_items(_get_template_items(nt_id), extra_templates)

            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            container = QWidget()
            container_layout = QVBoxLayout()
            container.setLayout(container_layout)
            scroll.setWidget(container)
            tab_layout.addWidget(scroll)

            for idx, st in enumerate(stages):
                box = QGroupBox(f"Stage {idx}")
                form = QFormLayout()
                box.setLayout(form)

                templates_combo, templates_model = _make_checkable_combo(
                    template_items, list(st.get("templates", []) or [])
                )
                form.addRow(
                    _tip_label("Templates", "Templates (card ords) that belong to this stage."),
                    templates_combo,
                )

                threshold_spin = QDoubleSpinBox()
                threshold_spin.setDecimals(2)
                threshold_spin.setRange(0, 100000)
                threshold_spin.setSuffix(" days")
                threshold_spin.setValue(float(st.get("threshold", config.STABILITY_DEFAULT_THRESHOLD)))
                form.addRow(
                    _tip_label("Threshold", "Required FSRS stability before the next stage can unlock."),
                    threshold_spin,
                )

                remove_btn = QPushButton("Remove stage")
                remove_btn.clicked.connect(lambda _=None, n=nt_id, i=idx: _remove_stage(n, i))
                form.addRow(remove_btn)

                container_layout.addWidget(box)
                widgets[nt_id].append({"templates_model": templates_model, "threshold_spin": threshold_spin})

            container_layout.addStretch(1)
            stage_tabs.addTab(tab, _note_type_label(nt_id))

    _refresh_stages()
    note_type_model.itemChanged.connect(lambda _item: _refresh_stages())

    ctx.add_tab(root, "Card Stages")

    def _save(cfg: dict, errors: list[str]) -> None:
        _capture_state()
        selected = _checked_items(note_type_model)
        note_types_cfg: dict[str, Any] = {}
        for nt_id in selected:
            stages = state.get(nt_id, [])
            if not stages:
                errors.append(f"Card Stages: no stages defined for note type: {_note_type_label(nt_id)}")
                continue
            stage_cfgs: list[dict[str, Any]] = []
            for s_idx, st in enumerate(stages):
                tmpls = [str(x) for x in (st.get("templates") or []) if str(x).isdigit()]
                if not tmpls:
                    errors.append(f"Card Stages: stage {s_idx} has no templates ({_note_type_label(nt_id)})")
                    continue
                stage_cfgs.append({"templates": tmpls, "threshold": float(st.get("threshold", config.STABILITY_DEFAULT_THRESHOLD))})
            if stage_cfgs:
                note_types_cfg[str(nt_id)] = {"stages": stage_cfgs}

        config._cfg_set(cfg, "card_stages.enabled", bool(enabled_cb.isChecked()))
        config._cfg_set(cfg, "card_stages.run_on_sync", bool(run_on_sync_cb.isChecked()))
        config._cfg_set(cfg, "card_stages.note_types", note_types_cfg)

    return _save


def _enabled_card_stages() -> bool:
    return bool(config.RUN_ON_UI and config.CARD_STAGES_ENABLED)


def _init() -> None:
    from aqt import gui_hooks, mw

    def _on_sync_start() -> None:
        run_card_stages(reason="sync")

    if mw is not None and not getattr(mw, "_ajpc_card_stages_sync_hook_installed", False):
        gui_hooks.sync_will_start.append(_on_sync_start)
        mw._ajpc_card_stages_sync_hook_installed = True


MODULE = ModuleSpec(
    id="card_stages",
    label="Card Stages",
    order=25,
    init=_init,
    run_items=[
        {
            "label": "Run Card Stages",
            "callback": lambda: run_card_stages(reason="manual"),
            "enabled_fn": _enabled_card_stages,
            "order": 11,
        }
    ],
    build_settings=_build_settings,
)

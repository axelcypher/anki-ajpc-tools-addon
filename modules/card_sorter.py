from __future__ import annotations

import json
import os
import re
import time
import traceback
from typing import Any

from anki.collection import Collection
from aqt import mw
from aqt.qt import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QFrame,
    QLabel,
    QPlainTextEdit,
    QStandardItem,
    QStandardItemModel,
    QTabWidget,
    Qt,
    QVBoxLayout,
    QWidget,
    QSizePolicy,
)
from aqt.utils import askUser, tooltip

from .. import logging as core_logging
from . import ModuleSpec

ADDON_DIR = os.path.dirname(os.path.dirname(__file__))
CONFIG_PATH = os.path.join(ADDON_DIR, "config.json")

CFG: dict[str, Any] = {}
DEBUG = False
RUN_ON_SYNC = True
RUN_ON_UI = True

CARD_SORTER_ENABLED = True
CARD_SORTER_RUN_ON_ADD = True
CARD_SORTER_RUN_ON_SYNC = True
CARD_SORTER_EXCLUDE_DECKS: list[str] = []
CARD_SORTER_EXCLUDE_TAGS: list[str] = []
CARD_SORTER_NOTE_TYPES: dict[str, Any] = {}


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
    global CFG, DEBUG, RUN_ON_SYNC, RUN_ON_UI
    global CARD_SORTER_ENABLED, CARD_SORTER_RUN_ON_ADD
    global CARD_SORTER_RUN_ON_SYNC
    global CARD_SORTER_EXCLUDE_DECKS, CARD_SORTER_EXCLUDE_TAGS, CARD_SORTER_NOTE_TYPES

    CFG = _load_config()

    _dbg = CFG.get("debug", {})
    if isinstance(_dbg, dict):
        DEBUG = bool(_dbg.get("enabled", False))
    else:
        DEBUG = bool(_dbg)

    RUN_ON_SYNC = bool(cfg_get("run_on_sync", True))
    RUN_ON_UI = bool(cfg_get("run_on_ui", True))

    CARD_SORTER_ENABLED = bool(cfg_get("card_sorter.enabled", True))
    CARD_SORTER_RUN_ON_ADD = bool(cfg_get("card_sorter.run_on_add_note", True))
    CARD_SORTER_RUN_ON_SYNC = bool(cfg_get("card_sorter.run_on_sync", True))
    CARD_SORTER_EXCLUDE_DECKS = list(cfg_get("card_sorter.exclude_decks", []) or [])
    CARD_SORTER_EXCLUDE_TAGS = list(cfg_get("card_sorter.exclude_tags", []) or [])
    CARD_SORTER_NOTE_TYPES = cfg_get("card_sorter.note_types", {}) or {}

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
            CARD_SORTER_NOTE_TYPES = _map_dict_keys(col, CARD_SORTER_NOTE_TYPES)


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
    core_logging.trace(*a, source="card_sorter")


def log_info(*a: Any) -> None:
    core_logging.info(*a, source="card_sorter")


def log_warn(*a: Any) -> None:
    core_logging.warn(*a, source="card_sorter")


def log_error(*a: Any) -> None:
    core_logging.error(*a, source="card_sorter")


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


def _populate_deck_combo(combo: QComboBox, deck_names: list[str], current_value: str) -> None:
    combo.setEditable(True)
    combo.addItem("", "")
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


def _combo_value(combo: QComboBox) -> str:
    data = combo.currentData()
    if data is None:
        return str(combo.currentText() or "").strip()
    return str(data).strip()


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


def _parse_list_entries(text: str) -> list[str]:
    tokens = re.split(r"[,\n;]+", text.strip())
    out: list[str] = []
    for tok in tokens:
        s = tok.strip()
        if s:
            out.append(s)
    return out


def _normalize_list(items: list[Any]) -> list[str]:
    out: list[str] = []
    for item in items:
        s = str(item).strip()
        if s:
            out.append(s)
    return out


def _info_box(text: str) -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
    label.setStyleSheet("padding: 6px; border: 1px solid #999; border-radius: 4px;")
    return label


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
            log_warn("note_ids_for_note_types failed", nt)
            continue
    return nids


def _get_note_type_cfgs() -> dict[str, dict[str, Any]]:
    raw = config.CARD_SORTER_NOTE_TYPES
    if not isinstance(raw, dict):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for nt_id, cfg in raw.items():
        if not isinstance(cfg, dict):
            continue
        mode = str(cfg.get("mode", "by_template")).strip() or "by_template"
        default_deck = str(cfg.get("default_deck", "")).strip()
        by_template_raw = cfg.get("by_template", {}) or {}
        by_template: dict[str, str] = {}
        if isinstance(by_template_raw, dict):
            for k, v in by_template_raw.items():
                tk = _template_ord_from_value(str(nt_id), k)
                tv = str(v).strip()
                if tk and tv:
                    by_template[tk] = tv
        out[str(nt_id)] = {
            "mode": mode,
            "default_deck": default_deck,
            "by_template": by_template,
        }
    return out


def _gather_target_decks(note_type_cfgs: dict[str, dict[str, Any]]) -> set[str]:
    targets: set[str] = set()
    for cfg in note_type_cfgs.values():
        mode = cfg.get("mode", "by_template")
        if mode == "all":
            deck = str(cfg.get("default_deck", "")).strip()
            if deck:
                targets.add(deck)
        else:
            by_template = cfg.get("by_template", {}) or {}
            if isinstance(by_template, dict):
                for deck in by_template.values():
                    deck_name = str(deck).strip()
                    if deck_name:
                        targets.add(deck_name)
    return targets


def _ensure_decks(target_decks: set[str]) -> set[str]:
    skipped: set[str] = set()
    for deck_name in sorted(target_decks):
        if not deck_name:
            continue
        if mw.col.decks.id_for_name(deck_name) is not None:
            continue
        if askUser(
            title="Card Sorter",
            text="Deck named '" + deck_name + "' is configured but does not exist. Create it?",
            defaultno=True,
        ):
            mw.col.decks.id(deck_name)
        else:
            skipped.add(deck_name)
            log_warn("card_sorter: deck skipped", deck_name)
    return skipped


def _deck_is_excluded(deck_name: str, exclude_decks: list[str]) -> bool:
    for ex in exclude_decks:
        if deck_name == ex or deck_name.startswith(ex):
            return True
    return False


def _note_has_excluded_tag(note, exclude_tags: set[str]) -> bool:
    if not exclude_tags:
        return False
    note_tags = set(note.tags)
    return any(tag in note_tags for tag in exclude_tags)


def _get_deck_id(deck_name: str, deck_id_cache: dict[str, int], skipped_decks: set[str]) -> int | None:
    if not deck_name or deck_name in skipped_decks:
        return None
    if deck_name in deck_id_cache:
        return deck_id_cache[deck_name]
    deck_id = mw.col.decks.id_for_name(deck_name)
    if deck_id is None:
        skipped_decks.add(deck_name)
        return None
    deck_id_cache[deck_name] = deck_id
    return deck_id


def _apply_moves(col: Collection, cards_in_deck: dict[int, list[int]]) -> int:
    moved = 0
    for deck_id, card_ids in cards_in_deck.items():
        if not card_ids:
            continue
        unique_ids = list(set(card_ids))
        moved += len(unique_ids)
        col.db.execute(
            f"UPDATE cards SET did = ? WHERE id IN ({','.join('?' * len(unique_ids))})",
            deck_id,
            *unique_ids,
        )
    return moved


def _sort_notes(notes: list, note_type_cfgs: dict[str, dict[str, Any]], skipped_decks: set[str]) -> dict[str, int]:
    exclude_decks = _normalize_list(config.CARD_SORTER_EXCLUDE_DECKS)
    exclude_tags = set(_normalize_list(config.CARD_SORTER_EXCLUDE_TAGS))
    deck_id_cache: dict[str, int] = {}
    cards_in_deck: dict[int, list[int]] = {}

    notes_processed = 0
    cards_moved = 0

    for note in notes:
        model = mw.col.models.get(note.mid)
        nt_name = str(model.get("name", "")) if model else ""
        nt_id = str(note.mid)
        cfg = note_type_cfgs.get(nt_id)
        if not cfg:
            continue

        if _note_has_excluded_tag(note, exclude_tags):
            if config.DEBUG:
                dbg("card_sorter: note excluded by tag", "nid=", note.id, "note_type=", nt_name)
            continue

        notes_processed += 1
        mode = cfg.get("mode", "by_template")
        default_deck = str(cfg.get("default_deck", "")).strip()
        by_template = cfg.get("by_template", {}) or {}
        if not isinstance(by_template, dict):
            by_template = {}

        for card in note.cards():
            card_deck_name = mw.col.decks.name(card.did)
            if _deck_is_excluded(card_deck_name, exclude_decks):
                continue

            if mode == "all":
                target_deck = default_deck
            else:
                tmpl_ord = str(card.ord)
                target_deck = str(by_template.get(tmpl_ord, "")).strip()

            if not target_deck:
                continue

            deck_id = _get_deck_id(target_deck, deck_id_cache, skipped_decks)
            if deck_id is None:
                continue

            if card.did != deck_id:
                cards_in_deck.setdefault(deck_id, []).append(card.id)

    cards_moved = _apply_moves(mw.col, cards_in_deck)
    if config.DEBUG:
        dbg(
            "card_sorter: done",
            "notes=",
            notes_processed,
            "cards_moved=",
            cards_moved,
            "decks=",
            len(cards_in_deck),
        )
    return {
        "notes_processed": notes_processed,
        "cards_moved": cards_moved,
        "decks_touched": len(cards_in_deck),
    }


def sort_note(note) -> dict[str, int]:
    config.reload_config()
    if not config.CARD_SORTER_ENABLED or not config.CARD_SORTER_RUN_ON_ADD:
        return {}
    if not mw or not mw.col:
        return {}

    note_type_cfgs = _get_note_type_cfgs()
    if not note_type_cfgs:
        return {}

    skipped_decks = _ensure_decks(_gather_target_decks(note_type_cfgs))
    return _sort_notes([note], note_type_cfgs, skipped_decks)


def sort_all(*, reason: str = "manual") -> dict[str, int]:
    config.reload_config()
    if not config.CARD_SORTER_ENABLED:
        return {}
    if reason == "sync" and not config.RUN_ON_SYNC:
        return {}
    if reason == "sync" and not config.CARD_SORTER_RUN_ON_SYNC:
        return {}
    if reason == "manual" and not config.RUN_ON_UI:
        return {}
    if not mw or not mw.col:
        return {}

    note_type_cfgs = _get_note_type_cfgs()
    if not note_type_cfgs:
        log_warn("card_sorter: no note types configured")
        return {}

    skipped_decks = _ensure_decks(_gather_target_decks(note_type_cfgs))
    note_types = list(note_type_cfgs.keys())
    note_ids = note_ids_for_note_types(mw.col, note_types)
    notes = [mw.col.get_note(nid) for nid in note_ids]
    return _sort_notes(notes, note_type_cfgs, skipped_decks)


def _notify_info(msg: str, *, reason: str = "manual") -> None:
    tooltip(msg, period=2500)


def _notify_error(msg: str, *, reason: str = "manual") -> None:
    tooltip(msg, period=2500)


def run_card_sorter(*, reason: str = "manual") -> None:
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
        log_error("card_sorter: no collection loaded")
        _notify_error("No collection loaded.", reason=reason)
        return

    if reason == "sync" and not config.RUN_ON_SYNC:
        log_info("card_sorter: skip (run_on_sync disabled)")
        return
    if reason == "sync" and not config.CARD_SORTER_RUN_ON_SYNC:
        log_info("card_sorter: skip (card_sorter.run_on_sync disabled)")
        return
    if reason == "manual" and not config.RUN_ON_UI:
        log_info("card_sorter: skip (run_on_ui disabled)")
        return

    try:
        result = sort_all(reason=reason) or {}
    except Exception as err:
        tb = "".join(traceback.format_exception(type(err), err, err.__traceback__))
        log_error("Card Sorter failed", repr(err))
        if config.DEBUG:
            dbg("CARD_SORTER_FAILURE", repr(err))
            dbg(tb)
        _notify_error("Card Sorter failed:\n" + tb, reason=reason)
        return

    msg = (
        "Card Sorter finished.\n"
        f"notes_processed={result.get('notes_processed', 0)} "
        f"cards_moved={result.get('cards_moved', 0)} "
        f"decks_touched={result.get('decks_touched', 0)}"
    )
    if config.DEBUG:
        dbg("CARD_SORTER_RESULT", msg)
    log_info(
        "Card Sorter finished",
        f"notes_processed={result.get('notes_processed', 0)}",
        f"cards_moved={result.get('cards_moved', 0)}",
        f"decks_touched={result.get('decks_touched', 0)}",
    )
    _notify_info(msg, reason=reason)


def _build_settings(ctx):
    card_sorter_tab = QWidget()
    card_sorter_layout = QVBoxLayout()
    card_sorter_tab.setLayout(card_sorter_layout)
    card_sorter_tabs = QTabWidget()
    card_sorter_layout.addWidget(card_sorter_tabs)

    general_tab = QWidget()
    general_layout = QVBoxLayout()
    general_tab.setLayout(general_layout)
    card_sorter_form = QFormLayout()
    general_layout.addLayout(card_sorter_form)

    deck_names = _get_deck_names()

    card_sorter_enabled_cb = QCheckBox()
    card_sorter_enabled_cb.setChecked(config.CARD_SORTER_ENABLED)
    card_sorter_form.addRow("Enabled", card_sorter_enabled_cb)

    card_sorter_run_on_sync_cb = QCheckBox()
    card_sorter_run_on_sync_cb.setChecked(config.CARD_SORTER_RUN_ON_SYNC)
    card_sorter_form.addRow("Run on sync", card_sorter_run_on_sync_cb)

    card_sorter_run_on_add_cb = QCheckBox()
    card_sorter_run_on_add_cb.setChecked(config.CARD_SORTER_RUN_ON_ADD)
    card_sorter_form.addRow("Run on add note", card_sorter_run_on_add_cb)

    separator = QFrame()
    separator.setFrameShape(QFrame.Shape.HLine)
    separator.setFrameShadow(QFrame.Shadow.Sunken)

    card_sorter_form.addWidget(separator)

    card_sorter_note_type_items = _merge_note_type_items(
        _get_note_type_items(), list((config.CARD_SORTER_NOTE_TYPES or {}).keys())
    )
    card_sorter_note_type_combo, card_sorter_note_type_model = _make_checkable_combo(
        card_sorter_note_type_items, list((config.CARD_SORTER_NOTE_TYPES or {}).keys())
    )
    card_sorter_form.addRow("Note types", card_sorter_note_type_combo)

    card_sorter_exclude_deck_names = sorted(
        set(deck_names + list(config.CARD_SORTER_EXCLUDE_DECKS or []))
    )
    card_sorter_exclude_decks_combo, card_sorter_exclude_decks_model = _make_checkable_combo(
        card_sorter_exclude_deck_names, list(config.CARD_SORTER_EXCLUDE_DECKS or [])
    )
    card_sorter_form.addRow("Exclude decks", card_sorter_exclude_decks_combo)

    card_sorter_exclude_tags_label = QLabel("Exclude tags (one per line or comma-separated)")
    card_sorter_exclude_tags_edit = QPlainTextEdit()
    if config.CARD_SORTER_EXCLUDE_TAGS:
        card_sorter_exclude_tags_edit.setPlainText("\n".join(config.CARD_SORTER_EXCLUDE_TAGS))
    card_sorter_exclude_tags_edit.setMaximumHeight(60)
    general_layout.addWidget(card_sorter_exclude_tags_label)
    general_layout.addWidget(card_sorter_exclude_tags_edit)
    general_layout.addStretch(1)
    general_layout.addWidget(
        _info_box(
            "Enabled: turns Card Sorter on/off.\n"
            "Run on sync: runs sorter automatically at sync start.\n"
            "Note types: only these note types are processed.\n"
            "Exclude decks: cards in these decks are never moved.\n"
            "Exclude tags: notes with any listed tag are skipped.\n"
            "Rules are configured per selected note type in the Rules tab."
        )
    )

    card_sorter_tabs.addTab(general_tab, "General")

    rules_tab = QWidget()
    rules_layout = QVBoxLayout()
    rules_tab.setLayout(rules_layout)

    card_sorter_rules_empty_label = QLabel("Select note types in General tab.")
    rules_layout.addWidget(card_sorter_rules_empty_label)

    card_sorter_rule_tabs = QTabWidget()
    rules_layout.addWidget(card_sorter_rule_tabs)

    card_sorter_tabs.addTab(rules_tab, "Rules")

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
                key = _template_ord_from_value(str(nt_id), k) or str(k).strip()
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
        while card_sorter_rule_tabs.count():
            w = card_sorter_rule_tabs.widget(0)
            card_sorter_rule_tabs.removeTab(0)
            if w is not None:
                w.deleteLater()

    def _refresh_card_sorter_rules() -> None:
        _capture_card_sorter_state()
        _clear_card_sorter_layout()
        card_sorter_note_type_widgets.clear()

        selected_types = _checked_items(card_sorter_note_type_model)
        card_sorter_rules_empty_label.setVisible(not bool(selected_types))
        card_sorter_rule_tabs.setVisible(bool(selected_types))
        for nt_id in selected_types:
            cfg = card_sorter_state.get(nt_id)
            if not cfg:
                cfg = {"mode": "by_template", "default_deck": "", "by_template": {}}
                card_sorter_state[nt_id] = cfg

            tab = QWidget()
            tab_layout = QVBoxLayout()
            tab.setLayout(tab_layout)

            form = QFormLayout()
            tab_layout.addLayout(form)

            mode_combo = QComboBox()
            mode_combo.addItem("sort by template", "by_template")
            mode_combo.addItem("sort all in same deck", "all")
            mode_val = str(cfg.get("mode", "by_template")).strip() or "by_template"
            mode_idx = mode_combo.findData(mode_val)
            if mode_idx < 0:
                mode_idx = 0
            mode_combo.setCurrentIndex(mode_idx)
            form.addRow("Mode", mode_combo)

            default_deck_label = QLabel("Deck")
            default_deck_combo = QComboBox()
            _populate_deck_combo(default_deck_combo, deck_names, cfg.get("default_deck", ""))
            form.addRow(default_deck_label, default_deck_combo)

            template_group = QGroupBox("Templates")
            template_layout = QFormLayout()
            template_group.setLayout(template_layout)
            template_combos: dict[str, QComboBox] = {}

            template_items = _merge_template_items(
                _get_template_items(nt_id), list(cfg.get("by_template", {}).keys())
            )
            for tmpl_ord, tmpl_label in template_items:
                combo = QComboBox()
                _populate_deck_combo(
                    combo, deck_names, cfg.get("by_template", {}).get(tmpl_ord, "")
                )
                template_layout.addRow(tmpl_label, combo)
                template_combos[tmpl_ord] = combo

            tab_layout.addWidget(template_group)

            def _toggle_template_group(
                _idx,
                combo=mode_combo,
                box=template_group,
                deck_label=default_deck_label,
                deck_combo=default_deck_combo,
            ) -> None:
                by_template = _combo_value(combo) == "by_template"
                box.setVisible(by_template)
                deck_label.setVisible(not by_template)
                deck_combo.setVisible(not by_template)

            mode_combo.currentIndexChanged.connect(_toggle_template_group)
            _toggle_template_group(0)

            tab_layout.addStretch(1)
            tab_layout.addWidget(
                _info_box(
                    "Mode:\n"
                    "- sort by template: assign target deck per template.\n"
                    "- sort all in same deck: move all cards of the note to one deck.\n"
                    "Deck: only used in 'sort all in same deck'.\n"
                    "Templates: only used in 'sort by template'.\n"
                    "Template IDs are saved by ord for stability."
                )
            )
            card_sorter_rule_tabs.addTab(tab, _note_type_label(nt_id))
            card_sorter_note_type_widgets[nt_id] = {
                "mode_combo": mode_combo,
                "default_deck_combo": default_deck_combo,
                "template_combos": template_combos,
            }

    _refresh_card_sorter_rules()
    card_sorter_note_type_model.itemChanged.connect(lambda _item: _refresh_card_sorter_rules())

    ctx.add_tab(card_sorter_tab, "Card Sorter")

    def _save(cfg: dict, errors: list[str]) -> None:
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
                    if key and val and key.isdigit():
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
                card_sorter_cfg[nt_id] = {"mode": "by_template", "by_template": by_template}

        card_sorter_exclude_decks = _checked_items(card_sorter_exclude_decks_model)
        card_sorter_exclude_tags = _parse_list_entries(card_sorter_exclude_tags_edit.toPlainText())

        config._cfg_set(cfg, "card_sorter.enabled", bool(card_sorter_enabled_cb.isChecked()))
        config._cfg_set(cfg, "card_sorter.run_on_add_note", bool(card_sorter_run_on_add_cb.isChecked()))
        config._cfg_set(cfg, "card_sorter.run_on_sync", bool(card_sorter_run_on_sync_cb.isChecked()))
        config._cfg_set(cfg, "card_sorter.exclude_decks", card_sorter_exclude_decks)
        config._cfg_set(cfg, "card_sorter.exclude_tags", card_sorter_exclude_tags)
        config._cfg_set(cfg, "card_sorter.note_types", card_sorter_cfg)

    return _save


def _enabled_card_sorter() -> bool:
    return bool(config.RUN_ON_UI and config.CARD_SORTER_ENABLED)


def _init() -> None:
    from aqt import gui_hooks, mw

    def _on_add_cards(note, *args, **kwargs) -> None:
        try:
            sort_note(note)
        except Exception:
            log_warn("card_sorter: add_cards hook failed")

    def _on_sync_start() -> None:
        run_card_sorter(reason="sync")

    if mw is not None and not getattr(mw, "_ajpc_card_sorter_hooks_installed", False):
        gui_hooks.add_cards_did_add_note.append(_on_add_cards)
        gui_hooks.sync_will_start.append(_on_sync_start)
        mw._ajpc_card_sorter_hooks_installed = True


MODULE = ModuleSpec(
    id="card_sorter",
    label="Card Sorter",
    order=50,
    init=_init,
    run_items=[
        {
            "label": "Run Card Sorter",
            "callback": lambda: run_card_sorter(reason="manual"),
            "enabled_fn": _enabled_card_sorter,
            "order": 50,
        }
    ],
    build_settings=_build_settings,
)

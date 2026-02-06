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
from aqt.qt import QCheckBox, QComboBox, QFormLayout, QLineEdit, QSpinBox, QWidget
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

EXAMPLE_GATE_ENABLED = True
VOCAB_DECK = ""
EXAMPLE_DECK = ""
VOCAB_KEY_FIELD = "Vocab"
EXAMPLE_KEY_FIELD = "Vocab"
EX_STAGE_SEP = "@"
EX_STAGE_DEFAULT = 0
EX_APPLY_ALL_CARDS = True

KEY_STRIP_HTML = True
KEY_TRIM = True
KEY_NFC = True
KEY_FIRST_TOKEN = True
KEY_STRIP_FURIGANA_BR = False

FAMILY_NOTE_TYPES: dict[str, Any] = {}


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
    global EXAMPLE_GATE_ENABLED, VOCAB_DECK, EXAMPLE_DECK
    global VOCAB_KEY_FIELD, EXAMPLE_KEY_FIELD, EX_STAGE_SEP, EX_STAGE_DEFAULT, EX_APPLY_ALL_CARDS
    global KEY_STRIP_HTML, KEY_TRIM, KEY_NFC, KEY_FIRST_TOKEN, KEY_STRIP_FURIGANA_BR
    global FAMILY_NOTE_TYPES

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

    EXAMPLE_GATE_ENABLED = bool(cfg_get("example_gate.enabled", True))
    VOCAB_DECK = str(cfg_get("example_gate.vocab_deck", "")).strip()
    EXAMPLE_DECK = str(cfg_get("example_gate.example_deck", "")).strip()
    VOCAB_KEY_FIELD = str(cfg_get("example_gate.vocab_key_field", "Vocab"))
    EXAMPLE_KEY_FIELD = str(cfg_get("example_gate.example_key_field", "Vocab"))
    EX_STAGE_SEP = str(cfg_get("example_gate.example_stage_syntax.separator", "@"))
    EX_STAGE_DEFAULT = int(cfg_get("example_gate.example_stage_syntax.default_stage", 0))
    EX_APPLY_ALL_CARDS = bool(
        cfg_get("example_gate.example_action.apply_to_all_cards_in_note", True)
    )

    key_norm = cfg_get("example_gate.key_normalization", {}) or {}
    if isinstance(key_norm, dict):
        KEY_STRIP_HTML = bool(key_norm.get("strip_html", True))
        KEY_STRIP_FURIGANA_BR = bool(key_norm.get("strip_furigana_brackets", False))
        KEY_TRIM = bool(key_norm.get("trim", True))
        KEY_NFC = bool(key_norm.get("unicode_nfc", True))
        KEY_FIRST_TOKEN = bool(key_norm.get("first_token_only", True))
    else:
        KEY_STRIP_HTML = True
        KEY_STRIP_FURIGANA_BR = False
        KEY_TRIM = True
        KEY_NFC = True
        KEY_FIRST_TOKEN = True

    FAMILY_NOTE_TYPES = cfg_get("family_gate.note_types", {}) or {}

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

    if _mw is not None and getattr(_mw, "col", None):
        col = _mw.col
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
    msg = f"[ExampleGate {ts}] {line}"

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


DEFAULT_STICKY_TAG_BASE = "_intern::family_gate::unlocked"
DEFAULT_EXAMPLE_TAG_PREFIX = "_intern::family_gate::unlocked::example_stage"

_HTML_RE = re.compile(r"<.*?>", re.DOTALL)
_FURIGANA_BR_RE = re.compile(r"\[[^\]]*\]")


def _strip_html(s: str) -> str:
    return _HTML_RE.sub("", s)


def strip_furigana_brackets(s: str) -> str:
    return _FURIGANA_BR_RE.sub("", s or "")


def norm_text(s: str) -> str:
    s = s or ""
    if config.KEY_STRIP_HTML:
        s = _strip_html(s)
    if config.KEY_STRIP_FURIGANA_BR:
        s = _FURIGANA_BR_RE.sub("", s)
    if config.KEY_TRIM:
        s = s.strip()
    if config.KEY_NFC:
        s = unicodedata.normalize("NFC", s)
    if config.KEY_FIRST_TOKEN:
        s = s.split(" ")[0] if s else ""
    return s


@dataclass(frozen=True)
class ExampleRef:
    key: str
    stage: int


def parse_example_key(raw: str) -> ExampleRef:
    s = norm_text(raw or "")
    if not s:
        return ExampleRef(key="", stage=config.EX_STAGE_DEFAULT)

    if config.EX_STAGE_SEP and config.EX_STAGE_SEP in s:
        left, right = s.rsplit(config.EX_STAGE_SEP, 1)
        key = norm_text(left)
        try:
            stage = int(right.strip())
        except Exception:
            stage = config.EX_STAGE_DEFAULT
        return ExampleRef(key=key, stage=stage)

    return ExampleRef(key=s, stage=config.EX_STAGE_DEFAULT)


def example_stage_tag(stage_index: int) -> str:
    return f"{DEFAULT_EXAMPLE_TAG_PREFIX}{stage_index}"


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


def _anki_quote(s: str) -> str:
    return (s or "").replace("\\", "\\\\").replace('"', '\\"')


def note_ids_for_deck(col: Collection, deck_name: str) -> list[int]:
    dn = _anki_quote(deck_name)
    q = f'deck:"{dn}"'
    if config.DEBUG:
        dbg("note_ids_for_deck", deck_name, "->", q)
    try:
        found = col.find_notes(q)
        if config.DEBUG:
            dbg("note_ids_for_deck count", deck_name, len(found))
        return found
    except Exception:
        if config.DEBUG:
            dbg("note_ids_for_deck failed", q)
            dbg(traceback.format_exc())
        return []


@dataclass
class VocabIndexEntry:
    nid: int
    note_type_id: int
    stage_stabs: list[float | None]


def example_gate_apply(col: Collection, ui_set, counters: dict[str, int]) -> None:
    if not config.EXAMPLE_GATE_ENABLED:
        dbg("example_gate disabled")
        return
    if not config.VOCAB_DECK or not config.EXAMPLE_DECK:
        dbg(
            "example_gate: missing deck config",
            "vocab_deck=",
            config.VOCAB_DECK,
            "example_deck=",
            config.EXAMPLE_DECK,
        )
        return
    if not config.VOCAB_KEY_FIELD or not config.EXAMPLE_KEY_FIELD:
        dbg(
            "example_gate: missing key field config",
            "vocab_key_field=",
            config.VOCAB_KEY_FIELD,
            "example_key_field=",
            config.EXAMPLE_KEY_FIELD,
        )
        return

    vocab_nids = note_ids_for_deck(col, config.VOCAB_DECK)
    dbg("example_gate: vocab notes", len(vocab_nids))

    vocab_index: dict[str, VocabIndexEntry] = {}

    for i, nid in enumerate(vocab_nids):
        try:
            note = col.get_note(nid)
            nt_id = int(note.mid)

            if str(nt_id) not in config.FAMILY_NOTE_TYPES:
                continue
            if config.VOCAB_KEY_FIELD not in note:
                continue

            key = norm_text(str(note[config.VOCAB_KEY_FIELD] or ""))
            if not key:
                continue
            if key in vocab_index:
                continue

            stabs = compute_stage_stabilities(col, note, nt_id)
            vocab_index[key] = VocabIndexEntry(nid=nid, note_type_id=nt_id, stage_stabs=stabs)

            if config.DEBUG and i < 10:
                dbg("example_gate: indexed", key, "stabs", stabs)

            if i % 400 == 0:
                ui_set(
                    f"ExampleGate: index vocab... {i}/{len(vocab_nids)} (keys={len(vocab_index)})",
                    i,
                    len(vocab_nids),
                )
        except Exception:
            dbg("example_gate: exception indexing vocab nid", nid)
            dbg(traceback.format_exc())

    dbg("example_gate: vocab keys", len(vocab_index))

    ex_nids = note_ids_for_deck(col, config.EXAMPLE_DECK)
    dbg("example_gate: example notes", len(ex_nids))

    to_suspend: list[int] = []
    to_unsuspend: list[int] = []

    for i, nid in enumerate(ex_nids):
        try:
            note = col.get_note(nid)
            if config.EXAMPLE_KEY_FIELD not in note:
                continue

            ref = parse_example_key(str(note[config.EXAMPLE_KEY_FIELD] or ""))
            if not ref.key:
                continue

            entry = vocab_index.get(ref.key)

            ex_tag = example_stage_tag(ref.stage)
            is_sticky = config.STICKY_UNLOCK and (ex_tag in note.tags)

            allow = False
            reason = ""

            if entry is None:
                allow = False
                reason = "no_vocab_match"
            elif 0 <= ref.stage < len(entry.stage_stabs):
                stab_val = entry.stage_stabs[ref.stage]
                allow = stage_is_ready(entry.note_type_id, ref.stage, stab_val)
                thr = get_stage_cfg_for_note_type(entry.note_type_id)[ref.stage].threshold
                reason = f"stab={stab_val} thr={thr}"
            else:
                allow = False
                reason = "stage_oob"

            if config.EX_APPLY_ALL_CARDS:
                cids = [c.id for c in note.cards()]
            else:
                cards = note.cards()
                cids = [cards[0].id] if cards else []

            if not cids:
                continue

            should_allow = allow or is_sticky
            if should_allow:
                to_unsuspend.extend(cids)
                if config.DEBUG and i < 50:
                    dbg(
                        "example_gate: UNSUSP",
                        nid,
                        ref.key,
                        "@",
                        ref.stage,
                        "sticky=",
                        is_sticky,
                        reason,
                    )

                if config.STICKY_UNLOCK and allow and ex_tag not in note.tags:
                    note.add_tag(DEFAULT_STICKY_TAG_BASE)
                    note.add_tag(ex_tag)
                    note.flush()
                    counters["example_notes_tagged"] += 1
            else:
                to_suspend.extend(cids)
                if config.DEBUG and i < 50:
                    dbg(
                        "example_gate: SUSP",
                        nid,
                        ref.key,
                        "@",
                        ref.stage,
                        "sticky=",
                        is_sticky,
                        reason,
                    )

            if i % 250 == 0:
                ui_set(
                    f"ExampleGate: {i}/{len(ex_nids)} | keys={len(vocab_index)} | pending unsusp={len(to_unsuspend)} susp={len(to_suspend)} | {ref.key}@{ref.stage}",
                    i,
                    len(ex_nids),
                )
        except Exception:
            dbg("example_gate: exception processing example nid", nid)
            dbg(traceback.format_exc())

    if to_suspend:
        sus = list(set(to_suspend))
        suspend_cards(col, sus)
        counters["example_cards_suspended"] += len(sus)
        _verify_suspended(col, sus, label="example_suspend")

    if to_unsuspend:
        uns = list(set(to_unsuspend))
        unsuspend_cards(col, uns)
        counters["example_cards_unsuspended"] += len(uns)
        _verify_suspended(col, uns, label="example_unsuspend")


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


def run_example_gate(*, reason: str = "manual") -> None:
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
        dbg("example_gate: skip (run_on_sync disabled)")
        return
    if reason == "manual" and not config.RUN_ON_UI:
        dbg("example_gate: skip (run_on_ui disabled)")
        return
    if not config.EXAMPLE_GATE_ENABLED:
        dbg("example_gate: skip (disabled)")
        return

    def ui_set(label: str, value: int, maxv: int) -> None:
        def _do() -> None:
            try:
                if mw.progress.want_cancel():
                    dbg("example_gate: cancelled")
                    return
                mw.progress.update(label=label, value=value, max=maxv)
            except Exception:
                return

        mw.taskman.run_on_main(_do)

    def op(col: Collection):
        undo_entry = col.add_custom_undo_entry("Example Gate")

        counters = {
            "example_cards_suspended": 0,
            "example_cards_unsuspended": 0,
            "example_notes_tagged": 0,
        }

        ui_set("ExampleGate: start...", 0, 1)
        example_gate_apply(col, ui_set, counters)

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
            "Example Gate finished.\n"
            f"unsuspended={c.get('example_cards_unsuspended', 0)} "
            f"suspended={c.get('example_cards_suspended', 0)} "
            f"tagged_notes={c.get('example_notes_tagged', 0)}"
        )
        if config.DEBUG:
            dbg("RESULT", msg)
        _notify_info(msg, reason=reason)

    def on_failure(err: Exception) -> None:
        tb = "".join(traceback.format_exception(type(err), err, err.__traceback__))
        if config.DEBUG:
            dbg("FAILURE", repr(err))
            dbg(tb)
        _notify_error("Example Gate failed:\n" + tb, reason=reason)

    CollectionOp(parent=mw, op=op).success(on_success).failure(on_failure).run_in_background()


def _build_settings(ctx):
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

    ctx.add_tab(example_tab, "Example Gate")

    def _save(cfg: dict, errors: list[str]) -> None:
        ex_stage_sep = example_stage_sep_edit.text().strip()
        if not ex_stage_sep:
            errors.append("Example stage separator cannot be empty.")

        config._cfg_set(cfg, "example_gate.enabled", bool(example_enabled_cb.isChecked()))
        config._cfg_set(cfg, "example_gate.vocab_deck", _combo_value(vocab_deck_combo))
        config._cfg_set(cfg, "example_gate.example_deck", _combo_value(example_deck_combo))
        config._cfg_set(cfg, "example_gate.vocab_key_field", vocab_key_edit.text().strip())
        config._cfg_set(cfg, "example_gate.example_key_field", example_key_edit.text().strip())
        config._cfg_set(cfg, "example_gate.example_stage_syntax.separator", ex_stage_sep)
        config._cfg_set(
            cfg,
            "example_gate.example_stage_syntax.default_stage",
            int(example_default_stage_spin.value()),
        )

    return _save


def _enabled_example() -> bool:
    return bool(config.RUN_ON_UI and config.EXAMPLE_GATE_ENABLED)


def _init() -> None:
    from aqt import gui_hooks, mw

    def _on_sync_finished() -> None:
        run_example_gate(reason="sync")

    if config.RUN_ON_SYNC:
        if mw is not None and not getattr(mw, "_ajpc_examplegate_sync_hook_installed", False):
            gui_hooks.sync_did_finish.append(_on_sync_finished)
            mw._ajpc_examplegate_sync_hook_installed = True


MODULE = ModuleSpec(
    id="example_gate",
    label="Example Gate",
    order=30,
    init=_init,
    run_items=[
        {
            "label": "Run Example Gate",
            "callback": lambda: run_example_gate(reason="manual"),
            "enabled_fn": _enabled_example,
            "order": 20,
        }
    ],
    build_settings=_build_settings,
)

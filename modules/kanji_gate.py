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
    QLabel,
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

KANJI_GATE_ENABLED = True
KANJI_GATE_BEHAVIOR = "kanji_and_components"
KANJI_GATE_STABILITY_AGG = "min"
KANJI_GATE_VOCAB_NOTE_TYPES: dict[str, Any] = {}
KANJI_GATE_KANJI_NOTE_TYPE = ""
KANJI_GATE_KANJI_FIELD = ""
KANJI_GATE_KANJI_ALT_FIELD = ""
KANJI_GATE_COMPONENTS_FIELD = ""
KANJI_GATE_KANJI_RADICAL_FIELD = ""
KANJI_GATE_RADICAL_NOTE_TYPE = ""
KANJI_GATE_RADICAL_FIELD = ""
KANJI_GATE_KANJI_THRESHOLD = 0.0
KANJI_GATE_COMPONENT_THRESHOLD = 0.0


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
    global RUN_ON_SYNC, RUN_ON_UI
    global STICKY_UNLOCK, STABILITY_DEFAULT_THRESHOLD, STABILITY_AGG
    global WATCH_NIDS
    global KANJI_GATE_ENABLED, KANJI_GATE_BEHAVIOR, KANJI_GATE_STABILITY_AGG
    global KANJI_GATE_VOCAB_NOTE_TYPES
    global KANJI_GATE_KANJI_NOTE_TYPE, KANJI_GATE_KANJI_FIELD, KANJI_GATE_KANJI_ALT_FIELD
    global KANJI_GATE_COMPONENTS_FIELD, KANJI_GATE_KANJI_RADICAL_FIELD
    global KANJI_GATE_RADICAL_NOTE_TYPE, KANJI_GATE_RADICAL_FIELD
    global KANJI_GATE_KANJI_THRESHOLD, KANJI_GATE_COMPONENT_THRESHOLD

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
    if STABILITY_AGG not in ("min", "max", "avg"):
        STABILITY_AGG = "min"

    KANJI_GATE_ENABLED = bool(cfg_get("kanji_gate.enabled", True))
    KANJI_GATE_BEHAVIOR = str(cfg_get("kanji_gate.behavior", "kanji_and_components")).strip()
    if not KANJI_GATE_BEHAVIOR:
        KANJI_GATE_BEHAVIOR = "kanji_and_components"
    KANJI_GATE_STABILITY_AGG = str(cfg_get("kanji_gate.stability_aggregation", "min")).lower().strip()
    if KANJI_GATE_STABILITY_AGG not in ("min", "max", "avg"):
        KANJI_GATE_STABILITY_AGG = "min"
    KANJI_GATE_VOCAB_NOTE_TYPES = cfg_get("kanji_gate.vocab_note_types", {}) or {}
    KANJI_GATE_KANJI_NOTE_TYPE = str(cfg_get("kanji_gate.kanji_note_type", "")).strip()
    KANJI_GATE_KANJI_FIELD = str(cfg_get("kanji_gate.kanji_field", "")).strip()
    KANJI_GATE_KANJI_ALT_FIELD = str(cfg_get("kanji_gate.kanji_alt_field", "")).strip()
    KANJI_GATE_COMPONENTS_FIELD = str(cfg_get("kanji_gate.components_field", "")).strip()
    KANJI_GATE_KANJI_RADICAL_FIELD = str(cfg_get("kanji_gate.kanji_radical_field", "")).strip()
    KANJI_GATE_RADICAL_NOTE_TYPE = str(cfg_get("kanji_gate.radical_note_type", "")).strip()
    KANJI_GATE_RADICAL_FIELD = str(cfg_get("kanji_gate.radical_field", "")).strip()
    KANJI_GATE_KANJI_THRESHOLD = float(
        cfg_get("kanji_gate.kanji_threshold", STABILITY_DEFAULT_THRESHOLD)
    )
    KANJI_GATE_COMPONENT_THRESHOLD = float(
        cfg_get("kanji_gate.component_threshold", STABILITY_DEFAULT_THRESHOLD)
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
            KANJI_GATE_VOCAB_NOTE_TYPES = _map_dict_keys(col, KANJI_GATE_VOCAB_NOTE_TYPES)
            if KANJI_GATE_KANJI_NOTE_TYPE:
                KANJI_GATE_KANJI_NOTE_TYPE = _note_type_id_from_ident(col, KANJI_GATE_KANJI_NOTE_TYPE)
            if KANJI_GATE_RADICAL_NOTE_TYPE:
                KANJI_GATE_RADICAL_NOTE_TYPE = _note_type_id_from_ident(col, KANJI_GATE_RADICAL_NOTE_TYPE)


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
    msg = f"[KanjiGate {ts}] {line}"

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


_FURIGANA_BR_RE = re.compile(r"\[[^\]]*\]")
_KANJI_RE = re.compile(r"[\u2E80-\u2EFF\u2F00-\u2FDF\u3400-\u4DBF\u4E00-\u9FFF\uF900-\uFAFF]")


def strip_furigana_brackets(s: str) -> str:
    return _FURIGANA_BR_RE.sub("", s or "")


def extract_kanji(s: str) -> list[str]:
    return _KANJI_RE.findall(s or "")


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

KANJI_STICKY_TAG_BASE = "_intern::kanji_gate::unlocked"
KANJI_STICKY_TAG_VOCAB = f"{KANJI_STICKY_TAG_BASE}::vocab_kanjiform"
KANJI_STICKY_TAG_KANJI = f"{KANJI_STICKY_TAG_BASE}::kanji"
KANJI_STICKY_TAG_RADICAL = f"{KANJI_STICKY_TAG_BASE}::radical"


@dataclass(frozen=True)
class VocabCfg:
    note_type_id: str
    furigana_field: str
    base_templates: list[str]
    kanji_templates: list[str]
    base_threshold: float


@dataclass(frozen=True)
class VocabNoteInfo:
    nid: int
    kanji: list[str]
    base_ready: bool
    kanji_card_ids: list[int]


@dataclass(frozen=True)
class KanjiNoteEntry:
    nid: int
    components: list[str]
    radicals: list[str]


def _agg(vals: list[float], mode: str) -> float | None:
    if not vals:
        return None
    if mode == "max":
        return max(vals)
    if mode == "avg":
        return sum(vals) / len(vals)
    return min(vals)


def _templates_stability(note, templates: set[str], mode: str) -> float | None:
    if not templates:
        return None
    vals: list[float] = []
    saw_any = False
    for card in note.cards():
        if str(card.ord) in templates:
            saw_any = True
            stab = card_stability(card)
            if stab is None:
                return None
            vals.append(stab)
    if not saw_any:
        return None
    return _agg(vals, mode)


def _note_stability(note, mode: str) -> float | None:
    vals: list[float] = []
    for card in note.cards():
        stab = card_stability(card)
        if stab is None:
            return None
        vals.append(stab)
    return _agg(vals, mode)


def _note_has_kanji_sticky_tag(note) -> bool:
    if not config.STICKY_UNLOCK:
        return False
    for tag in note.tags:
        if tag == KANJI_STICKY_TAG_BASE or tag.startswith(f"{KANJI_STICKY_TAG_BASE}::"):
            return True
    return False


def _tag_note(note, tag: str) -> None:
    if not config.STICKY_UNLOCK:
        return
    if tag in note.tags:
        return
    note.add_tag(KANJI_STICKY_TAG_BASE)
    note.add_tag(tag)
    note.flush()


def _get_vocab_cfgs() -> dict[str, VocabCfg]:
    raw = config.KANJI_GATE_VOCAB_NOTE_TYPES
    if not isinstance(raw, dict):
        return {}
    out: dict[str, VocabCfg] = {}
    for nt_name, cfg in raw.items():
        if not nt_name or not isinstance(cfg, dict):
            continue
        furigana_field = str(cfg.get("furigana_field", "")).strip()
        base_templates = [
            _template_ord_from_value(str(nt_name), x)
            for x in (cfg.get("base_templates") or [])
        ]
        base_templates = [t for t in base_templates if t]
        kanji_templates = [
            _template_ord_from_value(str(nt_name), x)
            for x in (cfg.get("kanji_templates") or [])
        ]
        kanji_templates = [t for t in kanji_templates if t]
        base_threshold = float(cfg.get("base_threshold", config.STABILITY_DEFAULT_THRESHOLD))
        out[str(nt_name)] = VocabCfg(
            note_type_id=str(nt_name),
            furigana_field=furigana_field,
            base_templates=base_templates,
            kanji_templates=kanji_templates,
            base_threshold=base_threshold,
        )
    return out


def kanji_gate_apply(col: Collection, ui_set, counters: dict[str, int]) -> None:
    if not config.KANJI_GATE_ENABLED:
        dbg("kanji_gate disabled")
        return

    behavior = str(config.KANJI_GATE_BEHAVIOR or "").strip()
    if behavior not in (
        "kanji_only",
        "kanji_then_components",
        "components_then_kanji",
        "kanji_and_components",
    ):
        dbg("kanji_gate: invalid behavior", behavior)
        return

    agg_mode = str(config.KANJI_GATE_STABILITY_AGG or "min").strip()
    if agg_mode not in ("min", "max", "avg"):
        agg_mode = "min"

    vocab_cfgs = _get_vocab_cfgs()
    if not vocab_cfgs:
        dbg("kanji_gate: no vocab note types configured")
        return

    kanji_note_type = config.KANJI_GATE_KANJI_NOTE_TYPE
    kanji_field = config.KANJI_GATE_KANJI_FIELD
    kanji_alt_field = config.KANJI_GATE_KANJI_ALT_FIELD
    components_field = config.KANJI_GATE_COMPONENTS_FIELD
    kanji_radical_field = config.KANJI_GATE_KANJI_RADICAL_FIELD
    radical_note_type = config.KANJI_GATE_RADICAL_NOTE_TYPE
    radical_field = config.KANJI_GATE_RADICAL_FIELD

    if not kanji_note_type or not kanji_field:
        dbg("kanji_gate: missing kanji config")
        return

    use_components = behavior in ("kanji_then_components", "components_then_kanji", "kanji_and_components")
    if use_components and not components_field:
        dbg("kanji_gate: missing components field")
        return

    radicals_enabled = bool(use_components and kanji_radical_field and radical_note_type and radical_field)

    vocab_note_types = list(vocab_cfgs.keys())
    vocab_nids = note_ids_for_note_types(col, vocab_note_types)
    dbg("kanji_gate: vocab notes", len(vocab_nids))

    vocab_notes: list[VocabNoteInfo] = []
    target_kanji: set[str] = set()
    vocab_kanji_scope_cards: set[int] = set()

    note_cache: dict[int, Any] = {}
    def _get_note(nid: int):
        if nid not in note_cache:
            note_cache[nid] = col.get_note(nid)
        return note_cache[nid]

    for i, nid in enumerate(vocab_nids):
        try:
            note = _get_note(nid)
            model = col.models.get(note.mid)
            nt_name = str(model.get("name", "")) if model else ""
            nt_id = str(note.mid)
            cfg = vocab_cfgs.get(nt_id) or vocab_cfgs.get(nt_name)
            if not cfg:
                continue
            if cfg.furigana_field not in note:
                continue

            raw = str(note[cfg.furigana_field] or "")
            cleaned = strip_furigana_brackets(raw)
            kanji_list = extract_kanji(cleaned)
            if not kanji_list:
                continue

            base_templates = set(cfg.base_templates)
            base_stab = _templates_stability(note, base_templates, agg_mode)
            base_ready = base_stab is not None and base_stab >= cfg.base_threshold

            kanji_templates = set(cfg.kanji_templates)
            kanji_card_ids: list[int] = []
            if kanji_templates:
                for card in note.cards():
                    if str(card.ord) in kanji_templates:
                        kanji_card_ids.append(card.id)
                if kanji_card_ids:
                    vocab_kanji_scope_cards.update(kanji_card_ids)

            vocab_notes.append(
                VocabNoteInfo(
                    nid=nid,
                    kanji=kanji_list,
                    base_ready=base_ready,
                    kanji_card_ids=kanji_card_ids,
                )
            )

            if base_ready:
                target_kanji.update(kanji_list)

            if i % 400 == 0:
                ui_set(
                    f"KanjiGate: index vocab... {i}/{len(vocab_nids)} (kanji={len(target_kanji)})",
                    i,
                    len(vocab_nids),
                )
        except Exception:
            dbg("kanji_gate: exception indexing vocab nid", nid)
            dbg(traceback.format_exc())

    if not vocab_notes:
        dbg("kanji_gate: no vocab notes with kanji")
        return

    kanji_index: dict[str, list[KanjiNoteEntry]] = {}
    note_chars: dict[int, set[str]] = {}
    all_radicals: set[str] = set()
    kanji_nids = note_ids_for_note_types(col, [kanji_note_type])
    dbg("kanji_gate: kanji notes", len(kanji_nids))

    for i, nid in enumerate(kanji_nids):
        try:
            note = _get_note(nid)
            if kanji_field not in note:
                continue

            keys = extract_kanji(str(note[kanji_field] or ""))
            if kanji_alt_field and kanji_alt_field in note:
                keys.extend(extract_kanji(str(note[kanji_alt_field] or "")))
            if not keys:
                continue

            comps: list[str] = []
            if use_components and components_field in note:
                comps = extract_kanji(str(note[components_field] or ""))

            radicals: list[str] = []
            if radicals_enabled and kanji_radical_field in note:
                radicals = extract_kanji(str(note[kanji_radical_field] or ""))

            key_set = set(keys)
            note_chars[nid] = key_set

            entry = KanjiNoteEntry(nid=nid, components=comps, radicals=radicals)
            for k in key_set:
                kanji_index.setdefault(k, []).append(entry)
            if radicals:
                all_radicals.update(radicals)

            if i % 400 == 0:
                ui_set(
                    f"KanjiGate: index kanji... {i}/{len(kanji_nids)} (keys={len(kanji_index)})",
                    i,
                    len(kanji_nids),
                )
        except Exception:
            dbg("kanji_gate: exception indexing kanji nid", nid)
            dbg(traceback.format_exc())

    radical_index: dict[str, list[int]] = {}
    if radicals_enabled:
        radical_nids = note_ids_for_note_types(col, [radical_note_type])
        dbg("kanji_gate: radical notes", len(radical_nids))
        for i, nid in enumerate(radical_nids):
            try:
                note = _get_note(nid)
                if radical_field not in note:
                    continue
                rads = extract_kanji(str(note[radical_field] or ""))
                if not rads:
                    continue
                for rad in set(rads):
                    radical_index.setdefault(rad, []).append(nid)
                if i % 400 == 0:
                    ui_set(
                        f"KanjiGate: index radicals... {i}/{len(radical_nids)} (keys={len(radical_index)})",
                        i,
                        len(radical_nids),
                    )
            except Exception:
                dbg("kanji_gate: exception indexing radical nid", nid)
                dbg(traceback.format_exc())

    radical_scope_note_ids: set[int] = set()
    if radicals_enabled and all_radicals:
        for rad in all_radicals:
            for rnid in radical_index.get(rad, []):
                radical_scope_note_ids.add(rnid)

    def _expand_components(start_chars: set[str]) -> set[str]:
        all_chars = set(start_chars)
        queue = list(start_chars)
        while queue:
            ch = queue.pop()
            for entry in kanji_index.get(ch, []):
                for comp in entry.components:
                    if comp not in all_chars:
                        all_chars.add(comp)
                        queue.append(comp)
        return all_chars

    def _add_note_cards(nid: int, out: set[int]) -> None:
        note = _get_note(nid)
        for card in note.cards():
            out.add(card.id)

    def _radical_note_ids_for_chars(chars: set[str]) -> set[int]:
        if not radicals_enabled:
            return set()
        out: set[int] = set()
        for ch in chars:
            for entry in kanji_index.get(ch, []):
                for rad in entry.radicals:
                    for rnid in radical_index.get(rad, []):
                        out.add(rnid)
        return out

    root_chars = set(target_kanji)
    root_unlock_chars: set[str] = set()
    component_unlock_chars: set[str] = set()
    radical_unlock_chars: set[str] = set()

    if behavior == "kanji_only":
        root_unlock_chars = set(root_chars)

    elif behavior == "kanji_then_components":
        root_unlock_chars = set(root_chars)

        ready_chars: set[str] = set()
        note_stab_cache: dict[int, float | None] = {}
        for ch in root_chars:
            for entry in kanji_index.get(ch, []):
                if entry.nid not in note_stab_cache:
                    note_stab_cache[entry.nid] = _note_stability(_get_note(entry.nid), agg_mode)
                stab = note_stab_cache[entry.nid]
                if stab is not None and stab >= float(config.KANJI_GATE_KANJI_THRESHOLD):
                    ready_chars.add(ch)
                    break

        for ch in ready_chars:
            for entry in kanji_index.get(ch, []):
                component_unlock_chars.update(entry.components)

        radical_unlock_chars = ready_chars | component_unlock_chars

    elif behavior == "components_then_kanji":
        relevant_chars = _expand_components(set(root_chars))

        note_stab_cache: dict[int, float | None] = {}
        char_ready: dict[str, bool] = {}
        for ch in relevant_chars:
            ready_any = False
            for entry in kanji_index.get(ch, []):
                if entry.nid not in note_stab_cache:
                    note_stab_cache[entry.nid] = _note_stability(_get_note(entry.nid), agg_mode)
                stab = note_stab_cache[entry.nid]
                if stab is not None and stab >= float(config.KANJI_GATE_COMPONENT_THRESHOLD):
                    ready_any = True
                    break
            char_ready[ch] = ready_any

        def _components_ready(entry: KanjiNoteEntry) -> bool:
            if not entry.components:
                return True
            for comp in entry.components:
                if comp in kanji_index and not char_ready.get(comp, False):
                    return False
            return True

        unlock_chars: set[str] = set()
        for ch in relevant_chars:
            for entry in kanji_index.get(ch, []):
                if _components_ready(entry):
                    unlock_chars.add(ch)
                    break

        root_unlock_chars = root_chars & unlock_chars
        component_unlock_chars = unlock_chars - root_chars
        radical_unlock_chars = unlock_chars

    elif behavior == "kanji_and_components":
        all_chars = _expand_components(set(root_chars))
        root_unlock_chars = set(root_chars)
        component_unlock_chars = all_chars - root_chars
        radical_unlock_chars = all_chars

    vocab_kanji_allow_cards: set[int] = set()
    unlocked_chars = root_unlock_chars | component_unlock_chars
    for i, info in enumerate(vocab_notes):
        try:
            note = _get_note(info.nid)
            is_sticky = _note_has_kanji_sticky_tag(note)
            if behavior == "components_then_kanji":
                eligible = info.base_ready and all(
                    (ch in unlocked_chars) or (ch not in kanji_index) for ch in info.kanji
                )
            else:
                eligible = info.base_ready

            if eligible or is_sticky:
                vocab_kanji_allow_cards.update(info.kanji_card_ids)
                if config.STICKY_UNLOCK and eligible and not is_sticky:
                    _tag_note(note, KANJI_STICKY_TAG_VOCAB)

            if i % 400 == 0:
                ui_set(
                    f"KanjiGate: apply vocab... {i}/{len(vocab_notes)} (allow={len(vocab_kanji_allow_cards)})",
                    i,
                    len(vocab_notes),
                )
        except Exception:
            dbg("kanji_gate: exception applying vocab nid", info.nid)
            dbg(traceback.format_exc())

    kanji_scope_cards: set[int] = set()
    component_scope_cards: set[int] = set()
    kanji_allow_cards: set[int] = set()
    component_allow_cards: set[int] = set()

    note_items = list(note_chars.items())
    for i, (nid, chars) in enumerate(note_items):
        try:
            note = _get_note(nid)
            is_sticky = _note_has_kanji_sticky_tag(note)
            if chars & root_chars:
                _add_note_cards(nid, kanji_scope_cards)
                eligible = bool(chars & root_unlock_chars)
                if eligible or is_sticky:
                    _add_note_cards(nid, kanji_allow_cards)
                    if config.STICKY_UNLOCK and eligible and not is_sticky:
                        _tag_note(note, KANJI_STICKY_TAG_KANJI)
            else:
                _add_note_cards(nid, component_scope_cards)
                eligible = bool(chars & component_unlock_chars)
                if eligible or is_sticky:
                    _add_note_cards(nid, component_allow_cards)
                    if config.STICKY_UNLOCK and eligible and not is_sticky:
                        _tag_note(note, KANJI_STICKY_TAG_KANJI)

            if i % 400 == 0:
                ui_set(
                    f"KanjiGate: apply kanji... {i}/{len(note_items)} (allow={len(kanji_allow_cards) + len(component_allow_cards)})",
                    i,
                    len(note_items),
                )
        except Exception:
            dbg("kanji_gate: exception applying kanji nid", nid)
            dbg(traceback.format_exc())

    radical_scope_cards: set[int] = set()
    radical_allow_cards: set[int] = set()
    if radicals_enabled and radical_scope_note_ids:
        allowed_radical_note_ids = _radical_note_ids_for_chars(radical_unlock_chars)
        rnids = list(radical_scope_note_ids)
        for i, rnid in enumerate(rnids):
            try:
                note = _get_note(rnid)
                is_sticky = _note_has_kanji_sticky_tag(note)
                _add_note_cards(rnid, radical_scope_cards)
                eligible = rnid in allowed_radical_note_ids
                if eligible or is_sticky:
                    _add_note_cards(rnid, radical_allow_cards)
                    if config.STICKY_UNLOCK and eligible and not is_sticky:
                        _tag_note(note, KANJI_STICKY_TAG_RADICAL)

                if i % 400 == 0:
                    ui_set(
                        f"KanjiGate: apply radicals... {i}/{len(rnids)} (allow={len(radical_allow_cards)})",
                        i,
                        len(rnids),
                    )
            except Exception:
                dbg("kanji_gate: exception applying radical nid", rnid)
                dbg(traceback.format_exc())

    vocab_susp = vocab_kanji_scope_cards - vocab_kanji_allow_cards
    kanji_susp = kanji_scope_cards - kanji_allow_cards
    component_susp = component_scope_cards - component_allow_cards
    radical_susp = radical_scope_cards - radical_allow_cards

    to_suspend = vocab_susp | kanji_susp | component_susp | radical_susp
    to_unsuspend = vocab_kanji_allow_cards | kanji_allow_cards | component_allow_cards | radical_allow_cards
    to_suspend.difference_update(to_unsuspend)

    if to_suspend:
        suspend_cards(col, list(to_suspend))
        counters["kanji_gate_cards_suspended"] += len(to_suspend)
        _verify_suspended(col, list(to_suspend), label="kanji_gate_suspend")

    if to_unsuspend:
        unsuspend_cards(col, list(to_unsuspend))
        counters["vocab_kanji_cards_unsuspended"] += len(vocab_kanji_allow_cards)
        counters["kanji_cards_unsuspended"] += len(kanji_allow_cards)
        counters["component_cards_unsuspended"] += len(component_allow_cards)
        counters["radical_cards_unsuspended"] += len(radical_allow_cards)
        _verify_suspended(col, list(to_unsuspend), label="kanji_gate_unsuspend")


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


def run_kanji_gate(*, reason: str = "manual") -> None:
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

    if not mw.col:
        _notify_error("No collection loaded.", reason=reason)
        return

    if reason == "sync" and not config.RUN_ON_SYNC:
        dbg("kanji_gate: skip (run_on_sync disabled)")
        return
    if reason == "manual" and not config.RUN_ON_UI:
        dbg("kanji_gate: skip (run_on_ui disabled)")
        return
    if not config.KANJI_GATE_ENABLED:
        dbg("kanji_gate: skip (disabled)")
        return

    def ui_set(label: str, value: int, maxv: int) -> None:
        def _do() -> None:
            try:
                if mw.progress.want_cancel():
                    dbg("kanji_gate: cancelled")
                    return
                mw.progress.update(label=label, value=value, max=maxv)
            except Exception:
                return

        mw.taskman.run_on_main(_do)

    def op(col: Collection):
        undo_entry = col.add_custom_undo_entry("Kanji Gate")

        counters = {
            "vocab_kanji_cards_unsuspended": 0,
            "kanji_cards_unsuspended": 0,
            "component_cards_unsuspended": 0,
            "radical_cards_unsuspended": 0,
            "kanji_gate_cards_suspended": 0,
        }

        ui_set("KanjiGate: start...", 0, 1)
        kanji_gate_apply(col, ui_set, counters)

        class _Result:
            def __init__(self, changes, counts: dict[str, int]):
                self.changes = changes
                self.counts = counts

        try:
            changes = col.merge_undo_entries(undo_entry)
        except InvalidInput:
            if config.DEBUG:
                dbg(
                    "merge_undo_entries skipped: target undo op not found",
                    f"undo_entry={undo_entry}",
                )
            changes = OpChanges()

        if changes is None:
            changes = OpChanges()

        return _Result(changes, counters)

    def on_success(result) -> None:
        if reason == "sync":
            return
        c = getattr(result, "counts", {}) or {}
        msg = (
            "Kanji Gate finished.\n"
            f"vocab_kanjiform_unsuspended={c.get('vocab_kanji_cards_unsuspended', 0)} "
            f"kanji_unsuspended={c.get('kanji_cards_unsuspended', 0)} "
            f"components_unsuspended={c.get('component_cards_unsuspended', 0)} "
            f"radical_unsuspended={c.get('radical_cards_unsuspended', 0)} "
            f"suspended={c.get('kanji_gate_cards_suspended', 0)}"
        )
        if config.DEBUG:
            dbg("RESULT", msg)
        _notify_info(msg, reason=reason)

    def on_failure(err: Exception) -> None:
        tb = "".join(traceback.format_exception(type(err), err, err.__traceback__))
        if config.DEBUG:
            dbg("FAILURE", repr(err))
            dbg(tb)
        _notify_error("Kanji Gate failed:\n" + tb, reason=reason)

    CollectionOp(parent=mw, op=op).success(on_success).failure(on_failure).run_in_background()


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


def _build_settings(ctx):
    kanji_tab = QWidget()
    kanji_layout = QVBoxLayout()
    kanji_tab.setLayout(kanji_layout)
    kanji_tabs = QTabWidget()
    kanji_layout.addWidget(kanji_tabs)

    general_tab = QWidget()
    general_layout = QVBoxLayout()
    general_tab.setLayout(general_layout)
    kanji_form = QFormLayout()
    general_layout.addLayout(kanji_form)

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

    kanji_tabs.addTab(general_tab, "General")

    vocab_tab = QWidget()
    vocab_layout = QVBoxLayout()
    vocab_tab.setLayout(vocab_layout)

    vocab_empty_label = QLabel("Select vocab note types in General tab.")
    vocab_layout.addWidget(vocab_empty_label)

    kanji_vocab_tabs = QTabWidget()
    vocab_layout.addWidget(kanji_vocab_tabs)

    kanji_tabs.addTab(vocab_tab, "Vocab")

    kanji_vocab_state: dict[str, dict[str, Any]] = {}
    for nt_id, nt_cfg in (config.KANJI_GATE_VOCAB_NOTE_TYPES or {}).items():
        if not isinstance(nt_cfg, dict):
            continue
        base_templates = [
            _template_ord_from_value(str(nt_id), x) or str(x).strip()
            for x in (nt_cfg.get("base_templates") or [])
        ]
        base_templates = [t for t in base_templates if t]
        kanji_templates = [
            _template_ord_from_value(str(nt_id), x) or str(x).strip()
            for x in (nt_cfg.get("kanji_templates") or [])
        ]
        kanji_templates = [t for t in kanji_templates if t]
        kanji_vocab_state[str(nt_id)] = {
            "furigana_field": str(nt_cfg.get("furigana_field", "")).strip(),
            "base_templates": base_templates,
            "kanji_templates": kanji_templates,
            "base_threshold": float(
                nt_cfg.get("base_threshold", config.STABILITY_DEFAULT_THRESHOLD)
            ),
        }

    kanji_vocab_widgets: dict[str, dict[str, Any]] = {}

    def _clear_kanji_vocab_layout() -> None:
        while kanji_vocab_tabs.count():
            w = kanji_vocab_tabs.widget(0)
            kanji_vocab_tabs.removeTab(0)
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
        vocab_empty_label.setVisible(not bool(selected_types))
        kanji_vocab_tabs.setVisible(bool(selected_types))
        for nt_id in selected_types:
            cfg = kanji_vocab_state.get(nt_id, {})
            field_names = list(_get_fields_for_note_type(nt_id))
            extra_field = str(cfg.get("furigana_field", "")).strip()
            if extra_field and extra_field not in field_names:
                field_names.append(extra_field)
            field_names = sorted(set(field_names))

            vocab_furigana_combo = QComboBox()
            _populate_field_combo(
                vocab_furigana_combo,
                field_names,
                cfg.get("furigana_field", ""),
            )

            extra_templates: list[str] = []
            extra_templates.extend(list(cfg.get("base_templates", []) or []))
            extra_templates.extend(list(cfg.get("kanji_templates", []) or []))
            template_items = _merge_template_items(_get_template_items(nt_id), extra_templates)
            base_templates_combo, base_templates_model = _make_checkable_combo(
                template_items, list(cfg.get("base_templates", []) or [])
            )
            kanji_templates_combo, kanji_templates_model = _make_checkable_combo(
                template_items, list(cfg.get("kanji_templates", []) or [])
            )

            base_threshold_spin = QDoubleSpinBox()
            base_threshold_spin.setDecimals(2)
            base_threshold_spin.setRange(0, 100000)
            base_threshold_spin.setValue(
                float(cfg.get("base_threshold", config.STABILITY_DEFAULT_THRESHOLD))
            )

            tab = QWidget()
            tab_layout = QVBoxLayout()
            tab.setLayout(tab_layout)

            form = QFormLayout()
            form.addRow("Vocab furigana field", vocab_furigana_combo)
            form.addRow("Vocab base templates (Grundform)", base_templates_combo)
            form.addRow("Vocab kanjiform templates", kanji_templates_combo)
            form.addRow("Base threshold", base_threshold_spin)
            tab_layout.addLayout(form)
            tab_layout.addStretch(1)

            kanji_vocab_widgets[nt_id] = {
                "furigana_combo": vocab_furigana_combo,
                "base_templates_model": base_templates_model,
                "kanji_templates_model": kanji_templates_model,
                "base_threshold_spin": base_threshold_spin,
            }
            kanji_vocab_tabs.addTab(tab, _note_type_label(nt_id))

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

    ctx.add_tab(kanji_tab, "Kanji Gate")

    def _save(cfg: dict, errors: list[str]) -> None:
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
            base_templates = [t for t in base_templates if t.isdigit()]
            kanji_templates = [
                str(x).strip()
                for x in (cfg_state.get("kanji_templates") or [])
                if str(x).strip()
            ]
            kanji_templates = [t for t in kanji_templates if t.isdigit()]
            base_threshold = float(cfg_state.get("base_threshold", config.STABILITY_DEFAULT_THRESHOLD))

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

    return _save


def _enabled_kanji() -> bool:
    return bool(config.RUN_ON_UI and config.KANJI_GATE_ENABLED)


def _init() -> None:
    from aqt import gui_hooks, mw as _mw

    def _on_sync_finished() -> None:
        run_kanji_gate(reason="sync")

    if config.RUN_ON_SYNC:
        if _mw is not None and not getattr(_mw, "_ajpc_kanjigate_sync_hook_installed", False):
            gui_hooks.sync_did_finish.append(_on_sync_finished)
            _mw._ajpc_kanjigate_sync_hook_installed = True


MODULE = ModuleSpec(
    id="kanji_gate",
    label="Kanji Gate",
    order=40,
    init=_init,
    run_items=[
        {
            "label": "Run Kanji Gate",
            "callback": lambda: run_kanji_gate(reason="manual"),
            "enabled_fn": _enabled_kanji,
            "order": 30,
        }
    ],
    build_settings=_build_settings,
)

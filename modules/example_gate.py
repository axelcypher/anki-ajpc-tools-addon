from __future__ import annotations

from collections import Counter
import json
import os
import re
import time
import traceback
import unicodedata
from dataclasses import dataclass
from typing import Any, Iterable

import aqt
from anki.collection import Collection, OpChanges
from anki.errors import InvalidInput
from aqt import mw
from aqt.operations import CollectionOp
from aqt.qt import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QFrame,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from aqt.utils import tooltip

from .. import logging as core_logging
from . import ModuleSpec
from ._widgets.deck_stats_registry import count_unsuspended_cards, register_provider

ADDON_DIR = os.path.dirname(os.path.dirname(__file__))
CONFIG_PATH = os.path.join(ADDON_DIR, "config.json")

CFG: dict[str, Any] = {}
DEBUG = False
DEBUG_VERIFY_SUSPENSION = False
RUN_ON_SYNC = True
RUN_ON_UI = True
STICKY_UNLOCK = True
STABILITY_DEFAULT_THRESHOLD = 14.0
STABILITY_AGG = "min"
WATCH_NIDS: set[int] = set()

EXAMPLE_GATE_ENABLED = True
EXAMPLE_GATE_RUN_ON_SYNC = True
VOCAB_DECK = ""
EXAMPLE_DECK = ""
VOCAB_KEY_FIELD = "Vocab"
EXAMPLE_KEY_FIELD = "Vocab"
EXAMPLE_READING_FIELD = "VocabReading"
EX_STAGE_SEP = "@"
EX_STAGE_DEFAULT = 0
EX_APPLY_ALL_CARDS = True
EXAMPLE_THRESHOLD = 14.0

KEY_STRIP_HTML = True
KEY_TRIM = True
KEY_NFC = True
KEY_FIRST_TOKEN = True
KEY_STRIP_FURIGANA_BR = False


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
    global EXAMPLE_GATE_ENABLED, EXAMPLE_GATE_RUN_ON_SYNC, VOCAB_DECK, EXAMPLE_DECK
    global VOCAB_KEY_FIELD, EXAMPLE_KEY_FIELD, EXAMPLE_READING_FIELD, EX_STAGE_SEP, EX_STAGE_DEFAULT, EX_APPLY_ALL_CARDS
    global EXAMPLE_THRESHOLD
    global KEY_STRIP_HTML, KEY_TRIM, KEY_NFC, KEY_FIRST_TOKEN, KEY_STRIP_FURIGANA_BR

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

    EXAMPLE_GATE_ENABLED = bool(cfg_get("example_gate.enabled", True))
    EXAMPLE_GATE_RUN_ON_SYNC = bool(cfg_get("example_gate.run_on_sync", True))
    VOCAB_DECK = str(cfg_get("example_gate.vocab_deck", "")).strip()
    EXAMPLE_DECK = str(cfg_get("example_gate.example_deck", "")).strip()
    _key_field = str(
        cfg_get(
            "example_gate.key_field",
            cfg_get("example_gate.example_key_field", cfg_get("example_gate.vocab_key_field", "Vocab")),
        )
    ).strip()
    if not _key_field:
        _key_field = "Vocab"
    VOCAB_KEY_FIELD = _key_field
    EXAMPLE_KEY_FIELD = _key_field
    _reading_field = str(cfg_get("example_gate.reading_field", "VocabReading")).strip()
    EXAMPLE_READING_FIELD = _reading_field or "VocabReading"
    EX_STAGE_SEP = str(cfg_get("example_gate.example_stage_syntax.separator", "@"))
    EX_STAGE_DEFAULT = int(cfg_get("example_gate.example_stage_syntax.default_stage", 0))
    EX_APPLY_ALL_CARDS = bool(
        cfg_get("example_gate.example_action.apply_to_all_cards_in_note", True)
    )
    EXAMPLE_THRESHOLD = float(cfg_get("example_gate.threshold", 14.0))

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
    core_logging.trace(*a, source="example_gate")


def log_info(*a: Any) -> None:
    core_logging.info(*a, source="example_gate")


def log_warn(*a: Any) -> None:
    core_logging.warn(*a, source="example_gate")


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


DEFAULT_STICKY_TAG_BASE = "_intern::example_gate::unlocked"
DEFAULT_EXAMPLE_TAG_PREFIX = "_intern::example_gate::unlocked::cid"

_HTML_RE = re.compile(r"<.*?>", re.DOTALL)
_FURIGANA_BR_RE = re.compile(r"\[[^\]]*\]")
_MATCH_PREFIX_MARK_RE = re.compile(r"^[\s~\u301c\uff5e\u223c]+")


def _strip_html(s: str) -> str:
    return _HTML_RE.sub("", s)


def strip_furigana_brackets(s: str) -> str:
    return _FURIGANA_BR_RE.sub("", s or "")


def _strip_match_prefix_markers(s: str) -> str:
    txt = str(s or "")
    while True:
        nxt = _MATCH_PREFIX_MARK_RE.sub("", txt)
        if nxt == txt:
            break
        txt = nxt
    return txt


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
    s = _strip_match_prefix_markers(s)
    if config.KEY_FIRST_TOKEN:
        s = s.split(" ")[0] if s else ""
    return s


def _norm_literal_text(s: str) -> str:
    out = _strip_html(s or "")
    out = out.strip()
    out = unicodedata.normalize("NFC", out)
    out = _strip_match_prefix_markers(out)
    return out


def _norm_reading_key(s: str) -> str:
    raw = norm_text(s or "")
    if not raw:
        return ""
    return _to_hira(raw)


def _extract_vocab_reading_key(note, key_src: str) -> str:
    candidates = [
        str(config.EXAMPLE_READING_FIELD or "").strip(),
        "VocabReading",
        f"{config.VOCAB_KEY_FIELD}Reading" if config.VOCAB_KEY_FIELD else "",
        "Reading",
    ]
    seen: set[str] = set()
    for fname in candidates:
        field = str(fname or "").strip()
        if not field or field in seen:
            continue
        seen.add(field)
        try:
            if field in note:
                val = _norm_reading_key(str(note[field] or ""))
                if val:
                    return val
        except Exception:
            continue
    return _norm_reading_key(_strip_html(strip_furigana_brackets(key_src or "")))


_CLOZE_RE = re.compile(r"\{\{c\d+::(.*?)(?:::(.*?))?\}\}", re.DOTALL)
_CLOZE_SPACING_RE = re.compile(r"\s+(?=[\u3400-\u9FFF\[])", re.UNICODE)
_FORCE_NID_TAG_RE = re.compile(r"^force_nid:(\d+)$", re.IGNORECASE)
_FORCE_NID_VAL_RE = re.compile(r"(\d+)")


def example_target_tag(target_cid: int) -> str:
    return f"{DEFAULT_EXAMPLE_TAG_PREFIX}{int(target_cid)}"


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


_FORM_VERB_RE = re.compile(r"data-conjugate-(?!adj-)([A-Za-z][A-Za-z0-9_-]*)", re.IGNORECASE)
_FORM_ADJ_RE = re.compile(r"data-conjugate-adj-([A-Za-z][A-Za-z0-9_-]*)", re.IGNORECASE)
_FORM_LEMMA_RE = re.compile(r"\bdata-lemma\b", re.IGNORECASE)
_DATA_READING_RE = re.compile(r"<[^>]*data-reading[^>]*>(.*?)</[^>]+>", re.IGNORECASE | re.DOTALL)
_DATA_TYPE_RE = re.compile(r'data-type\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE)

_MODEL_FORM_MARKER_CACHE: dict[int, dict[int, str | None]] = {}
_MODEL_LEMMA_MARKER_CACHE: dict[int, dict[int, bool]] = {}
_CARD_RUNTIME_CACHE: dict[int, tuple[str, str] | None] = {}
_FUGASHI_TAGGER = None
_FUGASHI_READY = False
_LEMMA_BACKEND_STATUS_LOGGED = False


def _norm_form_key(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def _to_hira(s: str) -> str:
    return re.sub(
        r"[\u30a1-\u30f6]",
        lambda m: chr(ord(m.group(0)) - 0x60),
        s or "",
    )


def _to_kata(s: str) -> str:
    return re.sub(
        r"[\u3041-\u3096]",
        lambda m: chr(ord(m.group(0)) + 0x60),
        s or "",
    )


def _back_to_src(src: str, hira: str) -> str:
    if not re.search(r"[\u30a1-\u30f6]", src or ""):
        return hira
    return _to_kata(hira)


def _parse_force_nid(note) -> int | None:
    for fname in ("force_nid", "ForceNid", "forceNid", "Force NID"):
        try:
            if fname not in note:
                continue
            raw = str(note[fname] or "").strip()
            if not raw:
                continue
            m = _FORCE_NID_VAL_RE.search(raw)
            if m:
                return int(m.group(1))
        except Exception:
            continue
    try:
        for tag in note.tags or []:
            m = _FORCE_NID_TAG_RE.match(str(tag or "").strip())
            if m:
                return int(m.group(1))
    except Exception:
        pass
    return None


def _normalize_cloze_spacing(s: str) -> str:
    return _CLOZE_SPACING_RE.sub("", s or "")


def _extract_first_cloze_target_literal(note) -> str:
    try:
        for fname in note.keys():
            raw = str(note[fname] or "")
            if not raw:
                continue
            m = _CLOZE_RE.search(raw)
            if not m:
                continue
            return _norm_literal_text(_normalize_cloze_spacing(m.group(1) or ""))
    except Exception:
        pass
    return ""


def _extract_first_cloze_target(note) -> str:
    return norm_text(_extract_first_cloze_target_literal(note))


def _mapping_level(error_msg: str) -> str:
    msg = str(error_msg or "")
    if msg.startswith("missing_cloze_target"):
        return "info"
    if msg.startswith("no_vocab_match:"):
        return "info"
    return "warn"


def _mapping_reason_key(error_msg: str) -> str:
    msg = str(error_msg or "").strip()
    if not msg:
        return "unknown"
    head = msg.split(":", 1)[0].strip()
    return head or "unknown"


def _mapping_reason_preview(errors: list[tuple[int, str]], *, limit: int = 5) -> str:
    if not errors:
        return ""
    counts = Counter(_mapping_reason_key(msg) for _nid, msg in errors)
    top = counts.most_common(max(1, int(limit)))
    return ", ".join(f"{reason}={count}" for reason, count in top)


def _mapping_examples_preview(errors: list[tuple[int, str]], *, limit: int = 8) -> str:
    if not errors:
        return ""
    clipped = errors[: max(1, int(limit))]
    out = ", ".join(f"{nid}:{_mapping_reason_key(msg)}" for nid, msg in clipped)
    if len(errors) > len(clipped):
        out += ", ..."
    return out


def _fugashi_tagger():
    global _FUGASHI_TAGGER, _FUGASHI_READY, _LEMMA_BACKEND_STATUS_LOGGED
    if _FUGASHI_READY:
        return _FUGASHI_TAGGER
    _FUGASHI_READY = True
    fugashi_ok = False
    fugashi_ver = ""
    fugashi_err = ""
    unidic_ok = False
    unidic_dicdir = ""
    unidic_err = ""
    try:
        import fugashi  # type: ignore

        _FUGASHI_TAGGER = fugashi.Tagger()
        fugashi_ok = _FUGASHI_TAGGER is not None
        fugashi_ver = str(getattr(fugashi, "__version__", "") or "")
    except Exception:
        _FUGASHI_TAGGER = None
        fugashi_err = traceback.format_exc(limit=1).strip()
    try:
        import unidic_lite  # type: ignore

        unidic_dicdir = str(getattr(unidic_lite, "DICDIR", "") or "")
        unidic_ok = bool(unidic_dicdir) and os.path.isdir(unidic_dicdir)
        if not unidic_ok and not unidic_dicdir:
            unidic_ok = True
    except Exception:
        unidic_err = traceback.format_exc(limit=1).strip()

    if not _LEMMA_BACKEND_STATUS_LOGGED:
        _LEMMA_BACKEND_STATUS_LOGGED = True
        if fugashi_ok and unidic_ok:
            log_info(
                "lemma_backend ready",
                "fugashi=ok",
                f"version={fugashi_ver or 'unknown'}",
                "unidic=ok",
                f"dicdir={unidic_dicdir or 'n/a'}",
            )
        else:
            log_warn(
                "lemma_backend degraded",
                f"fugashi={'ok' if fugashi_ok else 'failed'}",
                (f"fugashi_err={fugashi_err}" if fugashi_err else ""),
                f"unidic={'ok' if unidic_ok else 'failed'}",
                f"dicdir={unidic_dicdir or 'n/a'}",
                (f"unidic_err={unidic_err}" if unidic_err else ""),
            )
    return _FUGASHI_TAGGER


def _feature_pos_blob(feat: Any) -> str:
    if feat is None:
        return ""
    vals = [
        getattr(feat, "pos1", None),
        getattr(feat, "pos2", None),
        getattr(feat, "pos3", None),
        getattr(feat, "pos4", None),
        getattr(feat, "pos", None),
        getattr(feat, "part_of_speech", None),
    ]
    return " ".join(str(v or "") for v in vals if str(v or "").strip()).lower()


def _feature_ctype_blob(feat: Any) -> str:
    if feat is None:
        return ""
    return str(getattr(feat, "cType", None) or getattr(feat, "ctype", None) or "").lower()


def _token_is_verb_or_adj(tok: Any) -> bool:
    feat = getattr(tok, "feature", None)
    pos_blob = _feature_pos_blob(feat)
    if any(mark in pos_blob for mark in ("\u52d5\u8a5e", "\u5f62\u5bb9\u8a5e", "\u5f62\u72b6\u8a5e", "verb", "adjective")):
        return True
    ctype_blob = _feature_ctype_blob(feat)
    return any(
        mark in ctype_blob
        for mark in (
            "\u4e94\u6bb5",
            "\u4e0a\u4e00\u6bb5",
            "\u4e0b\u4e00\u6bb5",
            "\u30b5\u884c\u5909\u683c",
            "\u30ab\u884c\u5909\u683c",
            "godan",
            "ichidan",
            "suru",
            "kuru",
            "adj",
        )
    )


def _token_lemma_norm(tok: Any) -> str:
    feat = getattr(tok, "feature", None)
    lemma = (
        getattr(feat, "lemma", None)
        or getattr(feat, "dictionary_form", None)
        or getattr(feat, "base_form", None)
        or str(getattr(tok, "surface", "") or "")
    )
    lemma = str(lemma or "").strip()
    if not lemma or lemma == "*":
        lemma = str(getattr(tok, "surface", "") or "").strip()
    return norm_text(lemma)


def _token_reading_norm(tok: Any) -> str:
    feat = getattr(tok, "feature", None)
    reading = (
        getattr(feat, "kana", None)
        or getattr(feat, "pron", None)
        or getattr(feat, "reading", None)
        or str(getattr(tok, "surface", "") or "")
    )
    reading = str(reading or "").strip()
    if not reading or reading == "*":
        reading = str(getattr(tok, "surface", "") or "").strip()
    return _norm_reading_key(reading)


def _lemma_from_surface(surface: str) -> tuple[str, str]:
    s = norm_text(surface or "")
    if not s:
        return "", "empty_surface"
    tagger = _fugashi_tagger()
    if tagger is None:
        return s, "lemma_backend_unavailable"
    try:
        tokens = [t for t in tagger(s) if str(getattr(t, "surface", "") or "").strip()]
    except Exception:
        return s, "lemma_backend_failed"
    tok = None
    if len(tokens) == 1:
        tok = tokens[0]
    elif 2 <= len(tokens) <= 4 and _token_is_verb_or_adj(tokens[0]):
        tok = tokens[0]
    else:
        return s, "ambiguous_tokenization"
    lemma_norm = _token_lemma_norm(tok)
    if not lemma_norm:
        return s, "ambiguous_tokenization"
    # Guard single-kanji examples from semantic lemma remaps (e.g., 歳 -> 年).
    if (
        len(s) == 1
        and len(lemma_norm) == 1
        and s != lemma_norm
        and "\u3400" <= s <= "\u9fff"
        and "\u3400" <= lemma_norm <= "\u9fff"
    ):
        return s, "single_kanji_surface_guard"
    return lemma_norm, "ok"


def _reading_from_surface(surface: str) -> str:
    s = norm_text(surface or "")
    if not s:
        return ""
    tagger = _fugashi_tagger()
    if tagger is None:
        return _norm_reading_key(s)
    try:
        tokens = [t for t in tagger(s) if str(getattr(t, "surface", "") or "").strip()]
    except Exception:
        return _norm_reading_key(s)
    tok = None
    if len(tokens) == 1:
        tok = tokens[0]
    elif 2 <= len(tokens) <= 4 and _token_is_verb_or_adj(tokens[0]):
        tok = tokens[0]
    else:
        return ""
    return _token_reading_norm(tok)


_SURU_SUFFIXES = (
    "しませんでした",
    "しています",
    "していました",
    "しました",
    "しません",
    "します",
    "しなかった",
    "しない",
    "して",
    "した",
    "しよう",
    "しろ",
)


def _derive_suru_lookup_key(surface: str) -> str:
    s = norm_text(surface or "")
    if not s:
        return ""
    if s.endswith("する"):
        return s
    for suf in _SURU_SUFFIXES:
        if s.endswith(suf) and len(s) > len(suf):
            stem = s[: -len(suf)]
            if stem:
                return f"{stem}する"
    return ""


def _template_ord_form_markers(mid: int) -> dict[int, str | None]:
    cached = _MODEL_FORM_MARKER_CACHE.get(mid)
    if cached is not None:
        return cached
    out: dict[int, str | None] = {}
    if mw is None or not getattr(mw, "col", None):
        _MODEL_FORM_MARKER_CACHE[mid] = out
        return out
    try:
        model = mw.col.models.get(int(mid))
    except Exception:
        model = None
    if not model or not isinstance(model, dict):
        _MODEL_FORM_MARKER_CACHE[mid] = out
        return out
    tmpls = model.get("tmpls", []) or []
    for idx, t in enumerate(tmpls):
        if not isinstance(t, dict):
            out[idx] = None
            continue
        blob = f"{str(t.get('qfmt') or '')}\n{str(t.get('afmt') or '')}"
        v_forms = {_norm_form_key(x) for x in _FORM_VERB_RE.findall(blob)}
        a_forms = {_norm_form_key(x) for x in _FORM_ADJ_RE.findall(blob)}
        if len(v_forms) == 1 and not a_forms:
            out[idx] = f"verb:{next(iter(v_forms))}"
        elif len(a_forms) == 1 and not v_forms:
            out[idx] = f"adj:{next(iter(a_forms))}"
        else:
            out[idx] = None
    _MODEL_FORM_MARKER_CACHE[mid] = out
    return out


def _template_ord_lemma_markers(mid: int) -> dict[int, bool]:
    cached = _MODEL_LEMMA_MARKER_CACHE.get(mid)
    if cached is not None:
        return cached
    out: dict[int, bool] = {}
    if mw is None or not getattr(mw, "col", None):
        _MODEL_LEMMA_MARKER_CACHE[mid] = out
        return out
    try:
        model = mw.col.models.get(int(mid))
    except Exception:
        model = None
    if not model or not isinstance(model, dict):
        _MODEL_LEMMA_MARKER_CACHE[mid] = out
        return out
    tmpls = model.get("tmpls", []) or []
    for idx, t in enumerate(tmpls):
        if not isinstance(t, dict):
            out[idx] = False
            continue
        blob = f"{str(t.get('qfmt') or '')}\n{str(t.get('afmt') or '')}"
        out[idx] = bool(_FORM_LEMMA_RE.search(blob))
    _MODEL_LEMMA_MARKER_CACHE[mid] = out
    return out


def _card_runtime_data(card) -> tuple[str, str] | None:
    cid = int(getattr(card, "id", 0) or 0)
    if cid and cid in _CARD_RUNTIME_CACHE:
        return _CARD_RUNTIME_CACHE[cid]
    try:
        qhtml = str(card.question() or "")
    except Exception:
        if cid:
            _CARD_RUNTIME_CACHE[cid] = None
        return None
    m_read = _DATA_READING_RE.search(qhtml)
    m_type = _DATA_TYPE_RE.search(qhtml)
    if not m_read or not m_type:
        if cid:
            _CARD_RUNTIME_CACHE[cid] = None
        return None
    reading = norm_text(_strip_html(m_read.group(1) or ""))
    ctype = str(m_type.group(1) or "").strip().lower()
    if not reading or not ctype or "{{" in reading or "{{" in ctype:
        if cid:
            _CARD_RUNTIME_CACHE[cid] = None
        return None
    val = (reading, ctype)
    if cid:
        _CARD_RUNTIME_CACHE[cid] = val
    return val


def _conjugate_verb_forms(reading: str, verb_type: str) -> dict[str, str]:
    v0 = str(reading or "").strip()
    if not v0:
        return {}
    t = str(verb_type or "").strip().lower()
    v = _to_hira(v0)
    stem = v[:-1]
    last = v[-1:] if v else ""

    g_a = {"う": "わ", "く": "か", "ぐ": "が", "す": "さ", "つ": "た", "ぬ": "な", "ぶ": "ば", "む": "ま", "る": "ら"}
    g_i = {"う": "い", "く": "き", "ぐ": "ぎ", "す": "し", "つ": "ち", "ぬ": "に", "ぶ": "び", "む": "み", "る": "り"}
    g_e = {"う": "え", "く": "け", "ぐ": "げ", "す": "せ", "つ": "て", "ぬ": "ね", "ぶ": "べ", "む": "め", "る": "れ"}
    g_o = {"う": "お", "く": "こ", "ぐ": "ご", "す": "そ", "つ": "と", "ぬ": "の", "ぶ": "ぼ", "む": "も", "る": "ろ"}
    g_te = {"う": "って", "つ": "って", "る": "って", "む": "んで", "ぶ": "んで", "ぬ": "んで", "く": "いて", "ぐ": "いで", "す": "して"}
    g_ta = {"う": "った", "つ": "った", "る": "った", "む": "んだ", "ぶ": "んだ", "ぬ": "んだ", "く": "いた", "ぐ": "いだ", "す": "した"}

    f: dict[str, str] = {}
    if t == "ichidan":
        b = re.sub("る$", "", v)
        f = {
            "nonpast": v,
            "nonpastnegative": b + "ない",
            "polite": b + "ます",
            "politenegative": b + "ません",
            "past": b + "た",
            "pastnegative": b + "なかった",
            "pastpolite": b + "ました",
            "pastpolitenegative": b + "ませんでした",
            "te": b + "て",
            "potential": b + "られる",
            "potentialnegative": b + "られない",
            "passive": b + "られる",
            "passivenegative": b + "られない",
            "causative": b + "させる",
            "causativenegative": b + "させない",
            "causativepassive": b + "させられる",
            "causativepassivenegative": b + "させられない",
            "imperative": b + "ろ",
            "imperativenegative": b + "るな",
            "volitional": b + "よう",
            "volitionalnegative": b + "まい",
            "politevolitional": b + "ましょう",
            "conditionalba": b + "れば",
            "conditionalbanegative": b + "なければ",
            "conditionalta": b + "たら",
            "conditionaltanegative": b + "なかったら",
            "progressive": b + "ている",
            "progressivenegative": b + "ていない",
            "desire": b + "たい",
            "desirenegative": b + "たくない",
        }
    elif t == "godan":
        if v == "ある":
            f = {
                "nonpast": "ある", "nonpastnegative": "ない", "polite": "あります", "politenegative": "ありません",
                "past": "あった", "pastnegative": "なかった", "pastpolite": "ありました", "pastpolitenegative": "ありませんでした",
                "te": "あって", "potential": "ありえる", "potentialnegative": "ありえない", "passive": "あられる",
                "passivenegative": "あられない", "causative": "あらせる", "causativenegative": "あらせない",
                "causativepassive": "あらせられる", "causativepassivenegative": "あらせられない", "imperative": "あれ",
                "imperativenegative": "あるな", "volitional": "あろう", "volitionalnegative": "あるまい", "politevolitional": "ありましょう",
                "conditionalba": "あれば", "conditionalbanegative": "なければ", "conditionalta": "あったら",
                "conditionaltanegative": "なかったら", "progressive": "あっている", "progressivenegative": "あっていない",
                "desire": "ありたい", "desirenegative": "ありたくない",
            }
        elif v in ("いく", "ゆく"):
            f = {
                "nonpast": v, "nonpastnegative": "いかない", "polite": "いきます", "politenegative": "いきません",
                "past": "いった", "pastnegative": "いかなかった", "pastpolite": "いきました", "pastpolitenegative": "いきませんでした",
                "te": "いって", "potential": "いける", "potentialnegative": "いけない", "passive": "いかれる",
                "passivenegative": "いかれない", "causative": "いかせる", "causativenegative": "いかせない",
                "causativepassive": "いかせられる", "causativepassivenegative": "いかせられない", "imperative": "いけ",
                "imperativenegative": "いくな", "volitional": "いこう", "volitionalnegative": "いくまい", "politevolitional": "いきましょう",
                "conditionalba": "いけば", "conditionalbanegative": "いかなければ", "conditionalta": "いったら",
                "conditionaltanegative": "いかなかったら", "progressive": "いっている", "progressivenegative": "いっていない",
                "desire": "いきたい", "desirenegative": "いきたくない",
            }
        else:
            if last not in g_a:
                return {}
            f = {
                "nonpast": v, "nonpastnegative": stem + g_a[last] + "ない", "polite": stem + g_i[last] + "ます",
                "politenegative": stem + g_i[last] + "ません", "past": stem + g_ta[last], "pastnegative": stem + g_a[last] + "なかった",
                "pastpolite": stem + g_i[last] + "ました", "pastpolitenegative": stem + g_i[last] + "ませんでした", "te": stem + g_te[last],
                "potential": stem + g_e[last] + "る", "potentialnegative": stem + g_e[last] + "ない", "passive": stem + g_a[last] + "れる",
                "passivenegative": stem + g_a[last] + "れない", "causative": stem + g_a[last] + "せる", "causativenegative": stem + g_a[last] + "せない",
                "causativepassive": stem + g_a[last] + "せられる", "causativepassivenegative": stem + g_a[last] + "せられない",
                "imperative": stem + g_e[last], "imperativenegative": stem + g_a[last] + "な", "volitional": stem + g_o[last] + "う",
                "volitionalnegative": stem + g_o[last] + "まい", "politevolitional": stem + g_i[last] + "ましょう", "conditionalba": stem + g_e[last] + "ば",
                "conditionalbanegative": stem + g_a[last] + "なければ", "conditionalta": stem + g_ta[last] + "ら", "conditionaltanegative": stem + g_a[last] + "なかったら",
                "progressive": stem + g_te[last] + "いる", "progressivenegative": stem + g_te[last] + "いない", "desire": stem + g_i[last] + "たい",
                "desirenegative": stem + g_i[last] + "たくない",
            }
    elif t == "suru":
        b = re.sub("する$", "", v)
        f = {
            "nonpast": b + "する", "nonpastnegative": b + "しない", "polite": b + "します", "politenegative": b + "しません",
            "past": b + "した", "pastnegative": b + "しなかった", "pastpolite": b + "しました", "pastpolitenegative": b + "しませんでした",
            "te": b + "して", "potential": b + "できる", "potentialnegative": b + "できない", "passive": b + "される",
            "passivenegative": b + "されない", "causative": b + "させる", "causativenegative": b + "させない",
            "causativepassive": b + "させられる", "causativepassivenegative": b + "させられない", "imperative": b + "しろ",
            "imperativenegative": b + "するな", "volitional": b + "しよう", "volitionalnegative": b + "するまい", "politevolitional": b + "しましょう",
            "conditionalba": b + "すれば", "conditionalbanegative": b + "しなければ", "conditionalta": b + "したら", "conditionaltanegative": b + "しなかったら",
            "progressive": b + "している", "progressivenegative": b + "していない", "desire": b + "したい", "desirenegative": b + "したくない",
        }
    elif t == "kuru":
        f = {
            "nonpast": "くる", "nonpastnegative": "こない", "polite": "きます", "politenegative": "きません", "past": "きた",
            "pastnegative": "こなかった", "pastpolite": "きました", "pastpolitenegative": "きませんでした", "te": "きて",
            "potential": "こられる", "potentialnegative": "こられない", "passive": "こられる", "passivenegative": "こられない",
            "causative": "こさせる", "causativenegative": "こさせない", "causativepassive": "こさせられる", "causativepassivenegative": "こさせられない",
            "imperative": "こい", "imperativenegative": "くるな", "volitional": "こよう", "volitionalnegative": "くるまい",
            "politevolitional": "きましょう", "conditionalba": "くれば", "conditionalbanegative": "こなければ", "conditionalta": "きたら",
            "conditionaltanegative": "こなかったら", "progressive": "きている", "progressivenegative": "きていない", "desire": "きたい", "desirenegative": "きたくない",
        }
    return {k: _back_to_src(v0, val) for k, val in f.items()}


def _conjugate_adj_forms(reading: str, adj_type: str) -> dict[str, str]:
    a0 = str(reading or "").strip()
    if not a0:
        return {}
    t = str(adj_type or "").strip().lower()
    a = _to_hira(a0)
    f: dict[str, str] = {}
    if t == "i":
        base = "よい" if a == "いい" else a
        b = re.sub("い$", "", base)
        f = {
            "nonpast": a, "nonpastnegative": b + "くない", "past": b + "かった", "pastnegative": b + "くなかった",
            "polite": a + "です", "politenegative": b + "くないです", "pastpolite": b + "かったです", "pastpolitenegative": b + "くなかったです",
            "te": b + "くて", "adverb": b + "く", "conditionalba": b + "ければ", "conditionalta": b + "かったら",
        }
    elif t == "na":
        b = re.sub("な$", "", a)
        f = {
            "nonpast": b + "な", "nonpastnegative": b + "じゃない", "past": b + "だった", "pastnegative": b + "じゃなかった",
            "polite": b + "です", "politenegative": b + "じゃありません", "pastpolite": b + "でした", "pastpolitenegative": b + "じゃありませんでした",
            "te": b + "で", "adverb": b + "に", "conditionalba": b + "なら", "conditionalta": b + "だったら",
        }
    return {k: _back_to_src(a0, val) for k, val in f.items()}


def _surface_from_marker(marker: str, reading: str, ctype: str) -> str:
    if not marker:
        return ""
    parts = marker.split(":", 1)
    if len(parts) != 2:
        return ""
    category, key = parts[0], _norm_form_key(parts[1])
    if category == "verb":
        forms = _conjugate_verb_forms(reading, ctype)
    elif category == "adj":
        forms = _conjugate_adj_forms(reading, ctype)
    else:
        forms = {}
    return str(forms.get(key, "") or "")


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


def _build_vocab_mapping_indices(col: Collection, *, ui_set=None) -> tuple[
    dict[str, list["VocabIndexEntry"]],
    dict[int, "VocabIndexEntry"],
    dict[str, list["VocabIndexEntry"]],
    dict[str, list["SurfaceCandidate"]],
]:
    _MODEL_FORM_MARKER_CACHE.clear()
    _MODEL_LEMMA_MARKER_CACHE.clear()
    _CARD_RUNTIME_CACHE.clear()

    vocab_nids = note_ids_for_deck(col, config.VOCAB_DECK)
    dbg("example_gate: vocab notes", len(vocab_nids))

    vocab_by_key: dict[str, list[VocabIndexEntry]] = {}
    vocab_by_nid: dict[int, VocabIndexEntry] = {}
    vocab_by_reading: dict[str, list[VocabIndexEntry]] = {}
    surface_index: dict[str, list[SurfaceCandidate]] = {}

    for i, nid in enumerate(vocab_nids):
        try:
            note = col.get_note(nid)
            nt_id = int(note.mid)
            if config.EXAMPLE_KEY_FIELD not in note:
                continue

            key_src = _normalize_cloze_spacing(str(note[config.EXAMPLE_KEY_FIELD] or ""))
            key = norm_text(key_src)
            if not key:
                continue
            key_literal = _norm_literal_text(key_src)
            reading_key = _extract_vocab_reading_key(note, key_src)

            marker_map = _template_ord_form_markers(nt_id)
            lemma_map = _template_ord_lemma_markers(nt_id)
            candidate_cids: list[int] = []
            lemma_cids: list[int] = []
            is_suru_verb = False
            for card in note.cards():
                if lemma_map.get(int(card.ord), False):
                    lemma_cids.append(int(card.id))
                marker = marker_map.get(int(card.ord), None)
                if not marker:
                    continue
                runtime = _card_runtime_data(card)
                if not runtime:
                    continue
                reading, ctype = runtime
                if str(ctype or "").strip().lower() == "suru":
                    is_suru_verb = True
                surface = norm_text(_surface_from_marker(marker, reading, ctype))
                if not surface:
                    continue
                candidate_cids.append(int(card.id))
                cand = SurfaceCandidate(nid=int(nid), cid=int(card.id), key=key, marker=marker)
                surface_index.setdefault(surface, []).append(cand)

            entry = VocabIndexEntry(
                nid=int(nid),
                key=key,
                key_literal=key_literal,
                reading_key=reading_key,
                is_suru_verb=is_suru_verb,
                note_type_id=nt_id,
                candidate_cids=sorted(set(candidate_cids)),
                lemma_cids=sorted(set(lemma_cids)),
            )
            vocab_by_key.setdefault(key, []).append(entry)
            if reading_key:
                vocab_by_reading.setdefault(reading_key, []).append(entry)
            vocab_by_nid[int(nid)] = entry

            if callable(ui_set) and i % 400 == 0:
                ui_set(
                    f"ExampleGate: index vocab... {i}/{len(vocab_nids)} (keys={len(vocab_by_key)})",
                    i,
                    len(vocab_nids),
                )
        except Exception:
            dbg("example_gate: exception indexing vocab nid", nid)
            dbg(traceback.format_exc())
            log_warn("example_gate: exception indexing vocab nid", nid)

    dbg(
        "example_gate: vocab keys",
        len(vocab_by_key),
        "reading keys",
        len(vocab_by_reading),
        "surface keys",
        len(surface_index),
    )
    return vocab_by_key, vocab_by_nid, vocab_by_reading, surface_index


def _split_honorific_prefix(s: str) -> tuple[str, str]:
    txt = norm_text(s or "")
    if len(txt) >= 2 and txt[0] in ("\u5fa1", "\u304a", "\u3054"):
        return txt[0], txt[1:]
    return "", txt


def _is_honorific_equivalent(a: str, b: str) -> bool:
    left = norm_text(a or "")
    right = norm_text(b or "")
    if not left or not right:
        return False
    if left == right:
        return True
    p1, s1 = _split_honorific_prefix(left)
    p2, s2 = _split_honorific_prefix(right)
    if not s1 or not s2 or s1 != s2:
        return False
    if (p1 == "\u5fa1" and p2 in ("\u304a", "\u3054")) or (p2 == "\u5fa1" and p1 in ("\u304a", "\u3054")):
        return True
    return False


def _select_entry_by_suru_fallback(
    *,
    vocab_by_key: dict[str, list["VocabIndexEntry"]],
    cloze_surface: str,
    lemma_status: str,
) -> tuple["VocabIndexEntry | None", str | None]:
    if str(lemma_status or "") != "ambiguous_tokenization":
        return None, None
    suru_key = _derive_suru_lookup_key(cloze_surface)
    if not suru_key:
        return None, None
    candidates = [cand for cand in vocab_by_key.get(suru_key, []) if bool(cand.is_suru_verb)]
    if len(candidates) == 1:
        return candidates[0], "suru_fallback"
    if len(candidates) > 1:
        return None, f"ambiguous_suru:{suru_key}"
    return None, None


def _build_reading_terms(*terms: str) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for term in terms:
        txt = _norm_reading_key(str(term or ""))
        if not txt or txt in seen:
            continue
        seen.add(txt)
        out.append(txt)
    return out


def _select_entry_by_reading_fallback(
    *,
    vocab_by_reading: dict[str, list["VocabIndexEntry"]],
    reading_terms: list[str],
    cloze_surface: str,
    cloze_surface_literal: str,
    lemma: str,
    surface_index: dict[str, list["SurfaceCandidate"]],
    debug_meta: dict[str, Any] | None = None,
) -> tuple["VocabIndexEntry | None", str | None, set[int]]:
    related_nids: set[int] = set()
    terms = _build_reading_terms(*reading_terms)
    if debug_meta is not None:
        phase = str(debug_meta.get("phase", "") or "")
        debug_meta.clear()
        if phase:
            debug_meta["phase"] = phase
        debug_meta["reading_field"] = str(config.EXAMPLE_READING_FIELD or "").strip() or "VocabReading"
        debug_meta["reading_terms"] = list(terms)
        debug_meta["stage"] = "start"
    if not terms:
        if debug_meta is not None:
            debug_meta["stage"] = "no_reading_terms"
        return None, None, related_nids

    by_nid: dict[int, VocabIndexEntry] = {}
    for term in terms:
        for cand in vocab_by_reading.get(term, []):
            by_nid[int(cand.nid)] = cand
    candidates = list(by_nid.values())
    if not candidates:
        if debug_meta is not None:
            debug_meta["stage"] = "no_reading_candidates"
            debug_meta["candidate_nids"] = []
        return None, None, related_nids

    for cand in candidates:
        related_nids.add(int(cand.nid))
    if debug_meta is not None:
        debug_meta["candidate_nids"] = sorted(int(c.nid) for c in candidates)

    scoped = [cand for cand in candidates if cand.key in {cloze_surface, lemma}]
    if debug_meta is not None:
        scoped_nids = sorted(int(c.nid) for c in scoped)
        debug_meta["scoped_nids"] = scoped_nids
        debug_meta["rejected_scope_nids"] = sorted(
            int(c.nid) for c in candidates if int(c.nid) not in set(scoped_nids)
        )
    if not scoped:
        resolvable: list[VocabIndexEntry] = []
        for cand in candidates:
            target_cids, target_err = _resolve_target_cids(
                cand,
                cloze_surface=cloze_surface,
                lemma=lemma,
                cloze_reading=terms[0],
                reading_terms=terms,
                surface_index=surface_index,
            )
            if not target_err and len(target_cids) in (1, 2):
                resolvable.append(cand)
        if debug_meta is not None:
            debug_meta["resolvable_nids"] = sorted(int(c.nid) for c in resolvable)
        if len(resolvable) == 1:
            if debug_meta is not None:
                debug_meta["stage"] = "selected_resolvable_unscoped"
                debug_meta["selected_nid"] = int(resolvable[0].nid)
            return resolvable[0], "reading_fallback:resolvable_unscoped", related_nids
        if debug_meta is not None:
            debug_meta["stage"] = "ambiguous_unscoped"
        return None, f"ambiguous_reading:{terms[0]}", related_nids

    if len(scoped) == 1:
        if debug_meta is not None:
            debug_meta["stage"] = "selected_scoped"
            debug_meta["selected_nid"] = int(scoped[0].nid)
        return scoped[0], "reading_fallback", related_nids

    literal_hits = [
        cand for cand in scoped
        if cand.key_literal and cand.key_literal == cloze_surface_literal
    ]
    if debug_meta is not None:
        debug_meta["literal_hit_nids"] = sorted(int(c.nid) for c in literal_hits)
    if len(literal_hits) == 1:
        if debug_meta is not None:
            debug_meta["stage"] = "selected_literal"
            debug_meta["selected_nid"] = int(literal_hits[0].nid)
        return literal_hits[0], "reading_fallback:literal", related_nids

    resolvable: list[VocabIndexEntry] = []
    for cand in scoped:
        target_cids, target_err = _resolve_target_cids(
            cand,
            cloze_surface=cloze_surface,
            lemma=lemma,
            cloze_reading=terms[0],
            reading_terms=terms,
            surface_index=surface_index,
        )
        if not target_err and len(target_cids) in (1, 2):
            resolvable.append(cand)
    if debug_meta is not None:
        debug_meta["resolvable_nids"] = sorted(int(c.nid) for c in resolvable)
    if len(resolvable) == 1:
        if debug_meta is not None:
            debug_meta["stage"] = "selected_resolvable"
            debug_meta["selected_nid"] = int(resolvable[0].nid)
        return resolvable[0], "reading_fallback:resolvable", related_nids

    if debug_meta is not None:
        debug_meta["stage"] = "ambiguous_scoped"
    return None, f"ambiguous_reading:{terms[0]}", related_nids


def _resolve_target_cids(
    entry: "VocabIndexEntry",
    *,
    cloze_surface: str,
    lemma: str,
    cloze_reading: str = "",
    reading_terms: list[str] | None = None,
    surface_index: dict[str, list["SurfaceCandidate"]],
) -> tuple[list[int], str | None]:
    cloze_eq_lemma = bool(cloze_surface and lemma and _is_honorific_equivalent(cloze_surface, lemma))
    reading_pool = _build_reading_terms(cloze_reading, *(reading_terms or []))
    cloze_eq_reading = bool(entry.reading_key and entry.reading_key in set(reading_pool))
    if (cloze_eq_lemma or cloze_eq_reading) and len(entry.lemma_cids) in (1, 2):
        return list(entry.lemma_cids), None

    surface_hits = [h for h in surface_index.get(cloze_surface, []) if h.nid == entry.nid]
    uniq_cids = sorted({h.cid for h in surface_hits})
    if len(uniq_cids) in (1, 2):
        return uniq_cids, None
    if len(uniq_cids) > 2:
        return [], f"ambiguous_card_for_surface:{cloze_surface}"

    if len(entry.candidate_cids) in (1, 2):
        return list(entry.candidate_cids), None
    return [], f"ambiguous_target_card:{entry.nid}"


def _diagnose_example_mapping_by_nid(col: Collection, nid: int) -> dict[str, Any]:
    out: dict[str, Any] = {
        "ok": False,
        "nid": int(nid),
        "cloze_surface": "",
        "cloze_reading": "",
        "lemma": "",
        "lemma_reading": "",
        "lemma_status": "",
        "reading_terms": [],
        "reading_fallback_debug": {},
        "lookup_term": "",
        "force_nid": None,
        "match_reason": "",
        "target_vocab_nid": None,
        "target_cid": None,
        "target_cids": [],
        "error": "",
        "related_nids": [int(nid)],
    }
    related_nids: set[int] = {int(nid)}

    if not config.VOCAB_DECK or not config.EXAMPLE_DECK:
        out["error"] = "missing_deck_config"
        return out
    if not config.EXAMPLE_KEY_FIELD:
        out["error"] = "missing_key_field_config"
        return out

    try:
        note = col.get_note(int(nid))
    except Exception:
        out["error"] = "note_not_found"
        return out

    cloze_surface_literal = _extract_first_cloze_target_literal(note)
    cloze_surface = norm_text(cloze_surface_literal)
    out["cloze_surface"] = cloze_surface
    if not cloze_surface:
        out["error"] = "missing_cloze_target"
        return out

    force_nid = _parse_force_nid(note)
    if force_nid is not None:
        related_nids.add(int(force_nid))
    out["force_nid"] = force_nid

    lemma, lemma_status = _lemma_from_surface(cloze_surface)
    cloze_reading = _reading_from_surface(cloze_surface)
    lemma_reading = _reading_from_surface(lemma)
    reading_terms = _build_reading_terms(cloze_reading, lemma_reading)
    out["lemma"] = lemma
    out["cloze_reading"] = cloze_reading
    out["lemma_reading"] = lemma_reading
    out["lemma_status"] = lemma_status
    out["reading_terms"] = list(reading_terms)
    out["lookup_term"] = lemma

    vocab_by_key, vocab_by_nid, vocab_by_reading, surface_index = _build_vocab_mapping_indices(col)

    entry: VocabIndexEntry | None = None
    reason = ""

    if force_nid is not None:
        entry = vocab_by_nid.get(int(force_nid))
        if entry is None:
            out["error"] = f"force_nid_not_found:{force_nid}"
            out["related_nids"] = sorted(related_nids)
            return out
        reason = f"forced:{force_nid}"
    else:
        by_lemma = vocab_by_key.get(lemma, [])
        if len(by_lemma) == 1:
            entry = by_lemma[0]
            reason = f"lemma:{lemma_status}"
        elif len(by_lemma) > 1:
            literal_hits = [cand for cand in by_lemma if cand.key_literal and cand.key_literal == cloze_surface_literal]
            if len(literal_hits) == 1:
                entry = literal_hits[0]
                reason = f"lemma:{lemma_status}:literal"
            else:
                for cand in by_lemma:
                    related_nids.add(int(cand.nid))
                out["error"] = f"ambiguous_lemma:{lemma}"
                out["related_nids"] = sorted(related_nids)
                return out
        else:
            suru_entry, suru_reason = _select_entry_by_suru_fallback(
                vocab_by_key=vocab_by_key,
                cloze_surface=cloze_surface,
                lemma_status=lemma_status,
            )
            if suru_entry is not None:
                entry = suru_entry
                reason = str(suru_reason or "suru_fallback")
                out["lookup_term"] = _derive_suru_lookup_key(cloze_surface) or cloze_surface
            elif suru_reason:
                out["error"] = suru_reason
                out["related_nids"] = sorted(related_nids)
                return out

            if _is_honorific_equivalent(lemma, cloze_surface):
                by_cloze = vocab_by_key.get(cloze_surface, [])
                if len(by_cloze) == 1:
                    entry = by_cloze[0]
                    reason = f"lemma:{lemma_status}:honorific_equiv"
                    out["lookup_term"] = cloze_surface
                elif len(by_cloze) > 1:
                    literal_hits = [
                        cand for cand in by_cloze
                        if cand.key_literal and cand.key_literal == cloze_surface_literal
                    ]
                    if len(literal_hits) == 1:
                        entry = literal_hits[0]
                        reason = f"lemma:{lemma_status}:honorific_equiv:literal"
                        out["lookup_term"] = cloze_surface
                    else:
                        for cand in by_cloze:
                            related_nids.add(int(cand.nid))
                        out["error"] = f"ambiguous_lemma:{cloze_surface}"
                        out["related_nids"] = sorted(related_nids)
                        return out

            if entry is None:
                surface_hits = surface_index.get(cloze_surface, [])
                uniq_nids = sorted({h.nid for h in surface_hits})
                related_nids.update(int(x) for x in uniq_nids)
                if len(uniq_nids) == 1:
                    entry = vocab_by_nid.get(uniq_nids[0])
                    if entry:
                        reason = "surface_match"
                if entry is None:
                    reading_debug: dict[str, Any] = {"phase": "lookup"}
                    entry_by_reading, reading_reason, reading_related = _select_entry_by_reading_fallback(
                        vocab_by_reading=vocab_by_reading,
                        reading_terms=reading_terms,
                        cloze_surface=cloze_surface,
                        cloze_surface_literal=cloze_surface_literal,
                        lemma=lemma,
                        surface_index=surface_index,
                        debug_meta=reading_debug,
                    )
                    out["reading_fallback_debug"] = reading_debug
                    related_nids.update(int(x) for x in reading_related)
                    if entry_by_reading is not None:
                        entry = entry_by_reading
                        reason = reading_reason or "reading_fallback"
                        out["lookup_term"] = cloze_surface
                    elif reading_reason:
                        out["error"] = reading_reason
                        out["related_nids"] = sorted(related_nids)
                        return out
                    else:
                        out["error"] = f"no_vocab_match:{cloze_surface}"
                        out["related_nids"] = sorted(related_nids)
                        return out

    target_cids, target_err = _resolve_target_cids(
        entry,
        cloze_surface=cloze_surface,
        lemma=lemma,
        cloze_reading=cloze_reading,
        reading_terms=reading_terms,
        surface_index=surface_index,
    )
    if target_err and force_nid is None:
        reading_debug_retry: dict[str, Any] = {"phase": "retarget"}
        entry_by_reading, reading_reason, reading_related = _select_entry_by_reading_fallback(
            vocab_by_reading=vocab_by_reading,
            reading_terms=reading_terms,
            cloze_surface=cloze_surface,
            cloze_surface_literal=cloze_surface_literal,
            lemma=lemma,
            surface_index=surface_index,
            debug_meta=reading_debug_retry,
        )
        out["reading_fallback_debug"] = reading_debug_retry
        related_nids.update(int(x) for x in reading_related)
        if entry_by_reading is not None and int(entry_by_reading.nid) != int(entry.nid):
            fallback_cids, fallback_err = _resolve_target_cids(
                entry_by_reading,
                cloze_surface=cloze_surface,
                lemma=lemma,
                cloze_reading=cloze_reading,
                reading_terms=reading_terms,
                surface_index=surface_index,
            )
            if not fallback_err:
                entry = entry_by_reading
                target_cids = fallback_cids
                target_err = None
                reason = reading_reason or "reading_fallback"
                out["lookup_term"] = cloze_surface
    if target_err:
        out["error"] = target_err
        related_nids.add(int(entry.nid))
        out["related_nids"] = sorted(related_nids)
        return out

    related_nids.add(int(entry.nid))
    out["match_reason"] = reason
    out["target_vocab_nid"] = int(entry.nid)
    out["target_cids"] = [int(x) for x in target_cids]
    out["target_cid"] = int(target_cids[0]) if target_cids else None
    out["ok"] = True
    out["related_nids"] = sorted(related_nids)
    return out


def _open_browser_for_nids(nids: Iterable[int]) -> bool:
    if mw is None:
        return False
    uniq = sorted({int(x) for x in nids if int(x) > 0})
    if not uniq:
        return False
    query = " or ".join(f"nid:{nid}" for nid in uniq)
    try:
        browser = aqt.dialogs.open("Browser", mw)
        browser.search_for(query)
        return True
    except Exception:
        log_warn("example_gate browser filter failed", f"query={query}")
        return False


@dataclass
class VocabIndexEntry:
    nid: int
    key: str
    key_literal: str
    reading_key: str
    is_suru_verb: bool
    note_type_id: int
    candidate_cids: list[int]
    lemma_cids: list[int]


@dataclass(frozen=True)
class SurfaceCandidate:
    nid: int
    cid: int
    key: str
    marker: str


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
        log_warn(
            "example_gate: missing deck config",
            "vocab_deck=",
            config.VOCAB_DECK,
            "example_deck=",
            config.EXAMPLE_DECK,
        )
        return
    if not config.EXAMPLE_KEY_FIELD:
        dbg(
            "example_gate: missing key field config",
            "key_field=",
            config.EXAMPLE_KEY_FIELD,
        )
        log_warn(
            "example_gate: missing key field config",
            "key_field=",
            config.EXAMPLE_KEY_FIELD,
        )
        return

    vocab_by_key, vocab_by_nid, vocab_by_reading, surface_index = _build_vocab_mapping_indices(col, ui_set=ui_set)

    ex_nids = note_ids_for_deck(col, config.EXAMPLE_DECK)
    dbg("example_gate: example notes", len(ex_nids))

    to_suspend: list[int] = []
    to_unsuspend: list[int] = []
    mapping_errors: list[tuple[int, str]] = []

    for i, nid in enumerate(ex_nids):
        try:
            note = col.get_note(nid)
            cloze_surface_literal = _extract_first_cloze_target_literal(note)
            cloze_surface = norm_text(cloze_surface_literal)
            if not cloze_surface:
                mapping_errors.append((int(nid), "missing_cloze_target"))
                continue

            force_nid = _parse_force_nid(note)
            lemma, lemma_status = _lemma_from_surface(cloze_surface)
            cloze_reading = _reading_from_surface(cloze_surface)
            lemma_reading = _reading_from_surface(lemma)
            reading_terms = _build_reading_terms(cloze_reading, lemma_reading)

            entry: VocabIndexEntry | None = None
            reason = ""

            if force_nid is not None:
                entry = vocab_by_nid.get(int(force_nid))
                if not entry:
                    mapping_errors.append((int(nid), f"force_nid_not_found:{force_nid}"))
                    continue
                reason = f"forced:{force_nid}"
            else:
                by_lemma = vocab_by_key.get(lemma, [])
                if len(by_lemma) == 1:
                    entry = by_lemma[0]
                    reason = f"lemma:{lemma_status}"
                elif len(by_lemma) > 1:
                    literal_hits = [
                        cand for cand in by_lemma
                        if cand.key_literal and cand.key_literal == cloze_surface_literal
                    ]
                    if len(literal_hits) == 1:
                        entry = literal_hits[0]
                        reason = f"lemma:{lemma_status}:literal"
                    else:
                        mapping_errors.append((int(nid), f"ambiguous_lemma:{lemma}"))
                        continue
                else:
                    suru_entry, suru_reason = _select_entry_by_suru_fallback(
                        vocab_by_key=vocab_by_key,
                        cloze_surface=cloze_surface,
                        lemma_status=lemma_status,
                    )
                    if suru_entry is not None:
                        entry = suru_entry
                        reason = str(suru_reason or "suru_fallback")
                    elif suru_reason:
                        mapping_errors.append((int(nid), suru_reason))
                        continue

                    if _is_honorific_equivalent(lemma, cloze_surface):
                        by_cloze = vocab_by_key.get(cloze_surface, [])
                        if len(by_cloze) == 1:
                            entry = by_cloze[0]
                            reason = f"lemma:{lemma_status}:honorific_equiv"
                        elif len(by_cloze) > 1:
                            literal_hits = [
                                cand for cand in by_cloze
                                if cand.key_literal and cand.key_literal == cloze_surface_literal
                            ]
                            if len(literal_hits) == 1:
                                entry = literal_hits[0]
                                reason = f"lemma:{lemma_status}:honorific_equiv:literal"
                            else:
                                mapping_errors.append((int(nid), f"ambiguous_lemma:{cloze_surface}"))
                                continue

                    if entry is None:
                        surface_hits = surface_index.get(cloze_surface, [])
                        uniq_nids = sorted({h.nid for h in surface_hits})
                        if len(uniq_nids) == 1:
                            entry = vocab_by_nid.get(uniq_nids[0])
                            if entry:
                                reason = "surface_match"
                        if entry is None:
                            entry_by_reading, reading_reason, _reading_related = _select_entry_by_reading_fallback(
                                vocab_by_reading=vocab_by_reading,
                                reading_terms=reading_terms,
                                cloze_surface=cloze_surface,
                                cloze_surface_literal=cloze_surface_literal,
                                lemma=lemma,
                                surface_index=surface_index,
                            )
                            if entry_by_reading is not None:
                                entry = entry_by_reading
                                reason = reading_reason or "reading_fallback"
                            elif reading_reason:
                                mapping_errors.append((int(nid), reading_reason))
                                continue
                            else:
                                mapping_errors.append((int(nid), f"no_vocab_match:{cloze_surface}"))
                                continue

            target_cids, target_err = _resolve_target_cids(
                entry,
                cloze_surface=cloze_surface,
                lemma=lemma,
                cloze_reading=cloze_reading,
                reading_terms=reading_terms,
                surface_index=surface_index,
            )
            if target_err and force_nid is None:
                entry_by_reading, reading_reason, _reading_related = _select_entry_by_reading_fallback(
                    vocab_by_reading=vocab_by_reading,
                    reading_terms=reading_terms,
                    cloze_surface=cloze_surface,
                    cloze_surface_literal=cloze_surface_literal,
                    lemma=lemma,
                    surface_index=surface_index,
                )
                if entry_by_reading is not None and int(entry_by_reading.nid) != int(entry.nid):
                    fallback_cids, fallback_err = _resolve_target_cids(
                        entry_by_reading,
                        cloze_surface=cloze_surface,
                        lemma=lemma,
                        cloze_reading=cloze_reading,
                        reading_terms=reading_terms,
                        surface_index=surface_index,
                    )
                    if not fallback_err:
                        entry = entry_by_reading
                        target_cids = fallback_cids
                        target_err = None
                        reason = reading_reason or "reading_fallback"
            if target_err:
                mapping_errors.append((int(nid), target_err))
                continue

            target_cards = []
            missing_cids: list[int] = []
            for tcid in target_cids:
                try:
                    target_cards.append(col.get_card(int(tcid)))
                except Exception:
                    missing_cids.append(int(tcid))
            if missing_cids:
                mapping_errors.append((int(nid), f"target_card_missing:{','.join(str(x) for x in missing_cids)}"))
                continue

            stab_vals = [card_stability(card) for card in target_cards]
            allow = bool(
                stab_vals
                and all((sv is not None and sv >= float(config.EXAMPLE_THRESHOLD)) for sv in stab_vals)
            )
            ex_tags = [example_target_tag(int(tcid)) for tcid in target_cids]
            is_sticky = bool(config.STICKY_UNLOCK and ex_tags and all(tag in note.tags for tag in ex_tags))
            reason = (
                f"{reason} stab={stab_vals} thr={float(config.EXAMPLE_THRESHOLD)} "
                f"target_cids={target_cids}"
            )

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
                        cloze_surface,
                        "target_cids=",
                        target_cids,
                        "sticky=",
                        is_sticky,
                        reason,
                    )

                if config.STICKY_UNLOCK and allow:
                    note.add_tag(DEFAULT_STICKY_TAG_BASE)
                    added_any = False
                    for ex_tag in ex_tags:
                        if ex_tag not in note.tags:
                            note.add_tag(ex_tag)
                            added_any = True
                    if added_any:
                        note.flush()
                        counters["example_notes_tagged"] += 1
            else:
                to_suspend.extend(cids)
                if config.DEBUG and i < 50:
                    dbg(
                        "example_gate: SUSP",
                        nid,
                        cloze_surface,
                        "target_cids=",
                        target_cids,
                        "sticky=",
                        is_sticky,
                        reason,
                    )

            if i % 250 == 0:
                ui_set(
                    f"ExampleGate: {i}/{len(ex_nids)} | keys={len(vocab_by_key)} | pending unsusp={len(to_unsuspend)} susp={len(to_suspend)} | {cloze_surface}",
                    i,
                    len(ex_nids),
                )
        except Exception:
            dbg("example_gate: exception processing example nid", nid)
            dbg(traceback.format_exc())
            log_warn("example_gate: exception processing example nid", nid)

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

    if mapping_errors:
        counters["example_mapping_errors"] = len(mapping_errors)
        info_errors = [x for x in mapping_errors if _mapping_level(x[1]) == "info"]
        warn_errors = [x for x in mapping_errors if _mapping_level(x[1]) == "warn"]
        counters["example_mapping_info"] = len(info_errors)
        counters["example_mapping_warn"] = len(warn_errors)

        if info_errors:
            info_preview = _mapping_examples_preview(info_errors, limit=8)
            info_reasons = _mapping_reason_preview(info_errors, limit=5)
            log_info(
                "Example Unlocker mapping info",
                f"count={len(info_errors)}",
                f"reasons={info_reasons}",
                f"examples={info_preview}",
            )
        if warn_errors:
            warn_preview = _mapping_examples_preview(warn_errors, limit=8)
            warn_reasons = _mapping_reason_preview(warn_errors, limit=5)
            log_warn(
                "Example Unlocker mapping warnings",
                f"count={len(warn_errors)}",
                f"reasons={warn_reasons}",
                f"examples={warn_preview}",
            )

        preview = _mapping_examples_preview(mapping_errors, limit=8)
        if warn_errors:
            warn_reasons_short = _mapping_reason_preview(warn_errors, limit=3)
            _notify_error(
                f"Example Unlocker mapping warnings on {len(warn_errors)} notes "
                f"(plus {len(info_errors)} info cases). Reasons: {warn_reasons_short}. "
                f"Examples: {preview}. Use force_nid on affected notes.",
                reason="mapping",
            )
        else:
            _notify_info(
                f"Example Unlocker info: {len(info_errors)} notes had no mapping yet. "
                f"Examples: {preview}.",
                reason="mapping",
            )
        if config.DEBUG:
            for enid, emsg in mapping_errors[:50]:
                dbg("example_gate mapping error", enid, emsg)


def _notify_info(msg: str, *, reason: str = "manual") -> None:
    tooltip(msg, period=2500)


def _notify_error(msg: str, *, reason: str = "manual") -> None:
    tooltip(msg, period=2500)


def run_example_gate(*, reason: str = "manual") -> None:
    config.reload_config()
    dbg(
        "reloaded config",
        "debug=",
        config.DEBUG,
        "run_on_sync=",
        config.RUN_ON_SYNC,
        "example_run_on_sync=",
        config.EXAMPLE_GATE_RUN_ON_SYNC,
        "run_on_ui=",
        config.RUN_ON_UI,
    )

    if not mw or not mw.col:
        _notify_error("No collection loaded.", reason=reason)
        return

    if reason == "sync" and not (config.RUN_ON_SYNC and config.EXAMPLE_GATE_RUN_ON_SYNC):
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
        undo_entry = col.add_custom_undo_entry("Example Unlocker")

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
            log_warn("merge_undo_entries skipped: target undo op not found", undo_entry)
            changes = OpChanges()

        if changes is None:
            changes = OpChanges()

        return _Result(changes, counters)

    def on_success(result) -> None:
        c = getattr(result, "counts", {}) or {}
        msg = (
            "Example Unlocker finished.\n"
            f"unsuspended={c.get('example_cards_unsuspended', 0)} "
            f"suspended={c.get('example_cards_suspended', 0)} "
            f"tagged_notes={c.get('example_notes_tagged', 0)} "
            f"mapping_errors={c.get('example_mapping_errors', 0)}"
        )
        log_info(
            "Example Unlocker finished",
            f"unsuspended={c.get('example_cards_unsuspended', 0)}",
            f"suspended={c.get('example_cards_suspended', 0)}",
            f"tagged_notes={c.get('example_notes_tagged', 0)}",
            f"mapping_errors={c.get('example_mapping_errors', 0)}",
            f"mapping_warn={c.get('example_mapping_warn', 0)}",
            f"mapping_info={c.get('example_mapping_info', 0)}",
        )
        if config.DEBUG:
            dbg("RESULT", msg)
        _notify_info(msg, reason=reason)

    def on_failure(err: Exception) -> None:
        tb = "".join(traceback.format_exception(type(err), err, err.__traceback__))
        core_logging.error("Example Unlocker failed", repr(err), source="example_gate")
        if config.DEBUG:
            dbg("FAILURE", repr(err))
            dbg(tb)
        _notify_error("Example Unlocker failed:\n" + tb, reason=reason)

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
    example_tab = QWidget()
    example_layout = QVBoxLayout()
    example_tab.setLayout(example_layout)
    example_form = QFormLayout()
    example_layout.addLayout(example_form)

    deck_names = _get_deck_names()

    example_enabled_cb = QCheckBox()
    example_enabled_cb.setChecked(config.EXAMPLE_GATE_ENABLED)
    example_form.addRow(
        _tip_label("Enabled", "Enable or disable Example Unlocker."),
        example_enabled_cb,
    )

    example_run_on_sync_cb = QCheckBox()
    example_run_on_sync_cb.setChecked(config.EXAMPLE_GATE_RUN_ON_SYNC)
    example_form.addRow(
        _tip_label("Run on sync", "Run Example Unlocker automatically at sync start."),
        example_run_on_sync_cb,
    )

    separator = QFrame()
    separator.setFrameShape(QFrame.Shape.HLine)
    separator.setFrameShadow(QFrame.Shadow.Sunken)

    example_form.addWidget(separator)

    vocab_deck_combo = QComboBox()
    _populate_deck_combo(vocab_deck_combo, deck_names, config.VOCAB_DECK)
    example_form.addRow(
        _tip_label("Vocab deck", "Deck containing source vocabulary notes."),
        vocab_deck_combo,
    )

    example_deck_combo = QComboBox()
    _populate_deck_combo(example_deck_combo, deck_names, config.EXAMPLE_DECK)
    example_form.addRow(
        _tip_label("Example deck", "Deck containing example sentence notes."),
        example_deck_combo,
    )

    key_field_edit = QLineEdit()
    key_field_edit.setText(config.EXAMPLE_KEY_FIELD)
    example_form.addRow(
        _tip_label(
            "Key field",
            "Field on vocab notes used as lemma key for exact vocab/example matching.",
        ),
        key_field_edit,
    )
    reading_field_edit = QLineEdit()
    reading_field_edit.setText(config.EXAMPLE_READING_FIELD)
    example_form.addRow(
        _tip_label(
            "Reading fallback field",
            "Field on vocab notes used for normalized reading fallback matching.",
        ),
        reading_field_edit,
    )

    example_threshold_spin = QDoubleSpinBox()
    example_threshold_spin.setDecimals(2)
    example_threshold_spin.setRange(0, 100000)
    example_threshold_spin.setSuffix(" days")
    example_threshold_spin.setValue(float(config.EXAMPLE_THRESHOLD))
    example_form.addRow(
        _tip_label("Threshold", "Required FSRS stability before dependent cards unlock."),
        example_threshold_spin,
    )

    if bool(config.DEBUG):
        debug_separator = QFrame()
        debug_separator.setFrameShape(QFrame.Shape.HLine)
        debug_separator.setFrameShadow(QFrame.Shadow.Sunken)
        example_form.addWidget(debug_separator)

        debug_lookup_row = QWidget()
        debug_lookup_layout = QHBoxLayout()
        debug_lookup_layout.setContentsMargins(0, 0, 0, 0)
        debug_lookup_row.setLayout(debug_lookup_layout)
        mapping_debug_nid_edit = QLineEdit()
        mapping_debug_nid_edit.setPlaceholderText("Example note NID")
        mapping_debug_search_btn = QPushButton("Search")
        debug_lookup_layout.addWidget(mapping_debug_nid_edit)
        debug_lookup_layout.addWidget(mapping_debug_search_btn)
        example_form.addRow(
            _tip_label(
                "Mapping debug",
                "Inspect one Example-note mapping by NID and show fallback match details.",
            ),
            debug_lookup_row,
        )

        def _show_mapping_debug_popup(result: dict[str, Any]) -> None:
            ok = bool(result.get("ok"))
            nid = int(result.get("nid", 0) or 0)
            cloze_surface = str(result.get("cloze_surface", "") or "")
            cloze_reading = str(result.get("cloze_reading", "") or "")
            lemma = str(result.get("lemma", "") or "")
            lemma_reading = str(result.get("lemma_reading", "") or "")
            lemma_status = str(result.get("lemma_status", "") or "")
            lookup_term = str(result.get("lookup_term", "") or "")
            reason = str(result.get("match_reason", "") or "")
            target_vocab_nid = result.get("target_vocab_nid")
            target_cids = [int(x) for x in (result.get("target_cids") or []) if int(x) > 0]
            err = str(result.get("error", "") or "")
            related_nids = [int(x) for x in (result.get("related_nids") or []) if int(x) > 0]
            reading_terms = [str(x) for x in (result.get("reading_terms") or []) if str(x or "").strip()]
            fallback_debug = result.get("reading_fallback_debug")
            fallback_info = fallback_debug if isinstance(fallback_debug, dict) else {}
            fb_field = str(fallback_info.get("reading_field", "") or "")
            fb_phase = str(fallback_info.get("phase", "") or "")
            fb_stage = str(fallback_info.get("stage", "") or "")
            fb_terms = [str(x) for x in (fallback_info.get("reading_terms") or []) if str(x or "").strip()]
            fb_candidates = [int(x) for x in (fallback_info.get("candidate_nids") or []) if int(x) > 0]
            fb_scoped = [int(x) for x in (fallback_info.get("scoped_nids") or []) if int(x) > 0]
            fb_rejected = [int(x) for x in (fallback_info.get("rejected_scope_nids") or []) if int(x) > 0]
            fb_literals = [int(x) for x in (fallback_info.get("literal_hit_nids") or []) if int(x) > 0]
            fb_resolvable = [int(x) for x in (fallback_info.get("resolvable_nids") or []) if int(x) > 0]
            fb_selected = int(fallback_info.get("selected_nid", 0) or 0)

            msg = QMessageBox(example_tab)
            msg.setWindowTitle("Example Unlocker Mapping Debug")
            msg.setIcon(QMessageBox.Icon.Information if ok else QMessageBox.Icon.Warning)
            msg.setText("Mapping found." if ok else "No unique mapping found.")
            lines = [
                f"Example NID: {nid}",
                f"Cloze surface: {cloze_surface or '-'}",
                f"Cloze reading: {cloze_reading or '-'}",
                f"Lemma (ermittelt): {lemma or '-'}",
                f"Lemma reading: {lemma_reading or '-'}",
                f"Lemma status: {lemma_status or '-'}",
                f"Reading terms: {', '.join(reading_terms) if reading_terms else '-'}",
                f"Abgleichsbegriff: {lookup_term or '-'}",
                f"Match reason: {reason or '-'}",
                f"Target vocab NID: {target_vocab_nid if target_vocab_nid is not None else '-'}",
                f"Target card CIDs: {', '.join(str(x) for x in target_cids) if target_cids else '-'}",
                f"Error: {err or '-'}",
                f"Fallback field: {fb_field or '-'}",
                f"Fallback phase/stage: {fb_phase or '-'} / {fb_stage or '-'}",
                f"Fallback terms: {', '.join(fb_terms) if fb_terms else '-'}",
                f"Fallback candidates: {', '.join(str(x) for x in fb_candidates) if fb_candidates else '-'}",
                f"Fallback scoped: {', '.join(str(x) for x in fb_scoped) if fb_scoped else '-'}",
                f"Fallback rejected by scope: {', '.join(str(x) for x in fb_rejected) if fb_rejected else '-'}",
                f"Fallback literal hits: {', '.join(str(x) for x in fb_literals) if fb_literals else '-'}",
                f"Fallback resolvable: {', '.join(str(x) for x in fb_resolvable) if fb_resolvable else '-'}",
                f"Fallback selected: {fb_selected if fb_selected > 0 else '-'}",
                f"Related notes: {', '.join(str(x) for x in related_nids) if related_nids else '-'}",
            ]
            msg.setInformativeText("\n".join(lines))
            filter_btn = msg.addButton("Filter Notes", QMessageBox.ButtonRole.ActionRole)
            msg.addButton(QMessageBox.StandardButton.Close)
            msg.exec()
            if msg.clickedButton() == filter_btn:
                if _open_browser_for_nids(related_nids):
                    tooltip("Opened Browser filter for related notes.", period=2500)
                else:
                    tooltip("Failed to open Browser filter.", period=2500)

        def _run_mapping_debug_lookup() -> None:
            raw = str(mapping_debug_nid_edit.text() or "").strip()
            if not raw:
                tooltip("Enter an Example note NID first.", period=2500)
                return
            try:
                nid = int(raw)
            except Exception:
                tooltip("NID must be numeric.", period=2500)
                return
            if mw is None or mw.col is None:
                tooltip("No collection loaded.", period=2500)
                return

            config.reload_config()
            t0 = time.time()
            result = _diagnose_example_mapping_by_nid(mw.col, nid)
            elapsed_ms = int((time.time() - t0) * 1000)
            log_info(
                "Example Unlocker mapping lookup",
                f"nid={nid}",
                f"ok={bool(result.get('ok'))}",
                f"lemma={result.get('lemma', '')}",
                f"reason={result.get('match_reason', '')}",
                f"target_cids={result.get('target_cids', [])}",
                f"error={result.get('error', '')}",
                f"elapsed_ms={elapsed_ms}",
            )
            _show_mapping_debug_popup(result)

        mapping_debug_search_btn.clicked.connect(_run_mapping_debug_lookup)
        mapping_debug_nid_edit.returnPressed.connect(_run_mapping_debug_lookup)

    example_layout.addStretch(1)

    ctx.add_tab(example_tab, "Example Unlocker")

    def _save(cfg: dict, errors: list[str]) -> None:
        config._cfg_set(cfg, "example_gate.enabled", bool(example_enabled_cb.isChecked()))
        config._cfg_set(cfg, "example_gate.run_on_sync", bool(example_run_on_sync_cb.isChecked()))
        config._cfg_set(cfg, "example_gate.vocab_deck", _combo_value(vocab_deck_combo))
        config._cfg_set(cfg, "example_gate.example_deck", _combo_value(example_deck_combo))
        config._cfg_set(cfg, "example_gate.key_field", key_field_edit.text().strip())
        config._cfg_set(cfg, "example_gate.reading_field", reading_field_edit.text().strip())
        config._cfg_set(cfg, "example_gate.threshold", float(example_threshold_spin.value()))

    return _save


def _enabled_example() -> bool:
    return bool(config.RUN_ON_UI and config.EXAMPLE_GATE_ENABLED)


def _deck_stats_provider_example_gate() -> dict[str, Any]:
    reload_config()
    enabled = bool(EXAMPLE_GATE_ENABLED)
    tracked: set[int] = set()
    if enabled and mw is not None and getattr(mw, "col", None):
        ex_deck = str(EXAMPLE_DECK or "").strip()
        if ex_deck:
            ex_nids = note_ids_for_deck(mw.col, ex_deck)
            apply_all = bool(EX_APPLY_ALL_CARDS)
            for nid in ex_nids:
                try:
                    note = mw.col.get_note(int(nid))
                except Exception:
                    continue
                cloze_surface = _extract_first_cloze_target(note)
                if not cloze_surface:
                    continue
                cards = note.cards()
                if not cards:
                    continue
                if apply_all:
                    for card in cards:
                        tracked.add(int(card.id))
                else:
                    tracked.add(int(cards[0].id))
    return {
        "label": "Examples unlocked",
        "enabled": enabled,
        "tracked": len(tracked),
        "free": count_unsuspended_cards(tracked),
        "order": 30,
    }


def _init() -> None:
    from aqt import gui_hooks, mw

    register_provider("example_gate", _deck_stats_provider_example_gate, order=30)

    def _on_sync_start() -> None:
        run_example_gate(reason="sync")

    if mw is not None and not getattr(mw, "_ajpc_examplegate_sync_hook_installed", False):
        gui_hooks.sync_will_start.append(_on_sync_start)
        mw._ajpc_examplegate_sync_hook_installed = True


MODULE = ModuleSpec(
    id="example_gate",
    label="Example Unlocker",
    order=35,
    init=_init,
    run_items=[
        {
            "label": "Run Example Unlocker",
            "callback": lambda: run_example_gate(reason="manual"),
            "enabled_fn": _enabled_example,
            "order": 20,
        }
    ],
    build_settings=_build_settings,
)

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
    QFrame,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QLineEdit,
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
    global VOCAB_KEY_FIELD, EXAMPLE_KEY_FIELD, EX_STAGE_SEP, EX_STAGE_DEFAULT, EX_APPLY_ALL_CARDS
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


_CLOZE_RE = re.compile(r"\{\{c\d+::(.*?)(?:::(.*?))?\}\}", re.DOTALL)
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
_DATA_READING_RE = re.compile(r"<[^>]*data-reading[^>]*>(.*?)</[^>]+>", re.IGNORECASE | re.DOTALL)
_DATA_TYPE_RE = re.compile(r'data-type\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE)

_MODEL_FORM_MARKER_CACHE: dict[int, dict[int, str | None]] = {}
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


def _extract_first_cloze_target(note) -> str:
    try:
        for fname in note.keys():
            raw = str(note[fname] or "")
            if not raw:
                continue
            m = _CLOZE_RE.search(raw)
            if not m:
                continue
            return norm_text(_strip_html(m.group(1) or ""))
    except Exception:
        pass
    return ""


def _mapping_level(error_msg: str) -> str:
    msg = str(error_msg or "")
    if msg.startswith("missing_cloze_target"):
        return "info"
    if msg.startswith("no_vocab_match:"):
        return "info"
    return "warn"


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
    if len(tokens) != 1:
        return s, "ambiguous_tokenization"
    tok = tokens[0]
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
    return norm_text(lemma), "ok"


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


@dataclass
class VocabIndexEntry:
    nid: int
    key: str
    note_type_id: int
    candidate_cids: list[int]


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

    vocab_nids = note_ids_for_deck(col, config.VOCAB_DECK)
    dbg("example_gate: vocab notes", len(vocab_nids))

    _MODEL_FORM_MARKER_CACHE.clear()
    _CARD_RUNTIME_CACHE.clear()

    vocab_by_key: dict[str, list[VocabIndexEntry]] = {}
    vocab_by_nid: dict[int, VocabIndexEntry] = {}
    surface_index: dict[str, list[SurfaceCandidate]] = {}
    note_surface_candidates: dict[int, list[SurfaceCandidate]] = {}

    for i, nid in enumerate(vocab_nids):
        try:
            note = col.get_note(nid)
            nt_id = int(note.mid)
            if config.EXAMPLE_KEY_FIELD not in note:
                continue

            key = norm_text(str(note[config.EXAMPLE_KEY_FIELD] or ""))
            if not key:
                continue

            marker_map = _template_ord_form_markers(nt_id)
            candidate_cids: list[int] = []
            note_candidates: list[SurfaceCandidate] = []
            for card in note.cards():
                marker = marker_map.get(int(card.ord), None)
                if not marker:
                    continue
                runtime = _card_runtime_data(card)
                if not runtime:
                    continue
                reading, ctype = runtime
                surface = norm_text(_surface_from_marker(marker, reading, ctype))
                if not surface:
                    continue
                candidate_cids.append(int(card.id))
                cand = SurfaceCandidate(nid=int(nid), cid=int(card.id), key=key, marker=marker)
                note_candidates.append(cand)
                surface_index.setdefault(surface, []).append(cand)

            entry = VocabIndexEntry(
                nid=int(nid),
                key=key,
                note_type_id=nt_id,
                candidate_cids=sorted(set(candidate_cids)),
            )
            vocab_by_key.setdefault(key, []).append(entry)
            vocab_by_nid[int(nid)] = entry
            note_surface_candidates[int(nid)] = note_candidates

            if i % 400 == 0:
                ui_set(
                    f"ExampleGate: index vocab... {i}/{len(vocab_nids)} (keys={len(vocab_by_key)})",
                    i,
                    len(vocab_nids),
                )
        except Exception:
            dbg("example_gate: exception indexing vocab nid", nid)
            dbg(traceback.format_exc())
            log_warn("example_gate: exception indexing vocab nid", nid)

    dbg("example_gate: vocab keys", len(vocab_by_key), "surface keys", len(surface_index))

    ex_nids = note_ids_for_deck(col, config.EXAMPLE_DECK)
    dbg("example_gate: example notes", len(ex_nids))

    to_suspend: list[int] = []
    to_unsuspend: list[int] = []
    mapping_errors: list[tuple[int, str]] = []

    for i, nid in enumerate(ex_nids):
        try:
            note = col.get_note(nid)
            cloze_surface = _extract_first_cloze_target(note)
            if not cloze_surface:
                mapping_errors.append((int(nid), "missing_cloze_target"))
                continue

            force_nid = _parse_force_nid(note)
            lemma, lemma_status = _lemma_from_surface(cloze_surface)

            entry: VocabIndexEntry | None = None
            target_cid: int | None = None
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
                    mapping_errors.append((int(nid), f"ambiguous_lemma:{lemma}"))
                    continue
                else:
                    surface_hits = surface_index.get(cloze_surface, [])
                    uniq_nids = sorted({h.nid for h in surface_hits})
                    if len(uniq_nids) == 1:
                        entry = vocab_by_nid.get(uniq_nids[0])
                        if entry:
                            uniq_cids = sorted({h.cid for h in surface_hits if h.nid == entry.nid})
                            if len(uniq_cids) == 1:
                                target_cid = uniq_cids[0]
                            elif len(uniq_cids) > 1:
                                mapping_errors.append((int(nid), f"ambiguous_card_for_surface:{cloze_surface}"))
                                continue
                            reason = "surface_match"
                    if entry is None:
                        mapping_errors.append((int(nid), f"no_vocab_match:{cloze_surface}"))
                        continue

            if target_cid is None:
                surface_hits = [h for h in surface_index.get(cloze_surface, []) if h.nid == entry.nid]
                uniq_cids = sorted({h.cid for h in surface_hits})
                if len(uniq_cids) == 1:
                    target_cid = uniq_cids[0]
                elif len(entry.candidate_cids) == 1:
                    target_cid = entry.candidate_cids[0]
                else:
                    mapping_errors.append((int(nid), f"ambiguous_target_card:{entry.nid}"))
                    continue

            try:
                target_card = col.get_card(int(target_cid))
            except Exception:
                mapping_errors.append((int(nid), f"target_card_missing:{target_cid}"))
                continue

            stab_val = card_stability(target_card)
            allow = bool(stab_val is not None and stab_val >= float(config.EXAMPLE_THRESHOLD))
            ex_tag = example_target_tag(int(target_cid))
            is_sticky = config.STICKY_UNLOCK and (ex_tag in note.tags)
            reason = f"{reason} stab={stab_val} thr={float(config.EXAMPLE_THRESHOLD)}"

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
                    dbg("example_gate: UNSUSP", nid, cloze_surface, "target_cid=", target_cid, "sticky=", is_sticky, reason)

                if config.STICKY_UNLOCK and allow and ex_tag not in note.tags:
                    note.add_tag(DEFAULT_STICKY_TAG_BASE)
                    note.add_tag(ex_tag)
                    note.flush()
                    counters["example_notes_tagged"] += 1
            else:
                to_suspend.extend(cids)
                if config.DEBUG and i < 50:
                    dbg("example_gate: SUSP", nid, cloze_surface, "target_cid=", target_cid, "sticky=", is_sticky, reason)

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
            info_preview = ", ".join(str(x[0]) for x in info_errors[:8])
            if len(info_errors) > 8:
                info_preview += ", ..."
            log_info(
                "Example Unlocker mapping info",
                f"count={len(info_errors)}",
                f"examples={info_preview}",
            )
        if warn_errors:
            warn_preview = ", ".join(str(x[0]) for x in warn_errors[:8])
            if len(warn_errors) > 8:
                warn_preview += ", ..."
            log_warn(
                "Example Unlocker mapping warnings",
                f"count={len(warn_errors)}",
                f"examples={warn_preview}",
            )

        preview = ", ".join(str(x[0]) for x in mapping_errors[:8])
        if len(mapping_errors) > 8:
            preview += ", ..."
        if warn_errors:
            _notify_error(
                f"Example Unlocker mapping warnings on {len(warn_errors)} notes "
                f"(plus {len(info_errors)} info cases). "
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

    example_threshold_spin = QDoubleSpinBox()
    example_threshold_spin.setDecimals(2)
    example_threshold_spin.setRange(0, 100000)
    example_threshold_spin.setSuffix(" days")
    example_threshold_spin.setValue(float(config.EXAMPLE_THRESHOLD))
    example_form.addRow(
        _tip_label("Threshold", "Required FSRS stability before dependent cards unlock."),
        example_threshold_spin,
    )

    example_layout.addStretch(1)

    ctx.add_tab(example_tab, "Example Unlocker")

    def _save(cfg: dict, errors: list[str]) -> None:
        config._cfg_set(cfg, "example_gate.enabled", bool(example_enabled_cb.isChecked()))
        config._cfg_set(cfg, "example_gate.run_on_sync", bool(example_run_on_sync_cb.isChecked()))
        config._cfg_set(cfg, "example_gate.vocab_deck", _combo_value(vocab_deck_combo))
        config._cfg_set(cfg, "example_gate.example_deck", _combo_value(example_deck_combo))
        config._cfg_set(cfg, "example_gate.key_field", key_field_edit.text().strip())
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

from __future__ import annotations

import json
import os
from typing import Any

ADDON_DIR = os.path.dirname(__file__)
CONFIG_PATH = os.path.join(ADDON_DIR, "config.json")

CFG: dict[str, Any] = {}
DEBUG = False
DEBUG_VERIFY_SUSPENSION = False
RUN_ON_SYNC = True
RUN_ON_UI = True
STICKY_UNLOCK = True
STABILITY_DEFAULT_THRESHOLD = 2.5
STABILITY_AGG = "min"

FAMILY_GATE_ENABLED = True
FAMILY_FIELD = "FamilyID"
FAMILY_SEP = ";"
FAMILY_DEFAULT_PRIO = 0
FAMILY_NOTE_TYPES: dict[str, Any] = {}

EXAMPLE_GATE_ENABLED = True
VOCAB_DECK = ""
EXAMPLE_DECK = ""
VOCAB_KEY_FIELD = "Vocab"
EXAMPLE_KEY_FIELD = "Vocab"
EX_STAGE_SEP = "@"
EX_STAGE_DEFAULT = 0
EX_APPLY_ALL_CARDS = True

KEY_NORM: dict[str, Any] = {}
KEY_STRIP_HTML = True
KEY_TRIM = True
KEY_NFC = True
KEY_FIRST_TOKEN = True
KEY_STRIP_FURIGANA_BR = False

WATCH_NIDS: set[int] = set()

DEFAULT_JLPT_TAG_MAP = {
    "jlpt-n5": "JLPT::N5",
    "jlpt-n4": "JLPT::N4",
    "jlpt-n3": "JLPT::N3",
    "jlpt-n2": "JLPT::N2",
    "jlpt-n1": "JLPT::N1",
    "jlpt-none": "JLPT::None",
    "common": "common",
}
JLPT_TAGGER_DECKS: list[str] = []
JLPT_TAGGER_NOTE_TYPES: list[str] = []
JLPT_TAGGER_FIELDS: dict[str, dict[str, str]] = {}
JLPT_TAGGER_TAG_MAP: dict[str, str] = DEFAULT_JLPT_TAG_MAP.copy()

CARD_SORTER_ENABLED = True
CARD_SORTER_RUN_ON_ADD = True
CARD_SORTER_RUN_ON_SYNC_START = True
CARD_SORTER_RUN_ON_SYNC_FINISH = True
CARD_SORTER_EXCLUDE_DECKS: list[str] = []
CARD_SORTER_EXCLUDE_TAGS: list[str] = []
CARD_SORTER_NOTE_TYPES: dict[str, Any] = {}


def _load_config() -> dict[str, Any]:
    if not os.path.exists(CONFIG_PATH):
        return {}
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
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
    global FAMILY_GATE_ENABLED, FAMILY_FIELD, FAMILY_SEP, FAMILY_DEFAULT_PRIO, FAMILY_NOTE_TYPES
    global EXAMPLE_GATE_ENABLED, VOCAB_DECK, EXAMPLE_DECK, VOCAB_KEY_FIELD, EXAMPLE_KEY_FIELD
    global EX_STAGE_SEP, EX_STAGE_DEFAULT, EX_APPLY_ALL_CARDS
    global KEY_NORM, KEY_STRIP_HTML, KEY_TRIM, KEY_NFC, KEY_FIRST_TOKEN, KEY_STRIP_FURIGANA_BR
    global WATCH_NIDS
    global JLPT_TAGGER_DECKS, JLPT_TAGGER_NOTE_TYPES, JLPT_TAGGER_FIELDS, JLPT_TAGGER_TAG_MAP
    global CARD_SORTER_ENABLED, CARD_SORTER_RUN_ON_ADD, CARD_SORTER_RUN_ON_SYNC_START, CARD_SORTER_RUN_ON_SYNC_FINISH
    global CARD_SORTER_EXCLUDE_DECKS, CARD_SORTER_EXCLUDE_TAGS, CARD_SORTER_NOTE_TYPES

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
    FAMILY_FIELD = str(cfg_get("family_gate.family.field", "FamilyID"))
    FAMILY_SEP = str(cfg_get("family_gate.family.separator", ";"))
    FAMILY_DEFAULT_PRIO = int(cfg_get("family_gate.family.default_prio", 0))
    FAMILY_NOTE_TYPES = cfg_get("family_gate.note_types", {}) or {}

    EXAMPLE_GATE_ENABLED = bool(cfg_get("example_gate.enabled", True))
    VOCAB_DECK = str(cfg_get("example_gate.vocab_deck", "")).strip()
    EXAMPLE_DECK = str(cfg_get("example_gate.example_deck", "")).strip()
    VOCAB_KEY_FIELD = str(cfg_get("example_gate.vocab_key_field", "Vocab"))
    EXAMPLE_KEY_FIELD = str(cfg_get("example_gate.example_key_field", "Vocab"))

    EX_STAGE_SEP = str(cfg_get("example_gate.example_stage_syntax.separator", "@"))
    EX_STAGE_DEFAULT = int(cfg_get("example_gate.example_stage_syntax.default_stage", 0))

    EX_APPLY_ALL_CARDS = bool(cfg_get("example_gate.example_action.apply_to_all_cards_in_note", True))

    KEY_NORM = cfg_get("example_gate.key_normalization", {}) or {}
    KEY_STRIP_HTML = bool(KEY_NORM.get("strip_html", True))
    KEY_TRIM = bool(KEY_NORM.get("trim", True))
    KEY_NFC = bool(KEY_NORM.get("unicode_nfc", True))
    KEY_FIRST_TOKEN = bool(KEY_NORM.get("first_token_only", True))
    KEY_STRIP_FURIGANA_BR = bool(KEY_NORM.get("strip_furigana_brackets", False))

    JLPT_TAGGER_DECKS = list(cfg_get("jlpt_tagger.decks", []) or [])
    JLPT_TAGGER_NOTE_TYPES = list(cfg_get("jlpt_tagger.note_types", []) or [])
    JLPT_TAGGER_FIELDS = cfg_get("jlpt_tagger.note_type_fields", {}) or {}
    raw_map = cfg_get("jlpt_tagger.tag_map", None)
    if isinstance(raw_map, dict) and raw_map:
        JLPT_TAGGER_TAG_MAP = dict(raw_map)
    else:
        JLPT_TAGGER_TAG_MAP = DEFAULT_JLPT_TAG_MAP.copy()

    CARD_SORTER_ENABLED = bool(cfg_get("card_sorter.enabled", True))
    CARD_SORTER_RUN_ON_ADD = bool(cfg_get("card_sorter.run_on_add_note", True))
    CARD_SORTER_RUN_ON_SYNC_START = bool(cfg_get("card_sorter.run_on_sync_start", True))
    CARD_SORTER_RUN_ON_SYNC_FINISH = bool(cfg_get("card_sorter.run_on_sync_finish", True))
    CARD_SORTER_EXCLUDE_DECKS = list(cfg_get("card_sorter.exclude_decks", []) or [])
    CARD_SORTER_EXCLUDE_TAGS = list(cfg_get("card_sorter.exclude_tags", []) or [])
    CARD_SORTER_NOTE_TYPES = cfg_get("card_sorter.note_types", {}) or {}


reload_config()

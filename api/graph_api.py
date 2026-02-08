from __future__ import annotations

import json
import os
from typing import Any

from aqt import mw

ADDON_DIR = os.path.dirname(os.path.dirname(__file__))
CONFIG_PATH = os.path.join(ADDON_DIR, "config.json")

CFG: dict[str, Any] = {}
DEBUG = False

FAMILY_GATE_ENABLED = True
FAMILY_GATE_RUN_ON_SYNC = True
FAMILY_LINK_ENABLED = False
FAMILY_FIELD = "FamilyID"
FAMILY_SEP = ";"
FAMILY_DEFAULT_PRIO = 0
FAMILY_NOTE_TYPES: dict[str, Any] = {}

CARD_STAGES_ENABLED = True
CARD_STAGES_RUN_ON_SYNC = True
CARD_STAGES_NOTE_TYPES: dict[str, Any] = {}

EXAMPLE_GATE_ENABLED = True
EXAMPLE_GATE_RUN_ON_SYNC = True
VOCAB_DECK = ""
EXAMPLE_DECK = ""
VOCAB_KEY_FIELD = "Vocab"
EXAMPLE_KEY_FIELD = "Vocab"
EX_STAGE_SEP = "@"
EX_STAGE_DEFAULT = 0
EXAMPLE_THRESHOLD = 14.0
KEY_STRIP_HTML = True
KEY_TRIM = True
KEY_NFC = True
KEY_FIRST_TOKEN = True
KEY_STRIP_FURIGANA_BR = False

KANJI_GATE_ENABLED = True
KANJI_GATE_RUN_ON_SYNC = True
KANJI_GATE_BEHAVIOR = "kanji_and_components"
KANJI_GATE_STABILITY_AGG = "min"
KANJI_GATE_VOCAB_NOTE_TYPES: dict[str, Any] = {}
KANJI_GATE_KANJI_NOTE_TYPE = ""
KANJI_GATE_KANJI_FIELDS: list[str] = []
KANJI_GATE_KANJI_FIELD = ""
KANJI_GATE_KANJI_ALT_FIELD = ""
KANJI_GATE_COMPONENTS_FIELD = ""
KANJI_GATE_KANJI_RADICAL_FIELD = ""
KANJI_GATE_RADICAL_NOTE_TYPE = ""
KANJI_GATE_RADICAL_FIELD = ""
KANJI_GATE_KANJI_THRESHOLD = 14.0
KANJI_GATE_COMPONENT_THRESHOLD = 14.0

MASS_LINKER_ENABLED = True
MASS_LINKER_RULES: dict[str, Any] = {}

STABILITY_DEFAULT_THRESHOLD = 14.0
STABILITY_AGG = "min"


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
    global FAMILY_GATE_ENABLED, FAMILY_GATE_RUN_ON_SYNC, FAMILY_LINK_ENABLED
    global FAMILY_FIELD, FAMILY_SEP, FAMILY_DEFAULT_PRIO, FAMILY_NOTE_TYPES
    global CARD_STAGES_ENABLED, CARD_STAGES_RUN_ON_SYNC, CARD_STAGES_NOTE_TYPES
    global EXAMPLE_GATE_ENABLED, EXAMPLE_GATE_RUN_ON_SYNC, VOCAB_DECK, EXAMPLE_DECK, VOCAB_KEY_FIELD, EXAMPLE_KEY_FIELD
    global EX_STAGE_SEP, EX_STAGE_DEFAULT, EXAMPLE_THRESHOLD
    global KEY_STRIP_HTML, KEY_TRIM, KEY_NFC, KEY_FIRST_TOKEN, KEY_STRIP_FURIGANA_BR
    global KANJI_GATE_ENABLED, KANJI_GATE_RUN_ON_SYNC, KANJI_GATE_BEHAVIOR, KANJI_GATE_STABILITY_AGG
    global KANJI_GATE_VOCAB_NOTE_TYPES
    global KANJI_GATE_KANJI_NOTE_TYPE, KANJI_GATE_KANJI_FIELDS
    global KANJI_GATE_KANJI_FIELD, KANJI_GATE_KANJI_ALT_FIELD
    global KANJI_GATE_COMPONENTS_FIELD, KANJI_GATE_KANJI_RADICAL_FIELD
    global KANJI_GATE_RADICAL_NOTE_TYPE, KANJI_GATE_RADICAL_FIELD
    global KANJI_GATE_KANJI_THRESHOLD, KANJI_GATE_COMPONENT_THRESHOLD
    global MASS_LINKER_ENABLED, MASS_LINKER_RULES
    global STABILITY_DEFAULT_THRESHOLD, STABILITY_AGG

    CFG = _load_config()

    _dbg = CFG.get("debug", {})
    if isinstance(_dbg, dict):
        DEBUG = bool(_dbg.get("enabled", False))
    else:
        DEBUG = bool(_dbg)

    FAMILY_GATE_ENABLED = bool(cfg_get("family_gate.enabled", True))
    FAMILY_GATE_RUN_ON_SYNC = bool(cfg_get("family_gate.run_on_sync", True))
    FAMILY_LINK_ENABLED = bool(cfg_get("family_gate.link_family_member", False))
    FAMILY_FIELD = str(cfg_get("family_gate.family.field", "FamilyID"))
    FAMILY_SEP = str(cfg_get("family_gate.family.separator", ";"))
    FAMILY_DEFAULT_PRIO = int(cfg_get("family_gate.family.default_prio", 0))
    FAMILY_NOTE_TYPES = cfg_get("family_gate.note_types", {}) or {}

    CARD_STAGES_ENABLED = bool(cfg_get("card_stages.enabled", True))
    CARD_STAGES_RUN_ON_SYNC = bool(cfg_get("card_stages.run_on_sync", True))
    CARD_STAGES_NOTE_TYPES = cfg_get(
        "card_stages.note_types", cfg_get("family_gate.note_types", {})
    ) or {}

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

    KANJI_GATE_ENABLED = bool(cfg_get("kanji_gate.enabled", True))
    KANJI_GATE_RUN_ON_SYNC = bool(cfg_get("kanji_gate.run_on_sync", True))
    KANJI_GATE_BEHAVIOR = str(cfg_get("kanji_gate.behavior", "kanji_and_components")).strip()
    if not KANJI_GATE_BEHAVIOR:
        KANJI_GATE_BEHAVIOR = "kanji_and_components"
    KANJI_GATE_STABILITY_AGG = "min"
    KANJI_GATE_VOCAB_NOTE_TYPES = cfg_get("kanji_gate.vocab_note_types", {}) or {}
    if isinstance(KANJI_GATE_VOCAB_NOTE_TYPES, dict):
        normalized_vocab_cfg: dict[str, Any] = {}
        for nt_id, nt_cfg in KANJI_GATE_VOCAB_NOTE_TYPES.items():
            if not isinstance(nt_cfg, dict):
                continue
            item = dict(nt_cfg)
            reading_field = str(item.get("reading_field", "")).strip()
            if not reading_field:
                reading_field = str(item.get("furigana_field", "")).strip()
            if reading_field:
                item["reading_field"] = reading_field
            if "furigana_field" in item:
                del item["furigana_field"]
            normalized_vocab_cfg[str(nt_id)] = item
        KANJI_GATE_VOCAB_NOTE_TYPES = normalized_vocab_cfg
    KANJI_GATE_KANJI_NOTE_TYPE = str(cfg_get("kanji_gate.kanji_note_type", "")).strip()
    fields_raw = cfg_get("kanji_gate.kanji_fields", None)
    if isinstance(fields_raw, list):
        KANJI_GATE_KANJI_FIELDS = [str(x).strip() for x in fields_raw if str(x).strip()]
    else:
        KANJI_GATE_KANJI_FIELDS = []
    if not KANJI_GATE_KANJI_FIELDS:
        legacy_main = str(cfg_get("kanji_gate.kanji_field", "")).strip()
        legacy_alt = str(cfg_get("kanji_gate.kanji_alt_field", "")).strip()
        if legacy_main:
            KANJI_GATE_KANJI_FIELDS.append(legacy_main)
        if legacy_alt and legacy_alt not in KANJI_GATE_KANJI_FIELDS:
            KANJI_GATE_KANJI_FIELDS.append(legacy_alt)
    KANJI_GATE_KANJI_FIELD = KANJI_GATE_KANJI_FIELDS[0] if KANJI_GATE_KANJI_FIELDS else ""
    KANJI_GATE_KANJI_ALT_FIELD = (
        KANJI_GATE_KANJI_FIELDS[1] if len(KANJI_GATE_KANJI_FIELDS) > 1 else ""
    )
    KANJI_GATE_COMPONENTS_FIELD = str(cfg_get("kanji_gate.components_field", "")).strip()
    KANJI_GATE_KANJI_RADICAL_FIELD = str(cfg_get("kanji_gate.kanji_radical_field", "")).strip()
    KANJI_GATE_RADICAL_NOTE_TYPE = str(cfg_get("kanji_gate.radical_note_type", "")).strip()
    KANJI_GATE_RADICAL_FIELD = str(cfg_get("kanji_gate.radical_field", "")).strip()
    KANJI_GATE_KANJI_THRESHOLD = float(
        cfg_get("kanji_gate.kanji_threshold", 14.0)
    )
    KANJI_GATE_COMPONENT_THRESHOLD = 14.0

    MASS_LINKER_ENABLED = bool(cfg_get("mass_linker.enabled", True))
    MASS_LINKER_RULES = cfg_get("mass_linker.rules", {}) or {}

    STABILITY_DEFAULT_THRESHOLD = 14.0
    STABILITY_AGG = "min"

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
            CARD_STAGES_NOTE_TYPES = _map_dict_keys(col, CARD_STAGES_NOTE_TYPES)
            KANJI_GATE_VOCAB_NOTE_TYPES = _map_dict_keys(col, KANJI_GATE_VOCAB_NOTE_TYPES)
            MASS_LINKER_RULES = _map_dict_keys(col, MASS_LINKER_RULES)
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


__version__ = "1.2.1-beta"


def _note_type_info() -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    if mw is None or not getattr(mw, "col", None):
        return out
    try:
        models = mw.col.models.all()
    except Exception:
        models = []
    for m in models:
        if not isinstance(m, dict):
            continue
        mid = m.get("id")
        name = m.get("name")
        if mid is None or not name:
            continue
        fields = [str(f.get("name", "")) for f in (m.get("flds") or []) if f.get("name")]
        templates = [str(t.get("name", "")) for t in (m.get("tmpls") or []) if t.get("name")]
        out[str(mid)] = {
            "id": str(mid),
            "name": str(name),
            "fields": fields,
            "templates": templates,
        }
    return out


def get_graph_config(*, reload: bool = True) -> dict[str, Any]:
    if reload:
        config.reload_config()
    return {
        "debug_enabled": bool(config.DEBUG),
        "family_gate": {
            "enabled": bool(config.FAMILY_GATE_ENABLED),
            "run_on_sync": bool(config.FAMILY_GATE_RUN_ON_SYNC),
            "link_family_member": bool(config.FAMILY_LINK_ENABLED),
            "family_field": str(config.FAMILY_FIELD or ""),
            "separator": str(config.FAMILY_SEP or ";"),
            "default_prio": int(config.FAMILY_DEFAULT_PRIO),
            "note_types": dict(config.FAMILY_NOTE_TYPES or {}),
        },
        "card_stages": {
            "enabled": bool(config.CARD_STAGES_ENABLED),
            "run_on_sync": bool(config.CARD_STAGES_RUN_ON_SYNC),
            "note_types": dict(config.CARD_STAGES_NOTE_TYPES or {}),
        },
        "example_gate": {
            "enabled": bool(config.EXAMPLE_GATE_ENABLED),
            "run_on_sync": bool(config.EXAMPLE_GATE_RUN_ON_SYNC),
            "vocab_deck": str(config.VOCAB_DECK or ""),
            "example_deck": str(config.EXAMPLE_DECK or ""),
            "key_field": str(config.EXAMPLE_KEY_FIELD or ""),
            "lookup_mode": "cloze_lemma",
            "force_nid_supported": True,
            "vocab_key_field": str(config.VOCAB_KEY_FIELD or ""),
            "example_key_field": str(config.EXAMPLE_KEY_FIELD or ""),
            "threshold": float(config.EXAMPLE_THRESHOLD),
            "key_norm": {
                "strip_html": bool(config.KEY_STRIP_HTML),
                "strip_furigana_brackets": bool(config.KEY_STRIP_FURIGANA_BR),
                "trim": bool(config.KEY_TRIM),
                "unicode_nfc": bool(config.KEY_NFC),
                "first_token_only": bool(config.KEY_FIRST_TOKEN),
            },
        },
        "kanji_gate": {
            "enabled": bool(config.KANJI_GATE_ENABLED),
            "run_on_sync": bool(config.KANJI_GATE_RUN_ON_SYNC),
            "behavior": str(config.KANJI_GATE_BEHAVIOR or ""),
            "stability_aggregation": str(config.KANJI_GATE_STABILITY_AGG or ""),
            "kanji_note_type": str(config.KANJI_GATE_KANJI_NOTE_TYPE or ""),
            "kanji_fields": list(config.KANJI_GATE_KANJI_FIELDS or []),
            "kanji_field": str(config.KANJI_GATE_KANJI_FIELD or ""),
            "kanji_alt_field": str(config.KANJI_GATE_KANJI_ALT_FIELD or ""),
            "components_field": str(config.KANJI_GATE_COMPONENTS_FIELD or ""),
            "kanji_radical_field": str(config.KANJI_GATE_KANJI_RADICAL_FIELD or ""),
            "radical_note_type": str(config.KANJI_GATE_RADICAL_NOTE_TYPE or ""),
            "radical_field": str(config.KANJI_GATE_RADICAL_FIELD or ""),
            "kanji_threshold": float(config.KANJI_GATE_KANJI_THRESHOLD),
            "component_threshold": float(config.KANJI_GATE_COMPONENT_THRESHOLD),
            "vocab_note_types": dict(config.KANJI_GATE_VOCAB_NOTE_TYPES or {}),
        },
        "mass_linker": {
            "enabled": bool(config.MASS_LINKER_ENABLED),
            "rules": dict(config.MASS_LINKER_RULES or {}),
        },
        "stability": {
            "default_threshold": float(config.STABILITY_DEFAULT_THRESHOLD),
            "aggregation": str(config.STABILITY_AGG or ""),
        },
        "note_types": _note_type_info(),
    }


def _install_graph_api() -> None:
    if mw is None:
        return
    mw._ajpc_graph_api = {
        "get_config": get_graph_config,
        "version": __version__,
    }


def _selfcheck(*, reason: str = "init") -> None:
    if mw is None:
        return
    api = getattr(mw, "_ajpc_graph_api", None)
    ok = isinstance(api, dict) and callable(api.get("get_config")) and bool(api.get("version"))
    try:
        mw._ajpc_graph_api_status = "ok" if ok else "missing"
    except Exception:
        pass
    try:
        from aqt.utils import tooltip

        if ok:
            if config.DEBUG:
                tooltip(f"AJPC Graph API ready ({reason}).", period=2500)
        else:
            tooltip(f"AJPC Graph API missing ({reason}).", period=2500)
    except Exception:
        pass


def install_graph_api() -> None:
    _install_graph_api()
    _selfcheck(reason="init")

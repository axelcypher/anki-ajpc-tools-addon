from __future__ import annotations

import json
import os
from typing import Any

from aqt import mw

from . import ModuleSpec

ADDON_DIR = os.path.dirname(os.path.dirname(__file__))
CONFIG_PATH = os.path.join(ADDON_DIR, "config.json")

CFG: dict[str, Any] = {}
DEBUG = False

FAMILY_GATE_ENABLED = True
FAMILY_LINK_ENABLED = False
FAMILY_LINK_CSS_SELECTOR = ""
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
KEY_STRIP_HTML = True
KEY_TRIM = True
KEY_NFC = True
KEY_FIRST_TOKEN = True
KEY_STRIP_FURIGANA_BR = False

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

NOTE_LINKER_ENABLED = True
NOTE_LINKER_RULES: dict[str, Any] = {}

STABILITY_DEFAULT_THRESHOLD = 2.5
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
    global FAMILY_GATE_ENABLED, FAMILY_LINK_ENABLED, FAMILY_LINK_CSS_SELECTOR
    global FAMILY_FIELD, FAMILY_SEP, FAMILY_DEFAULT_PRIO, FAMILY_NOTE_TYPES
    global EXAMPLE_GATE_ENABLED, VOCAB_DECK, EXAMPLE_DECK, VOCAB_KEY_FIELD, EXAMPLE_KEY_FIELD
    global EX_STAGE_SEP, EX_STAGE_DEFAULT
    global KEY_STRIP_HTML, KEY_TRIM, KEY_NFC, KEY_FIRST_TOKEN, KEY_STRIP_FURIGANA_BR
    global KANJI_GATE_ENABLED, KANJI_GATE_BEHAVIOR, KANJI_GATE_STABILITY_AGG
    global KANJI_GATE_VOCAB_NOTE_TYPES
    global KANJI_GATE_KANJI_NOTE_TYPE, KANJI_GATE_KANJI_FIELD, KANJI_GATE_KANJI_ALT_FIELD
    global KANJI_GATE_COMPONENTS_FIELD, KANJI_GATE_KANJI_RADICAL_FIELD
    global KANJI_GATE_RADICAL_NOTE_TYPE, KANJI_GATE_RADICAL_FIELD
    global KANJI_GATE_KANJI_THRESHOLD, KANJI_GATE_COMPONENT_THRESHOLD
    global NOTE_LINKER_ENABLED, NOTE_LINKER_RULES
    global STABILITY_DEFAULT_THRESHOLD, STABILITY_AGG

    CFG = _load_config()

    _dbg = CFG.get("debug", {})
    if isinstance(_dbg, dict):
        DEBUG = bool(_dbg.get("enabled", False))
    else:
        DEBUG = bool(_dbg)

    FAMILY_GATE_ENABLED = bool(cfg_get("family_gate.enabled", True))
    FAMILY_LINK_ENABLED = bool(cfg_get("family_gate.link_family_member", False))
    FAMILY_LINK_CSS_SELECTOR = str(cfg_get("family_gate.link_css_selector", "")).strip()
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

    NOTE_LINKER_ENABLED = bool(cfg_get("note_linker.enabled", True))
    NOTE_LINKER_RULES = cfg_get("note_linker.rules", {}) or {}

    STABILITY_DEFAULT_THRESHOLD = float(cfg_get("stability.default_threshold", 2.5))
    STABILITY_AGG = str(cfg_get("stability.aggregation", "min")).lower().strip()
    if STABILITY_AGG not in ("min", "max", "avg"):
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
            KANJI_GATE_VOCAB_NOTE_TYPES = _map_dict_keys(col, KANJI_GATE_VOCAB_NOTE_TYPES)
            NOTE_LINKER_RULES = _map_dict_keys(col, NOTE_LINKER_RULES)
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
            "link_family_member": bool(config.FAMILY_LINK_ENABLED),
            "link_css_selector": str(config.FAMILY_LINK_CSS_SELECTOR or ""),
            "family_field": str(config.FAMILY_FIELD or ""),
            "separator": str(config.FAMILY_SEP or ";"),
            "default_prio": int(config.FAMILY_DEFAULT_PRIO),
            "note_types": dict(config.FAMILY_NOTE_TYPES or {}),
        },
        "example_gate": {
            "enabled": bool(config.EXAMPLE_GATE_ENABLED),
            "vocab_deck": str(config.VOCAB_DECK or ""),
            "example_deck": str(config.EXAMPLE_DECK or ""),
            "vocab_key_field": str(config.VOCAB_KEY_FIELD or ""),
            "example_key_field": str(config.EXAMPLE_KEY_FIELD or ""),
            "stage_sep": str(config.EX_STAGE_SEP or "@"),
            "default_stage": int(config.EX_STAGE_DEFAULT),
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
            "behavior": str(config.KANJI_GATE_BEHAVIOR or ""),
            "stability_aggregation": str(config.KANJI_GATE_STABILITY_AGG or ""),
            "kanji_note_type": str(config.KANJI_GATE_KANJI_NOTE_TYPE or ""),
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
        "note_linker": {
            "enabled": bool(config.NOTE_LINKER_ENABLED),
            "rules": dict(config.NOTE_LINKER_RULES or {}),
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
                tooltip(f"AJPC Graph API ready ({reason}).")
        else:
            tooltip(f"AJPC Graph API missing ({reason}).")
    except Exception:
        pass


def _init() -> None:
    from aqt import gui_hooks

    _install_graph_api()
    _selfcheck(reason="init")

    def _on_profile_open(*_args, **_kw) -> None:
        _install_graph_api()
        _selfcheck(reason="profile")

    gui_hooks.profile_did_open.append(_on_profile_open)


MODULE = ModuleSpec(
    id="graph_api",
    label="Graph API",
    order=60,
    init=_init,
)

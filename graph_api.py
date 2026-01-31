from __future__ import annotations

from typing import Any

from aqt import mw

from . import config


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

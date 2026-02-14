from __future__ import annotations

import json
import os
from typing import Any

from aqt import mw

from .. import logging

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
    mass_rules_raw = config.MASS_LINKER_RULES or {}
    if isinstance(mass_rules_raw, dict):
        mass_rules_out: Any = dict(mass_rules_raw)
    elif isinstance(mass_rules_raw, list):
        mass_rules_out = list(mass_rules_raw)
    else:
        mass_rules_out = []
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
            "rules": mass_rules_out,
        },
        "stability": {
            "default_threshold": float(config.STABILITY_DEFAULT_THRESHOLD),
            "aggregation": str(config.STABILITY_AGG or ""),
        },
        "note_types": _note_type_info(),
    }


def _provider_category_for_graph_api(provider_id: str) -> str:
    pid = str(provider_id or "").strip().lower()
    if pid == "family_gate" or pid.startswith("family_") or "family" in pid:
        return "family"
    if (
        pid == "mass_linker"
        or pid == "note_linker"
        or pid.startswith("mass_")
        or "mass" in pid
        or "note_linker" in pid
    ):
        return "mass"
    return "other"


def _iter_link_providers_for_graph_api() -> list[tuple[str, int, Any]]:
    try:
        from ..modules import link_core
    except Exception:
        return []
    try:
        return list(link_core._iter_providers())  # type: ignore[attr-defined]
    except Exception:
        pass
    providers = getattr(link_core, "_PROVIDERS", {})
    out: list[tuple[str, int, Any]] = []
    if isinstance(providers, dict):
        for provider_id, payload in providers.items():
            try:
                prio, fn = payload
                out.append((str(provider_id), int(prio), fn))
            except Exception:
                continue
    out.sort(key=lambda x: (x[1], x[0]))
    return out


def _payload_refs_for_graph_api(payload: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []

    def _add_ref(ref: Any, group_key: str = "") -> None:
        try:
            kind = str(getattr(ref, "kind", "nid") or "nid").strip().lower()
            target_id = int(getattr(ref, "target_id", 0) or 0)
            label = str(getattr(ref, "label", "") or "")
        except Exception:
            return
        if target_id <= 0:
            return
        if kind not in ("nid", "cid"):
            kind = "nid"
        out.append(
            {
                "kind": kind,
                "target_id": target_id,
                "label": label,
                "group": str(group_key or ""),
            }
        )

    links = getattr(payload, "links", None) or []
    groups = getattr(payload, "groups", None) or []
    for ref in links:
        _add_ref(ref, "")
    for grp in groups:
        gkey = str(getattr(grp, "key", "") or "")
        summary = getattr(grp, "summary", None)
        if summary is not None:
            _add_ref(summary, gkey)
        for ref in (getattr(grp, "links", None) or []):
            _add_ref(ref, gkey)
    return out


def get_link_provider_edges(
    *,
    note_ids: list[int] | None = None,
    provider_ids: list[str] | None = None,
    include_family: bool = False,
) -> dict[str, Any]:
    if mw is None or not getattr(mw, "col", None):
        return {"providers": [], "edges": []}

    try:
        from ..modules import link_core
    except Exception:
        return {"providers": [], "edges": []}

    providers_all = _iter_link_providers_for_graph_api()
    selected_provider_ids = {
        str(x).strip().lower() for x in (provider_ids or []) if str(x).strip()
    }

    providers: list[tuple[str, int, Any, str]] = []
    for provider_id, prio, fn in providers_all:
        pid = str(provider_id or "").strip()
        if not pid or not callable(fn):
            continue
        pid_low = pid.lower()
        if selected_provider_ids and pid_low not in selected_provider_ids:
            continue
        category = _provider_category_for_graph_api(pid)
        if category == "family" and not include_family:
            continue
        providers.append((pid, int(prio), fn, category))

    if not providers:
        return {"providers": [], "edges": []}

    col = mw.col
    source_nids: list[int] = []
    if note_ids:
        seen_nids: set[int] = set()
        for nid in note_ids:
            try:
                val = int(nid or 0)
            except Exception:
                continue
            if val <= 0 or val in seen_nids:
                continue
            seen_nids.add(val)
            source_nids.append(val)
    else:
        try:
            source_nids = [int(x) for x in (col.find_notes("") or []) if int(x) > 0]
        except Exception:
            source_nids = []

    providers_meta = [
        {"id": pid, "order": int(prio), "category": category}
        for pid, prio, _fn, category in providers
    ]
    if not source_nids:
        return {"providers": providers_meta, "edges": []}

    edges: list[dict[str, Any]] = []
    seen_edges: set[tuple[str, int, str, int, str, str]] = set()
    for source_nid in source_nids:
        try:
            note = col.get_note(int(source_nid))
        except Exception:
            continue
        try:
            cards = note.cards() or []
        except Exception:
            cards = []
        if not cards:
            continue
        for card in cards:
            known_nids: set[int] = set()
            known_cids: set[int] = set()
            for kind in ("reviewQuestion", "reviewAnswer"):
                for provider_id, _prio, provider_fn, category in providers:
                    try:
                        ctx = link_core.ProviderContext(
                            card=card,
                            kind=kind,
                            note=note,
                            html="",
                            existing_nids=set(known_nids),
                            existing_cids=set(known_cids),
                        )
                        payloads = provider_fn(ctx) or []
                    except Exception:
                        continue
                    for payload in payloads:
                        for ref in _payload_refs_for_graph_api(payload):
                            ref_kind = str(ref.get("kind", "nid") or "nid").strip().lower()
                            ref_target = int(ref.get("target_id", 0) or 0)
                            ref_label = str(ref.get("label", "") or "")
                            ref_group = str(ref.get("group", "") or "")
                            if ref_target <= 0:
                                continue

                            target_nid = 0
                            if ref_kind == "cid":
                                known_cids.add(ref_target)
                                try:
                                    target_nid = int(col.get_card(ref_target).nid)
                                except Exception:
                                    target_nid = 0
                            else:
                                known_nids.add(ref_target)
                                try:
                                    target_nid = int(col.get_note(ref_target).id)
                                except Exception:
                                    target_nid = 0
                            if target_nid <= 0:
                                continue

                            edge_key = (
                                str(provider_id),
                                int(source_nid),
                                str(ref_kind),
                                int(ref_target),
                                str(ref_label),
                                str(ref_group),
                            )
                            if edge_key in seen_edges:
                                continue
                            seen_edges.add(edge_key)
                            edges.append(
                                {
                                    "provider_id": str(provider_id),
                                    "provider_category": str(category),
                                    "source_nid": int(source_nid),
                                    "source_cid": int(getattr(card, "id", 0) or 0),
                                    "target_kind": str(ref_kind),
                                    "target_id": int(ref_target),
                                    "target_nid": int(target_nid),
                                    "label": str(ref_label),
                                    "group": str(ref_group),
                                }
                            )

    logging.dbg(
        "graph_api provider edges",
        "providers=",
        len(providers_meta),
        "source_notes=",
        len(source_nids),
        "edges=",
        len(edges),
        source="graph_api",
    )
    return {"providers": providers_meta, "edges": edges}


def _open_note_editor_for_graph_api(
    nid: int, *, title: str = "AJpC Note Editor"
) -> bool:
    try:
        from .note_editor_api import open_editor as _open_editor

        return bool(_open_editor(int(nid), title=str(title or "AJpC Note Editor")))
    except Exception:
        return False


def _is_note_editor_open_for_graph_api(nid: int) -> bool:
    try:
        from .note_editor_api import is_open as _is_open

        return bool(_is_open(int(nid)))
    except Exception:
        return False


def _resolve_dep_tree_nid(
    nid: int | None = None,
    *,
    note_id: int | None = None,
    id: int | None = None,
) -> int:
    candidates = [nid, note_id, id]
    for value in candidates:
        try:
            out = int(value or 0)
        except Exception:
            continue
        if out > 0:
            return out
    return 0


def get_dependency_tree(
    nid: int | None = None,
    *,
    note_id: int | None = None,
    id: int | None = None,
    view_width: int = 0,
    include_raw: bool = True,
) -> dict[str, Any]:
    target_nid = _resolve_dep_tree_nid(nid, note_id=note_id, id=id)
    if target_nid <= 0:
        return {"nodes": [], "edges": [], "current_nid": 0}

    try:
        from ..modules import browser_graph as _bg
    except Exception:
        return {"nodes": [], "edges": [], "current_nid": int(target_nid)}

    try:
        chain_nodes, chain_edges, chain_labels = _bg._family_prio_chain(int(target_nid))  # noqa: SLF001 - shared internal data builder
    except Exception:
        return {"nodes": [], "edges": [], "current_nid": int(target_nid)}

    try:
        payload = _bg._build_prio_chain_payload(  # noqa: SLF001 - shared internal data builder
            int(target_nid),
            chain_nodes,
            chain_edges,
            chain_labels,
        )
    except Exception:
        payload = {"nodes": [], "edges": [], "current_nid": int(target_nid)}

    if include_raw:
        payload["raw_nodes"] = sorted(int(x) for x in chain_nodes if int(x) > 0)
        payload["raw_edges"] = [
            [int(src), int(dst)]
            for src, dst in chain_edges
            if int(src) > 0 and int(dst) > 0
        ]
        payload["raw_labels"] = {
            str(int(k)): str(v)
            for k, v in (chain_labels or {}).items()
            if int(k) > 0
        }

    try:
        vw = int(view_width or 0)
    except Exception:
        vw = 0
    if vw > 0:
        try:
            payload["estimated_height"] = int(
                _bg._estimate_prio_needed_height(  # noqa: SLF001 - shared internal data builder
                    int(target_nid),
                    chain_nodes,
                    chain_edges,
                    chain_labels,
                    int(vw),
                )
            )
        except Exception:
            payload["estimated_height"] = 0

    return payload


def _install_graph_api() -> None:
    if mw is None:
        return
    editor_api = {
        "open_note_editor": _open_note_editor_for_graph_api,
        "open_editor_for_note": _open_note_editor_for_graph_api,
        "open_editor": _open_note_editor_for_graph_api,
        "edit_note": _open_note_editor_for_graph_api,
        "show_note_editor": _open_note_editor_for_graph_api,
        "is_open": _is_note_editor_open_for_graph_api,
    }
    mw._ajpc_graph_api = {
        "get_config": get_graph_config,
        "get_dependency_tree": get_dependency_tree,
        "get_prio_chain": get_dependency_tree,
        "get_link_provider_edges": get_link_provider_edges,
        "get_provider_link_edges": get_link_provider_edges,
        "version": __version__,
        # Keep editor entry points on graph API so dependent add-ons can
        # open the AJPC popup editor with its integrated side panel.
        "open_note_editor": _open_note_editor_for_graph_api,
        "open_editor_for_note": _open_note_editor_for_graph_api,
        "open_editor": _open_note_editor_for_graph_api,
        "edit_note": _open_note_editor_for_graph_api,
        "show_note_editor": _open_note_editor_for_graph_api,
        "is_note_editor_open": _is_note_editor_open_for_graph_api,
        "editor": editor_api,
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

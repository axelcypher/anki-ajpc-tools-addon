from __future__ import annotations

import traceback
from dataclasses import dataclass
from typing import Any

from anki.collection import Collection

from .. import config, logging
from ..utils import (
    _tmpl_by_ord,
    _verify_suspended,
    card_stability,
    extract_kanji,
    note_ids_for_note_types,
    strip_furigana_brackets,
    suspend_cards,
    unsuspend_cards,
)

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


def _templates_stability(note, name_by_ord: dict[int, str], templates: set[str], mode: str) -> float | None:
    if not templates:
        return None
    vals: list[float] = []
    saw_any = False
    for card in note.cards():
        if name_by_ord.get(card.ord, "") in templates:
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
        base_templates = [str(x).strip() for x in (cfg.get("base_templates") or []) if str(x).strip()]
        kanji_templates = [str(x).strip() for x in (cfg.get("kanji_templates") or []) if str(x).strip()]
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
        logging.dbg("kanji_gate disabled")
        return

    behavior = str(config.KANJI_GATE_BEHAVIOR or "").strip()
    if behavior not in (
        "kanji_only",
        "kanji_then_components",
        "components_then_kanji",
        "kanji_and_components",
    ):
        logging.dbg("kanji_gate: invalid behavior", behavior)
        return

    agg_mode = str(config.KANJI_GATE_STABILITY_AGG or "min").strip()
    if agg_mode not in ("min", "max", "avg"):
        agg_mode = "min"

    vocab_cfgs = _get_vocab_cfgs()
    if not vocab_cfgs:
        logging.dbg("kanji_gate: no vocab note types configured")
        return

    kanji_note_type = config.KANJI_GATE_KANJI_NOTE_TYPE
    kanji_field = config.KANJI_GATE_KANJI_FIELD
    kanji_alt_field = config.KANJI_GATE_KANJI_ALT_FIELD
    components_field = config.KANJI_GATE_COMPONENTS_FIELD
    kanji_radical_field = config.KANJI_GATE_KANJI_RADICAL_FIELD
    radical_note_type = config.KANJI_GATE_RADICAL_NOTE_TYPE
    radical_field = config.KANJI_GATE_RADICAL_FIELD

    if not kanji_note_type or not kanji_field:
        logging.dbg("kanji_gate: missing kanji config")
        return

    use_components = behavior in ("kanji_then_components", "components_then_kanji", "kanji_and_components")
    if use_components and not components_field:
        logging.dbg("kanji_gate: missing components field")
        return

    radicals_enabled = bool(
        use_components and kanji_radical_field and radical_note_type and radical_field
    )

    vocab_note_types = list(vocab_cfgs.keys())
    vocab_nids = note_ids_for_note_types(col, vocab_note_types)
    logging.dbg("kanji_gate: vocab notes", len(vocab_nids))

    vocab_notes: list[VocabNoteInfo] = []
    target_kanji: set[str] = set()
    vocab_kanji_scope_cards: set[int] = set()

    note_cache: dict[int, Any] = {}
    name_by_ord_cache: dict[int, dict[int, str]] = {}

    def _get_note(nid: int):
        if nid not in note_cache:
            note_cache[nid] = col.get_note(nid)
        return note_cache[nid]

    def _get_name_by_ord(nid: int) -> dict[int, str]:
        if nid not in name_by_ord_cache:
            name_by_ord_cache[nid] = _tmpl_by_ord(col, _get_note(nid))
        return name_by_ord_cache[nid]

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

            name_by_ord = _get_name_by_ord(nid)
            base_templates = set(cfg.base_templates)
            base_stab = _templates_stability(note, name_by_ord, base_templates, agg_mode)
            base_ready = base_stab is not None and base_stab >= cfg.base_threshold

            kanji_templates = set(cfg.kanji_templates)
            kanji_card_ids: list[int] = []
            if kanji_templates:
                for card in note.cards():
                    tmpl = name_by_ord.get(card.ord, "")
                    if tmpl in kanji_templates:
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
            logging.dbg("kanji_gate: exception indexing vocab nid", nid)
            logging.dbg(traceback.format_exc())

    if not vocab_notes:
        logging.dbg("kanji_gate: no vocab notes with kanji")
        return

    kanji_index: dict[str, list[KanjiNoteEntry]] = {}
    note_chars: dict[int, set[str]] = {}
    all_radicals: set[str] = set()
    kanji_nids = note_ids_for_note_types(col, [kanji_note_type])
    logging.dbg("kanji_gate: kanji notes", len(kanji_nids))

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
            logging.dbg("kanji_gate: exception indexing kanji nid", nid)
            logging.dbg(traceback.format_exc())

    radical_index: dict[str, list[int]] = {}
    if radicals_enabled:
        radical_nids = note_ids_for_note_types(col, [radical_note_type])
        logging.dbg("kanji_gate: radical notes", len(radical_nids))
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
                logging.dbg("kanji_gate: exception indexing radical nid", nid)
                logging.dbg(traceback.format_exc())

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
            logging.dbg("kanji_gate: exception applying vocab nid", info.nid)
            logging.dbg(traceback.format_exc())

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
            logging.dbg("kanji_gate: exception applying kanji nid", nid)
            logging.dbg(traceback.format_exc())

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
                logging.dbg("kanji_gate: exception applying radical nid", rnid)
                logging.dbg(traceback.format_exc())

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

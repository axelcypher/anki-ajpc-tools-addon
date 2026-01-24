from __future__ import annotations

import traceback
from dataclasses import dataclass

from anki.collection import Collection

from .. import config, logging
from ..utils import (
    DEFAULT_STICKY_TAG_BASE,
    _verify_suspended,
    compute_stage_stabilities,
    example_stage_tag,
    get_stage_cfg_for_note_type,
    note_ids_for_deck,
    norm_text,
    parse_example_key,
    stage_is_ready,
    suspend_cards,
    unsuspend_cards,
)


@dataclass
class VocabIndexEntry:
    nid: int
    note_type: str
    stage_stabs: list[float | None]


def example_gate_apply(col: Collection, ui_set, counters: dict[str, int]) -> None:
    if not config.EXAMPLE_GATE_ENABLED:
        logging.dbg("example_gate disabled")
        return
    if not config.VOCAB_DECK or not config.EXAMPLE_DECK:
        logging.dbg(
            "example_gate: missing deck config",
            "vocab_deck=",
            config.VOCAB_DECK,
            "example_deck=",
            config.EXAMPLE_DECK,
        )
        return
    if not config.VOCAB_KEY_FIELD or not config.EXAMPLE_KEY_FIELD:
        logging.dbg(
            "example_gate: missing key field config",
            "vocab_key_field=",
            config.VOCAB_KEY_FIELD,
            "example_key_field=",
            config.EXAMPLE_KEY_FIELD,
        )
        return

    vocab_nids = note_ids_for_deck(col, config.VOCAB_DECK)
    logging.dbg("example_gate: vocab notes", len(vocab_nids))

    vocab_index: dict[str, VocabIndexEntry] = {}

    for i, nid in enumerate(vocab_nids):
        try:
            note = col.get_note(nid)
            model = col.models.get(note.mid)
            nt_name = str(model.get("name", ""))

            if nt_name not in config.FAMILY_NOTE_TYPES:
                continue
            if config.VOCAB_KEY_FIELD not in note:
                continue

            key = norm_text(str(note[config.VOCAB_KEY_FIELD] or ""))
            if not key:
                continue
            if key in vocab_index:
                continue

            stabs = compute_stage_stabilities(col, note, nt_name)
            vocab_index[key] = VocabIndexEntry(nid=nid, note_type=nt_name, stage_stabs=stabs)

            if config.DEBUG and i < 10:
                logging.dbg("example_gate: indexed", key, "stabs", stabs)

            if i % 400 == 0:
                ui_set(
                    f"ExampleGate: index vocab... {i}/{len(vocab_nids)} (keys={len(vocab_index)})",
                    i,
                    len(vocab_nids),
                )
        except Exception:
            logging.dbg("example_gate: exception indexing vocab nid", nid)
            logging.dbg(traceback.format_exc())

    logging.dbg("example_gate: vocab keys", len(vocab_index))

    ex_nids = note_ids_for_deck(col, config.EXAMPLE_DECK)
    logging.dbg("example_gate: example notes", len(ex_nids))

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
                allow = stage_is_ready(entry.note_type, ref.stage, stab_val)
                thr = get_stage_cfg_for_note_type(entry.note_type)[ref.stage].threshold
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
                    logging.dbg(
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
                    logging.dbg(
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
            logging.dbg("example_gate: exception processing example nid", nid)
            logging.dbg(traceback.format_exc())

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

from __future__ import annotations

import traceback
from dataclasses import dataclass

from anki.collection import Collection

from .. import config, logging
from ..utils import (
    DEFAULT_STICKY_TAG_BASE,
    _dbg_card_state,
    _tmpl_by_ord,
    _verify_suspended,
    compute_stage_stabilities,
    debug_template_coverage,
    get_stage_cfg_for_note_type,
    note_ids_for_note_types,
    parse_family_field,
    stage_card_ids,
    stage_is_ready,
    stage_tag,
    suspend_cards,
    unsuspend_cards,
)


@dataclass
class NoteInFamily:
    nid: int
    note_type_id: int
    prio: int


def family_gate_apply(col: Collection, ui_set, counters: dict[str, int]) -> None:
    if not config.FAMILY_GATE_ENABLED:
        logging.dbg("family_gate disabled")
        return

    note_types = list(config.FAMILY_NOTE_TYPES.keys())
    if not note_types:
        logging.dbg("family_gate: no note_types configured")
        return

    nids = note_ids_for_note_types(col, note_types)
    logging.dbg("family_gate: candidate notes", len(nids))
    debug_template_coverage(col)

    fam_map: dict[str, list[NoteInFamily]] = {}
    note_refs: dict[int, tuple[int, list]] = {}

    for i, nid in enumerate(nids):
        try:
            note = col.get_note(nid)
            nt_id = int(note.mid)

            if config.FAMILY_FIELD not in note:
                continue

            refs = parse_family_field(str(note[config.FAMILY_FIELD] or ""))
            if not refs:
                continue

            note_refs[nid] = (nt_id, refs)

            for r in refs:
                fam_map.setdefault(r.fid, []).append(NoteInFamily(nid=nid, note_type_id=nt_id, prio=r.prio))

            if i % 250 == 0:
                ui_set(
                    f"FamilyGate: index families... {i}/{len(nids)} (families={len(fam_map)})",
                    i,
                    len(nids),
                )
        except Exception:
            logging.dbg("family_gate: exception indexing nid", nid)
            logging.dbg(traceback.format_exc())

    logging.dbg("family_gate: unique families", len(fam_map))

    note_stage_stabs: dict[int, list[float | None]] = {}
    note_stage0_ready: dict[int, bool] = {}

    for i, (nid, (nt_id, _refs)) in enumerate(note_refs.items()):
        try:
            note = col.get_note(nid)
            stages = get_stage_cfg_for_note_type(nt_id)
            if not stages:
                note_stage_stabs[nid] = []
                note_stage0_ready[nid] = True
                continue

            stabs = compute_stage_stabilities(col, note, nt_id)
            note_stage_stabs[nid] = stabs
            s0 = stabs[0] if stabs else None
            note_stage0_ready[nid] = stage_is_ready(nt_id, 0, s0)
        except Exception:
            note_stage_stabs[nid] = []
            note_stage0_ready[nid] = False

        if i % 400 == 0:
            ui_set(f"FamilyGate: compute stability... {i}/{len(note_refs)}", i, len(note_refs))

    family_gate_open: dict[str, dict[int, bool]] = {}

    for fid, items in fam_map.items():
        items.sort(key=lambda x: x.prio)

        groups: list[list[NoteInFamily]] = []
        cur: list[NoteInFamily] = []
        last_prio: int | None = None
        for it in items:
            if last_prio is None or it.prio != last_prio:
                if cur:
                    groups.append(cur)
                cur = [it]
                last_prio = it.prio
            else:
                cur.append(it)
        if cur:
            groups.append(cur)

        prev_groups_ready = True

        for g_i, g_notes in enumerate(groups):
            prio = g_notes[0].prio
            gate_open = True if g_i == 0 else prev_groups_ready
            family_gate_open.setdefault(fid, {})[prio] = gate_open

            group_stage0_ready_all = True
            for ninfo in g_notes:
                group_stage0_ready_all = group_stage0_ready_all and bool(note_stage0_ready.get(ninfo.nid, False))

            prev_groups_ready = prev_groups_ready and group_stage0_ready_all

    to_suspend: list[int] = []
    to_unsuspend: list[int] = []

    note_items = list(note_refs.items())
    for i, (nid, (nt_id, refs)) in enumerate(note_items):
        try:
            note = col.get_note(nid)
            stages = get_stage_cfg_for_note_type(nt_id)
            if not stages:
                continue

            effective_gate_open = True
            gate_parts: list[str] = []
            for r in refs:
                ok = bool(family_gate_open.get(r.fid, {}).get(r.prio, False))
                effective_gate_open = effective_gate_open and ok
                if config.DEBUG and nid in config.WATCH_NIDS:
                    gate_parts.append(f"{r.fid}@{r.prio}={ok}")

            stabs = note_stage_stabs.get(nid, [])
            prev_stage_ok = True

            for st_idx in range(len(stages)):
                st_cids = stage_card_ids(col, note, nt_id, st_idx)
                if not st_cids:
                    continue

                should_open = effective_gate_open if st_idx == 0 else (effective_gate_open and prev_stage_ok)

                stab_val = stabs[st_idx] if st_idx < len(stabs) else None
                this_stage_ready = stage_is_ready(nt_id, st_idx, stab_val)

                st_tag = stage_tag(st_idx)
                st_sticky = config.STICKY_UNLOCK and (st_tag in note.tags)

                if config.DEBUG and nid in config.WATCH_NIDS:
                    logging.dbg(
                        "WATCH",
                        "nid=",
                        nid,
                        "refs=",
                        " | ".join(gate_parts),
                        "stage=",
                        st_idx,
                        "gate_all=",
                        effective_gate_open,
                        "should_open=",
                        should_open,
                        "sticky=",
                        st_sticky,
                        "ready=",
                        this_stage_ready,
                        "stab=",
                        stab_val,
                        "cids=",
                        len(st_cids),
                    )

                    name_by_ord = _tmpl_by_ord(col, note)
                    cards = note.cards()
                    wanted_set = set(stages[st_idx].templates)

                    for c in cards:
                        tn = name_by_ord.get(c.ord) or ""
                        if tn in wanted_set:
                            logging.dbg("WATCH_CARD", "nid=", nid, _dbg_card_state(c, tn))

                if should_open or st_sticky:
                    to_unsuspend.extend(st_cids)
                    if config.STICKY_UNLOCK and this_stage_ready and st_tag not in note.tags:
                        note.add_tag(DEFAULT_STICKY_TAG_BASE)
                        note.add_tag(st_tag)
                        note.flush()
                        counters["notes_tagged"] += 1
                else:
                    to_suspend.extend(st_cids)

                prev_stage_ok = this_stage_ready

        except Exception:
            logging.dbg("family_gate: exception applying nid", nid)
            logging.dbg(traceback.format_exc())

        if i % 400 == 0:
            ui_set(
                f"FamilyGate: apply... {i}/{len(note_items)} | unsusp={len(to_unsuspend)} susp={len(to_suspend)}",
                i,
                len(note_items),
            )

    if to_suspend:
        sus = list(set(to_suspend))
        suspend_cards(col, sus)
        counters["cards_suspended"] += len(sus)
        _verify_suspended(col, sus, label="family_suspend")

    if to_unsuspend:
        uns = list(set(to_unsuspend))
        unsuspend_cards(col, uns)
        counters["cards_unsuspended"] += len(uns)
        _verify_suspended(col, uns, label="family_unsuspend")

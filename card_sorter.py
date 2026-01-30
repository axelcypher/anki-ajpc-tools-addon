from __future__ import annotations

from typing import Any

from anki.collection import Collection, OpChanges
from aqt import mw
from aqt.operations import CollectionOp
from aqt.utils import askUser

from . import config, logging
from .utils import _tmpl_by_ord, note_ids_for_note_types


def _normalize_list(items: list[Any]) -> list[str]:
    out: list[str] = []
    for item in items:
        s = str(item).strip()
        if s:
            out.append(s)
    return out


def _get_note_type_cfgs() -> dict[str, dict[str, Any]]:
    raw = config.CARD_SORTER_NOTE_TYPES
    if not isinstance(raw, dict):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for nt_id, cfg in raw.items():
        if not isinstance(cfg, dict):
            continue
        mode = str(cfg.get("mode", "by_template")).strip() or "by_template"
        default_deck = str(cfg.get("default_deck", "")).strip()
        by_template_raw = cfg.get("by_template", {}) or {}
        by_template: dict[str, str] = {}
        if isinstance(by_template_raw, dict):
            for k, v in by_template_raw.items():
                tk = str(k).strip()
                tv = str(v).strip()
                if tk and tv:
                    by_template[tk] = tv
        out[str(nt_id)] = {
            "mode": mode,
            "default_deck": default_deck,
            "by_template": by_template,
        }
    return out


def _gather_target_decks(note_type_cfgs: dict[str, dict[str, Any]]) -> set[str]:
    targets: set[str] = set()
    for cfg in note_type_cfgs.values():
        mode = cfg.get("mode", "by_template")
        if mode == "all":
            deck = str(cfg.get("default_deck", "")).strip()
            if deck:
                targets.add(deck)
        else:
            by_template = cfg.get("by_template", {}) or {}
            if isinstance(by_template, dict):
                for deck in by_template.values():
                    deck_name = str(deck).strip()
                    if deck_name:
                        targets.add(deck_name)
    return targets


def _ensure_decks(target_decks: set[str]) -> set[str]:
    skipped: set[str] = set()
    for deck_name in sorted(target_decks):
        if not deck_name:
            continue
        if mw.col.decks.id_for_name(deck_name) is not None:
            continue
        if askUser(
            title="Card Sorter",
            text="Deck named '" + deck_name + "' is configured but does not exist. Create it?",
            defaultno=True,
        ):
            mw.col.decks.id(deck_name)
        else:
            skipped.add(deck_name)
            logging.dbg("card_sorter: deck skipped", deck_name)
    return skipped


def _deck_is_excluded(deck_name: str, exclude_decks: list[str]) -> bool:
    for ex in exclude_decks:
        if deck_name == ex or deck_name.startswith(ex):
            return True
    return False


def _note_has_excluded_tag(note, exclude_tags: set[str]) -> bool:
    if not exclude_tags:
        return False
    note_tags = set(note.tags)
    return any(tag in note_tags for tag in exclude_tags)


def _get_deck_id(deck_name: str, deck_id_cache: dict[str, int], skipped_decks: set[str]) -> int | None:
    if not deck_name or deck_name in skipped_decks:
        return None
    if deck_name in deck_id_cache:
        return deck_id_cache[deck_name]
    deck_id = mw.col.decks.id_for_name(deck_name)
    if deck_id is None:
        skipped_decks.add(deck_name)
        return None
    deck_id_cache[deck_name] = deck_id
    return deck_id


def _apply_moves(cards_in_deck: dict[int, list[int]]) -> int:
    moved = 0
    for deck_id, card_ids in cards_in_deck.items():
        if not card_ids:
            continue
        unique_ids = list(set(card_ids))
        moved += len(unique_ids)

        def op(col, cids=unique_ids, did=deck_id):
            col.db.execute(
                f"UPDATE cards SET did = ? WHERE id IN ({','.join('?' * len(cids))})",
                did,
                *cids,
            )
            return OpChanges()

        CollectionOp(mw, op).run_in_background()
    return moved


def _sort_notes(notes: list, note_type_cfgs: dict[str, dict[str, Any]], skipped_decks: set[str]) -> dict[str, int]:
    exclude_decks = _normalize_list(config.CARD_SORTER_EXCLUDE_DECKS)
    exclude_tags = set(_normalize_list(config.CARD_SORTER_EXCLUDE_TAGS))
    deck_id_cache: dict[str, int] = {}
    cards_in_deck: dict[int, list[int]] = {}

    notes_processed = 0
    cards_moved = 0

    for note in notes:
        model = mw.col.models.get(note.mid)
        nt_name = str(model.get("name", "")) if model else ""
        nt_id = str(note.mid)
        cfg = note_type_cfgs.get(nt_id)
        if not cfg:
            continue

        if _note_has_excluded_tag(note, exclude_tags):
            if config.DEBUG:
                logging.dbg("card_sorter: note excluded by tag", "nid=", note.id, "note_type=", nt_name)
            continue

        notes_processed += 1
        mode = cfg.get("mode", "by_template")
        default_deck = str(cfg.get("default_deck", "")).strip()
        by_template = cfg.get("by_template", {}) or {}
        if not isinstance(by_template, dict):
            by_template = {}

        name_by_ord = _tmpl_by_ord(mw.col, note)
        for card in note.cards():
            card_deck_name = mw.col.decks.name(card.did)
            if _deck_is_excluded(card_deck_name, exclude_decks):
                continue

            if mode == "all":
                target_deck = default_deck
            else:
                tmpl_name = name_by_ord.get(card.ord, "")
                target_deck = str(by_template.get(tmpl_name, "")).strip()

            if not target_deck:
                continue

            deck_id = _get_deck_id(target_deck, deck_id_cache, skipped_decks)
            if deck_id is None:
                continue

            if card.did != deck_id:
                cards_in_deck.setdefault(deck_id, []).append(card.id)

    cards_moved = _apply_moves(cards_in_deck)
    if config.DEBUG:
        logging.dbg(
            "card_sorter: done",
            "notes=",
            notes_processed,
            "cards_moved=",
            cards_moved,
            "decks=",
            len(cards_in_deck),
        )
    return {
        "notes_processed": notes_processed,
        "cards_moved": cards_moved,
        "decks_touched": len(cards_in_deck),
    }


def sort_note(note) -> dict[str, int]:
    config.reload_config()
    if not config.CARD_SORTER_ENABLED or not config.CARD_SORTER_RUN_ON_ADD:
        return {}
    if not mw or not mw.col:
        return {}

    note_type_cfgs = _get_note_type_cfgs()
    if not note_type_cfgs:
        return {}

    skipped_decks = _ensure_decks(_gather_target_decks(note_type_cfgs))
    return _sort_notes([note], note_type_cfgs, skipped_decks)


def sort_all(*, reason: str = "manual") -> dict[str, int]:
    config.reload_config()
    if not config.CARD_SORTER_ENABLED:
        return {}
    if reason == "sync_start" and not config.CARD_SORTER_RUN_ON_SYNC_START:
        return {}
    if reason == "sync_finish" and not config.CARD_SORTER_RUN_ON_SYNC_FINISH:
        return {}
    if reason == "manual" and not config.RUN_ON_UI:
        return {}
    if not mw or not mw.col:
        return {}

    note_type_cfgs = _get_note_type_cfgs()
    if not note_type_cfgs:
        logging.dbg("card_sorter: no note types configured")
        return {}

    skipped_decks = _ensure_decks(_gather_target_decks(note_type_cfgs))
    note_types = list(note_type_cfgs.keys())
    note_ids = note_ids_for_note_types(mw.col, note_types)
    notes = [mw.col.get_note(nid) for nid in note_ids]
    return _sort_notes(notes, note_type_cfgs, skipped_decks)

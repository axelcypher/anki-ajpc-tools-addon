from __future__ import annotations

import traceback

from anki.collection import Collection, OpChanges
from anki.errors import InvalidInput
from aqt import mw
from aqt.operations import CollectionOp
from aqt.utils import showInfo, show_info

from . import config, logging
from .card_sorter import sort_all as card_sorter_run_all
from .gates.example import example_gate_apply
from .gates.family import family_gate_apply
from .gates.kanji import kanji_gate_apply
from .taggers.jlpt import jlpt_tagger_apply


def run_gate(
    reason: str = "manual",
    *,
    run_family: bool = True,
    run_example: bool = True,
) -> None:
    config.reload_config()
    logging.dbg("reloaded config", "debug=", config.DEBUG, "run_on_sync=", config.RUN_ON_SYNC, "run_on_ui=", config.RUN_ON_UI)

    if not mw.col:
        showInfo("No collection loaded.")
        return

    if reason == "sync" and not config.RUN_ON_SYNC:
        logging.dbg("run_gate: skip (run_on_sync disabled)")
        return
    if reason == "manual" and not config.RUN_ON_UI:
        logging.dbg("run_gate: skip (run_on_ui disabled)")
        return

    logging.dbg(
        "run_gate:",
        reason,
        "run_family=",
        run_family,
        "run_example=",
        run_example,
    )

    def ui_set(label: str, value: int, maxv: int) -> None:
        def _do() -> None:
            try:
                if mw.progress.want_cancel():
                    logging.dbg("run_gate: cancelled")
                    return
                mw.progress.update(label=label, value=value, max=maxv)
            except Exception:
                return

        mw.taskman.run_on_main(_do)

    def op(col: Collection):
        undo_entry = col.add_custom_undo_entry("AJpC Gates")

        counters = {
            "cards_suspended": 0,
            "cards_unsuspended": 0,
            "notes_tagged": 0,
            "example_cards_suspended": 0,
            "example_cards_unsuspended": 0,
            "example_notes_tagged": 0,
        }

        ui_set("Gates: start...", 0, 1)

        if run_family and config.FAMILY_GATE_ENABLED:
            family_gate_apply(col, ui_set, counters)

        if run_example and config.EXAMPLE_GATE_ENABLED:
            example_gate_apply(col, ui_set, counters)

        class _Result:
            def __init__(self, changes, counts: dict[str, int]):
                self.changes = changes
                self.counts = counts

        try:
            changes = col.merge_undo_entries(undo_entry)
        except InvalidInput:
            if config.DEBUG:
                print(f"[AJpC Gates] merge_undo_entries skipped: target undo op not found (undo_entry={undo_entry})")
            changes = OpChanges()

        if changes is None:
            changes = OpChanges()

        return _Result(changes, counters)

    def on_success(result) -> None:
        if reason == "sync":
            return
        c = getattr(result, "counts", {}) or {}
        msg = (
            "Gates finished.\n"
            f"FamilyGate: unsuspended={c.get('cards_unsuspended', 0)} "
            f"suspended={c.get('cards_suspended', 0)} "
            f"tagged_notes={c.get('notes_tagged', 0)}\n"
            f"ExampleGate: unsuspended={c.get('example_cards_unsuspended', 0)} "
            f"suspended={c.get('example_cards_suspended', 0)} "
            f"tagged_notes={c.get('example_notes_tagged', 0)}"
        )
        if config.DEBUG:
            logging.dbg("RESULT", msg)
        show_info(msg)

    def on_failure(err: Exception) -> None:
        tb = "".join(traceback.format_exception(type(err), err, err.__traceback__))
        if config.DEBUG:
            logging.dbg("FAILURE", repr(err))
            logging.dbg(tb)
        showInfo("Gate run failed:\n" + tb)

    CollectionOp(parent=mw, op=op).success(on_success).failure(on_failure).run_in_background()


def run_kanji_gate(*, reason: str = "manual") -> None:
    config.reload_config()
    logging.dbg(
        "reloaded config",
        "debug=",
        config.DEBUG,
        "run_on_sync=",
        config.RUN_ON_SYNC,
        "run_on_ui=",
        config.RUN_ON_UI,
    )

    if not mw.col:
        showInfo("No collection loaded.")
        return

    if reason == "sync" and not config.RUN_ON_SYNC:
        logging.dbg("kanji_gate: skip (run_on_sync disabled)")
        return
    if reason == "manual" and not config.RUN_ON_UI:
        logging.dbg("kanji_gate: skip (run_on_ui disabled)")
        return
    if not config.KANJI_GATE_ENABLED:
        logging.dbg("kanji_gate: skip (disabled)")
        return

    def ui_set(label: str, value: int, maxv: int) -> None:
        def _do() -> None:
            try:
                if mw.progress.want_cancel():
                    logging.dbg("kanji_gate: cancelled")
                    return
                mw.progress.update(label=label, value=value, max=maxv)
            except Exception:
                return

        mw.taskman.run_on_main(_do)

    def op(col: Collection):
        undo_entry = col.add_custom_undo_entry("Kanji Gate")

        counters = {
            "vocab_kanji_cards_unsuspended": 0,
            "kanji_cards_unsuspended": 0,
            "component_cards_unsuspended": 0,
            "radical_cards_unsuspended": 0,
            "kanji_gate_cards_suspended": 0,
        }

        ui_set("KanjiGate: start...", 0, 1)
        kanji_gate_apply(col, ui_set, counters)

        class _Result:
            def __init__(self, changes, counts: dict[str, int]):
                self.changes = changes
                self.counts = counts

        try:
            changes = col.merge_undo_entries(undo_entry)
        except InvalidInput:
            if config.DEBUG:
                print(f"[KanjiGate] merge_undo_entries skipped: target undo op not found (undo_entry={undo_entry})")
            changes = OpChanges()

        if changes is None:
            changes = OpChanges()

        return _Result(changes, counters)

    def on_success(result) -> None:
        if reason == "sync":
            return
        c = getattr(result, "counts", {}) or {}
        msg = (
            "Kanji Gate finished.\n"
            f"vocab_kanjiform_unsuspended={c.get('vocab_kanji_cards_unsuspended', 0)} "
            f"kanji_unsuspended={c.get('kanji_cards_unsuspended', 0)} "
            f"components_unsuspended={c.get('component_cards_unsuspended', 0)} "
            f"radical_unsuspended={c.get('radical_cards_unsuspended', 0)} "
            f"suspended={c.get('kanji_gate_cards_suspended', 0)}"
        )
        if config.DEBUG:
            logging.dbg("RESULT", msg)
        show_info(msg)

    def on_failure(err: Exception) -> None:
        tb = "".join(traceback.format_exception(type(err), err, err.__traceback__))
        if config.DEBUG:
            logging.dbg("FAILURE", repr(err))
            logging.dbg(tb)
        showInfo("Kanji Gate failed:\n" + tb)

    CollectionOp(parent=mw, op=op).success(on_success).failure(on_failure).run_in_background()


def run_jlpt_tagger() -> None:
    config.reload_config()
    logging.dbg(
        "reloaded config",
        "debug=",
        config.DEBUG,
        "run_on_sync=",
        config.RUN_ON_SYNC,
        "run_on_ui=",
        config.RUN_ON_UI,
    )

    if not mw.col:
        showInfo("No collection loaded.")
        return

    if not config.RUN_ON_UI:
        logging.dbg("jlpt_tagger: skip (run_on_ui disabled)")
        return

    def ui_set(label: str, value: int, maxv: int) -> None:
        def _do() -> None:
            try:
                if mw.progress.want_cancel():
                    logging.dbg("jlpt_tagger: cancelled")
                    return
                mw.progress.update(label=label, value=value, max=maxv)
            except Exception:
                return

        mw.taskman.run_on_main(_do)

    def op(col: Collection):
        undo_entry = col.add_custom_undo_entry("JLPT Tagger")

        counters = {
            "notes_tagged": 0,
            "tags_added": 0,
            "jlpt_tagged": 0,
            "no_jlpt_tagged": 0,
            "common_tagged": 0,
        }

        ui_set("JLPT Tagger: start...", 0, 1)
        jlpt_tagger_apply(col, ui_set, counters)

        class _Result:
            def __init__(self, changes, counts: dict[str, int]):
                self.changes = changes
                self.counts = counts

        try:
            changes = col.merge_undo_entries(undo_entry)
        except InvalidInput:
            if config.DEBUG:
                print(f"[JLPT Tagger] merge_undo_entries skipped: target undo op not found (undo_entry={undo_entry})")
            changes = OpChanges()

        if changes is None:
            changes = OpChanges()

        return _Result(changes, counters)

    def on_success(result) -> None:
        c = getattr(result, "counts", {}) or {}
        msg = (
            "JLPT Tagger finished.\n"
            f"notes_tagged={c.get('notes_tagged', 0)} "
            f"tags_added={c.get('tags_added', 0)} "
            f"jlpt_tagged={c.get('jlpt_tagged', 0)} "
            f"no_jlpt={c.get('no_jlpt_tagged', 0)} "
            f"common={c.get('common_tagged', 0)}"
        )
        if config.DEBUG:
            logging.dbg("RESULT", msg)
        show_info(msg)

    def on_failure(err: Exception) -> None:
        tb = "".join(traceback.format_exception(type(err), err, err.__traceback__))
        if config.DEBUG:
            logging.dbg("FAILURE", repr(err))
            logging.dbg(tb)
        showInfo("JLPT Tagger failed:\n" + tb)

    CollectionOp(parent=mw, op=op).success(on_success).failure(on_failure).run_in_background()


def run_card_sorter(*, reason: str = "manual") -> None:
    config.reload_config()
    logging.dbg(
        "reloaded config",
        "debug=",
        config.DEBUG,
        "run_on_sync=",
        config.RUN_ON_SYNC,
        "run_on_ui=",
        config.RUN_ON_UI,
    )

    if not mw.col:
        showInfo("No collection loaded.")
        return

    if reason == "manual" and not config.RUN_ON_UI:
        logging.dbg("card_sorter: skip (run_on_ui disabled)")
        return

    try:
        result = card_sorter_run_all(reason=reason) or {}
    except Exception as err:
        tb = "".join(traceback.format_exception(type(err), err, err.__traceback__))
        if config.DEBUG:
            logging.dbg("CARD_SORTER_FAILURE", repr(err))
            logging.dbg(tb)
        showInfo("Card Sorter failed:\n" + tb)
        return

    if reason != "manual":
        return

    msg = (
        "Card Sorter finished.\n"
        f"notes_processed={result.get('notes_processed', 0)} "
        f"cards_moved={result.get('cards_moved', 0)} "
        f"decks_touched={result.get('decks_touched', 0)}"
    )
    if config.DEBUG:
        logging.dbg("CARD_SORTER_RESULT", msg)
    show_info(msg)

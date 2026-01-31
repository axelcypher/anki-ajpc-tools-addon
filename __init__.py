from __future__ import annotations

from aqt import gui_hooks, mw

from . import config, logging
from .card_sorter import sort_note as card_sorter_sort_note
from .runner import run_card_sorter, run_gate, run_jlpt_tagger, run_kanji_gate
from .note_linker import install_note_linker
from . import graph_api
from .ui import menu
from .ui.settings import open_settings_dialog
from .version import __version__

config.reload_config()
logging.dbg("loaded config", "debug=", config.DEBUG, "run_on_sync=", config.RUN_ON_SYNC, "run_on_ui=", config.RUN_ON_UI)


def on_sync_finished() -> None:
    run_gate("sync", run_family=True, run_example=True)


def on_sync_finished_kanji() -> None:
    run_kanji_gate(reason="sync")


def on_sync_start_card_sorter() -> None:
    run_card_sorter(reason="sync_start")


def on_sync_finish_card_sorter() -> None:
    run_card_sorter(reason="sync_finish")


def on_menu_trigger_family_only() -> None:
    run_gate("manual", run_family=True, run_example=False)


def on_menu_trigger_example_only() -> None:
    run_gate("manual", run_family=False, run_example=True)


def on_menu_trigger_kanji_only() -> None:
    run_kanji_gate(reason="manual")


def on_menu_trigger_settings() -> None:
    open_settings_dialog()


def on_menu_trigger_jlpt_tagger() -> None:
    run_jlpt_tagger()


def on_menu_trigger_card_sorter() -> None:
    run_card_sorter(reason="manual")


def _enabled_family() -> bool:
    return bool(config.RUN_ON_UI and config.FAMILY_GATE_ENABLED)


def _enabled_example() -> bool:
    return bool(config.RUN_ON_UI and config.EXAMPLE_GATE_ENABLED)


def _enabled_kanji() -> bool:
    return bool(config.RUN_ON_UI and config.KANJI_GATE_ENABLED)


def _enabled_jlpt() -> bool:
    return bool(config.RUN_ON_UI and config.JLPT_TAGGER_DECKS and config.JLPT_TAGGER_NOTE_TYPES)


def _enabled_card_sorter() -> bool:
    return bool(config.RUN_ON_UI and config.CARD_SORTER_ENABLED)


def on_add_cards(note, *args, **kwargs) -> None:
    try:
        card_sorter_sort_note(note)
    except Exception:
        if config.DEBUG:
            logging.dbg("card_sorter: add_cards hook failed")


if config.RUN_ON_SYNC:
    if mw is not None and not getattr(mw, "_familygate_sync_hook_installed", False):
        gui_hooks.sync_did_finish.append(on_sync_finished)
        gui_hooks.sync_did_finish.append(on_sync_finished_kanji)
        mw._familygate_sync_hook_installed = True

if mw is not None and not getattr(mw, "_ajpc_card_sorter_hooks_installed", False):
    gui_hooks.add_cards_did_add_note.append(on_add_cards)
    gui_hooks.sync_will_start.append(on_sync_start_card_sorter)
    gui_hooks.sync_did_finish.append(on_sync_finish_card_sorter)
    mw._ajpc_card_sorter_hooks_installed = True

install_note_linker()

def _install_graph_api() -> None:
    if mw is None:
        return
    mw._ajpc_graph_api = {
        "get_config": graph_api.get_graph_config,
        "version": __version__,
    }


menu.install_menu(
    run_items=[
        {"label": "Run Family Gate", "callback": on_menu_trigger_family_only, "enabled_fn": _enabled_family, "order": 10},
        {"label": "Run Example Gate", "callback": on_menu_trigger_example_only, "enabled_fn": _enabled_example, "order": 20},
        {"label": "Run Kanji Gate", "callback": on_menu_trigger_kanji_only, "enabled_fn": _enabled_kanji, "order": 30},
        {"label": "Run JLPT Tagger", "callback": on_menu_trigger_jlpt_tagger, "enabled_fn": _enabled_jlpt, "order": 40},
        {"label": "Run Card Sorter", "callback": on_menu_trigger_card_sorter, "enabled_fn": _enabled_card_sorter, "order": 50},
    ],
    settings_items=[
        {"label": "Open Debug Log", "callback": menu.open_debug_log, "visible_fn": lambda: bool(config.DEBUG), "order": 10},
        {"label": "Settings", "callback": on_menu_trigger_settings, "order": 20},
    ],
)

_install_graph_api()
gui_hooks.profile_did_open.append(lambda *_args, **_kw: _install_graph_api())

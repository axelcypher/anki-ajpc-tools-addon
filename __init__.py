from __future__ import annotations

from aqt import gui_hooks, mw

from . import config, logging
from .card_sorter import sort_note as card_sorter_sort_note
from .runner import run_card_sorter, run_gate, run_jlpt_tagger
from .ui import menu
from .ui.settings import open_settings_dialog
from .version import __version__

config.reload_config()
logging.dbg("loaded config", "debug=", config.DEBUG, "run_on_sync=", config.RUN_ON_SYNC, "run_on_ui=", config.RUN_ON_UI)


def on_sync_finished() -> None:
    run_gate("sync", run_family=True, run_example=True)


def on_sync_start_card_sorter() -> None:
    run_card_sorter(reason="sync_start")


def on_sync_finish_card_sorter() -> None:
    run_card_sorter(reason="sync_finish")


def on_menu_trigger_family_only() -> None:
    run_gate("manual", run_family=True, run_example=False)


def on_menu_trigger_example_only() -> None:
    run_gate("manual", run_family=False, run_example=True)


def on_menu_trigger_settings() -> None:
    open_settings_dialog()


def on_menu_trigger_jlpt_tagger() -> None:
    run_jlpt_tagger()


def on_menu_trigger_card_sorter() -> None:
    run_card_sorter(reason="manual")


def on_add_cards(note, *args, **kwargs) -> None:
    try:
        card_sorter_sort_note(note)
    except Exception:
        if config.DEBUG:
            logging.dbg("card_sorter: add_cards hook failed")


if config.RUN_ON_SYNC:
    if mw is not None and not getattr(mw, "_familygate_sync_hook_installed", False):
        gui_hooks.sync_did_finish.append(on_sync_finished)
        mw._familygate_sync_hook_installed = True

if mw is not None and not getattr(mw, "_ajpc_card_sorter_hooks_installed", False):
    gui_hooks.add_cards_did_add_note.append(on_add_cards)
    gui_hooks.sync_will_start.append(on_sync_start_card_sorter)
    gui_hooks.sync_did_finish.append(on_sync_finish_card_sorter)
    mw._ajpc_card_sorter_hooks_installed = True

menu.install_menu(
    on_menu_trigger_family_only,
    on_menu_trigger_example_only,
    on_menu_trigger_jlpt_tagger,
    on_menu_trigger_card_sorter,
    on_menu_trigger_settings,
)

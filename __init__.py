from __future__ import annotations

from aqt import mw

from . import config, logging
from .modules import discover_modules, iter_run_items, iter_settings_items
from .ui import menu

config.migrate_note_type_names_to_ids()
config.migrate_template_names_to_ords()
config.reload_config()
logging.dbg(
    "loaded config",
    "debug=",
    config.DEBUG,
    "run_on_sync=",
    config.RUN_ON_SYNC,
    "run_on_ui=",
    config.RUN_ON_UI,
)

modules = discover_modules()


for mod in modules:
    if callable(mod.init):
        try:
            mod.init()
        except Exception as exc:
            logging.dbg("module init failed", mod.id, repr(exc))

menu.install_menu(
    run_items=iter_run_items(modules),
    settings_items=iter_settings_items(modules),
)

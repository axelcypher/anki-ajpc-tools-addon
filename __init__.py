from __future__ import annotations

from aqt import gui_hooks, mw

from . import _vendor_loader
from . import config, logging
from . import config_migrations
from .core import debug as core_debug
from .core import general as core_general
from .api import graph_api, settings_api
from .modules import discover_modules, iter_run_items, iter_settings_items
from .ui import menu

_HIDE_CONFIG_FOR_ADDONS = {"ajpc-tools_dev", "ajpc-yomitran_dev"}


def _noop_addon_config_action() -> bool:
    # Prevent Anki's built-in JSON config editor for AJpC add-ons.
    return True


def _on_addons_dialog_selection(dialog, addon_meta) -> None:
    try:
        dir_name = str(getattr(addon_meta, "dir_name", "") or "")
        if dir_name in _HIDE_CONFIG_FOR_ADDONS:
            dialog.form.config.setEnabled(False)
    except Exception:
        return


def _install_addons_dialog_config_guard() -> None:
    if mw is None or not getattr(mw, "addonManager", None):
        return
    mgr = mw.addonManager
    for addon_name in _HIDE_CONFIG_FOR_ADDONS:
        try:
            mgr.setConfigAction(addon_name, _noop_addon_config_action)
        except Exception:
            continue
    if not getattr(mw, "_ajpc_addons_cfg_guard_installed", False):
        gui_hooks.addons_dialog_did_change_selected_addon.append(_on_addons_dialog_selection)
        mw._ajpc_addons_cfg_guard_installed = True


config_migrations.migrate_legacy_keys()
config_migrations.migrate_note_type_names_to_ids()
config_migrations.migrate_template_names_to_ords()
config.reload_config()
_vendor_paths = _vendor_loader.install_vendor_paths(config.ADDON_DIR)
_install_addons_dialog_config_guard()
logging.dbg(
    "loaded config",
    "debug=",
    config.DEBUG,
    "run_on_sync=",
    config.RUN_ON_SYNC,
    "run_on_ui=",
    config.RUN_ON_UI,
    "vendor_paths=",
    _vendor_paths,
    source="__init__",
)

modules = discover_modules()

settings_api.install_settings_api()
graph_api.install_graph_api()


def _on_profile_open(*_args, **_kwargs) -> None:
    settings_api.install_settings_api()
    graph_api.install_graph_api()


gui_hooks.profile_did_open.append(_on_profile_open)

try:
    core_general.init()
except Exception as exc:
    logging.error("core init failed", "general", repr(exc), source="__init__")
try:
    core_debug.init()
except Exception as exc:
    logging.error("core init failed", "debug", repr(exc), source="__init__")

for mod in modules:
    if callable(mod.init):
        try:
            mod.init()
        except Exception as exc:
            logging.error("module init failed", mod.id, repr(exc), source="__init__")

menu.install_menu(
    run_items=iter_run_items(modules),
    settings_items=(core_general.settings_items() + core_debug.settings_items() + iter_settings_items(modules)),
)

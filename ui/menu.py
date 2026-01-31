from __future__ import annotations

import json
import os

from aqt import mw
from aqt.qt import QAction, QMenu
from aqt.utils import openLink, showInfo

from .. import config, logging
from ..logging import DEBUG_LOG_PATH


def open_debug_log() -> None:
    path = DEBUG_LOG_PATH
    if not os.path.exists(path):
        showInfo("Debug log not found:\n" + path)
        return
    try:
        os.startfile(path)  # type: ignore[attr-defined]
    except Exception as exc:
        showInfo("Failed to open debug log:\n" + repr(exc))


def _notetypes_package_path() -> str:
    base = os.path.join(config.ADDON_DIR, "ajpc_notetypes")
    if os.path.exists(base):
        return base
    apkg = base + ".apkg"
    if os.path.exists(apkg):
        return apkg
    return ""


def _mark_notetypes_installed() -> None:
    cfg = config._load_config()
    if not isinstance(cfg, dict):
        cfg = {}
    config._cfg_set(cfg, "installer.notetypes_installed", True)
    try:
        with open(config.CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
    except Exception as exc:
        logging.dbg("failed to persist installer.notetypes_installed", repr(exc))
    config.reload_config()


def reset_notetypes_installed() -> None:
    cfg = config._load_config()
    if not isinstance(cfg, dict):
        cfg = {}
    config._cfg_set(cfg, "installer.notetypes_installed", False)
    try:
        with open(config.CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
    except Exception as exc:
        logging.dbg("failed to reset installer.notetypes_installed", repr(exc))
    config.reload_config()
    refresh_menu_state()


def import_notetypes() -> None:
    if mw is None or not getattr(mw, "col", None):
        showInfo("No collection loaded.")
        return
    path = _notetypes_package_path()
    if not path:
        showInfo("Install package not found:\n" + os.path.join(config.ADDON_DIR, "ajpc_notetypes(.apkg)"))
        return
    try:
        from anki.importing.apkg import AnkiPackageImporter

        imp = AnkiPackageImporter(mw.col, path)
        imp.run()
        _mark_notetypes_installed()
        showInfo("Note types installed.")
        refresh_menu_state()
    except Exception as exc:
        showInfo("Failed to import package:\n" + repr(exc))


def _open_addon_page(addon_id: str) -> None:
    openLink(f"https://ankiweb.net/shared/info/{addon_id}")


def _ensure_registry() -> dict[str, list[dict]]:
    if mw is None:
        return {}
    reg = getattr(mw, "_ajpc_menu_registry", None)
    if reg is None:
        reg = {
            "top_internal": [],
            "top_external": [],
            "run_internal": [],
            "run_external": [],
            "settings_internal": [],
            "settings_external": [],
        }
        mw._ajpc_menu_registry = reg
    return reg


def _sorted_items(items: list[dict]) -> list[dict]:
    return sorted(items, key=lambda x: (int(x.get("order", 100)), str(x.get("label", ""))))


def _apply_item_state(item: dict) -> None:
    action = item.get("qaction")
    if action is None:
        return
    enabled_fn = item.get("enabled_fn")
    visible_fn = item.get("visible_fn")
    enabled = True
    visible = True
    if item.get("kind") == "run" and not config.RUN_ON_UI:
        enabled = False
    if callable(enabled_fn):
        try:
            enabled = bool(enabled_fn())
        except Exception:
            enabled = True
    if callable(visible_fn):
        try:
            visible = bool(visible_fn())
        except Exception:
            visible = True
    action.setEnabled(enabled)
    action.setVisible(visible)


def _rebuild_menu(menu: QMenu, items: list[dict]) -> list[QAction]:
    menu.clear()
    actions: list[QAction] = []
    for item in _sorted_items(items):
        action = QAction(item.get("label", ""), mw)
        action.triggered.connect(item.get("callback"))
        item["qaction"] = action
        menu.addAction(action)
        _apply_item_state(item)
        actions.append(action)
    return actions


def _get_run_items() -> list[dict]:
    reg = _ensure_registry()
    return reg.get("run_internal", []) + reg.get("run_external", [])

def _get_top_items() -> list[dict]:
    reg = _ensure_registry()
    return reg.get("top_internal", []) + reg.get("top_external", [])


def _get_settings_items() -> list[dict]:
    reg = _ensure_registry()
    return reg.get("settings_internal", []) + reg.get("settings_external", [])


def refresh_menu_state() -> None:
    if mw is None:
        return
    reg = _ensure_registry()
    for item in reg.get("top_internal", []) + reg.get("top_external", []):
        _apply_item_state(item)
    for item in reg.get("run_internal", []) + reg.get("run_external", []):
        _apply_item_state(item)
    for item in reg.get("settings_internal", []) + reg.get("settings_external", []):
        _apply_item_state(item)
    run_all_action = getattr(mw, "_ajpc_run_all_action", None)
    if run_all_action is not None:
        run_all_action.setEnabled(bool(config.RUN_ON_UI))
    install_action = getattr(mw, "_ajpc_install_action", None)
    if install_action is not None:
        has_pkg = bool(_notetypes_package_path())
        install_action.setEnabled(has_pkg and not config.NOTETYPES_INSTALLED)
        install_action.setVisible(not config.NOTETYPES_INSTALLED)


def _run_all() -> None:
    for item in _sorted_items(_get_run_items()):
        enabled_fn = item.get("enabled_fn")
        should_run = True
        if callable(enabled_fn):
            try:
                should_run = bool(enabled_fn())
            except Exception:
                should_run = True
        if should_run:
            try:
                cb = item.get("callback")
                if callable(cb):
                    cb()
            except Exception:
                continue


def register_external_action(
    *,
    kind: str,
    label: str,
    callback,
    enabled_fn=None,
    visible_fn=None,
    order: int = 100,
) -> None:
    if mw is None:
        return
    reg = _ensure_registry()
    if kind == "top":
        bucket = "top_external"
    elif kind == "run":
        bucket = "run_external"
    else:
        bucket = "settings_external"
    items = reg.get(bucket, [])
    for it in items:
        if it.get("label") == label and it.get("callback") == callback:
            return
    items.append(
        {
            "label": label,
            "callback": callback,
            "enabled_fn": enabled_fn,
            "visible_fn": visible_fn,
            "order": order,
            "source": "external",
            "kind": kind,
        }
    )
    reg[bucket] = items

    if getattr(mw, "_ajpc_main_menu", None) is not None:
        install_menu(reg.get("run_internal", []), reg.get("settings_internal", []))


def install_menu(
    run_items: list[dict],
    settings_items: list[dict],
) -> None:
    if mw is None:
        return

    reg = _ensure_registry()
    for it in run_items:
        it["kind"] = "run"
    for it in settings_items:
        it["kind"] = "settings"
    reg["run_internal"] = list(run_items)
    reg["settings_internal"] = list(settings_items)

    menu = getattr(mw, "_ajpc_main_menu", None)
    if menu is None:
        menu = QMenu("AJpC", mw)
        mw.form.menubar.addMenu(menu)
        mw._ajpc_main_menu = menu

    menu.clear()

    run_all_action = QAction("Run All", mw)
    run_all_action.triggered.connect(_run_all)
    run_all_action.setEnabled(bool(config.RUN_ON_UI))
    menu.addAction(run_all_action)
    mw._ajpc_run_all_action = run_all_action

    top_actions: list[QAction] = []
    for item in _sorted_items(_get_top_items()):
        action = QAction(item.get("label", ""), mw)
        action.triggered.connect(item.get("callback"))
        item["qaction"] = action
        menu.addAction(action)
        _apply_item_state(item)
        top_actions.append(action)
    mw._ajpc_top_actions = top_actions

    run_menu = QMenu("Run", mw)
    settings_menu = QMenu("Settings", mw)

    mw._ajpc_run_actions = _rebuild_menu(run_menu, _get_run_items())
    mw._ajpc_settings_actions = _rebuild_menu(settings_menu, _get_settings_items())

    menu.addMenu(run_menu)
    menu.addMenu(settings_menu)

    install_action = QAction("Install Note Types", mw)
    install_action.triggered.connect(import_notetypes)
    install_action.setEnabled(bool(_notetypes_package_path()) and not config.NOTETYPES_INSTALLED)
    install_action.setVisible(not config.NOTETYPES_INSTALLED)
    menu.addAction(install_action)
    mw._ajpc_install_action = install_action

    recommended_menu = QMenu("Recommended Addons", mw)
    anki_note_linker = QAction("Anki Note Linker", mw)
    anki_note_linker.triggered.connect(lambda: _open_addon_page("1077002392"))
    recommended_menu.addAction(anki_note_linker)
    menu.addMenu(recommended_menu)
    mw._ajpc_recommended_menu = recommended_menu

    mw._ajpc_run_menu = run_menu
    mw._ajpc_settings_menu = settings_menu

    mw._ajpc_menu_api = {
        "register": register_external_action,
        "refresh": refresh_menu_state,
    }

    refresh_menu_state()

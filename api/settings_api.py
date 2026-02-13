from __future__ import annotations

from typing import Any, Callable

from aqt import mw


SETTINGS_API_VERSION = "1.0.0"
_REGISTRY_ATTR = "_ajpc_settings_registry"


def _ensure_registry() -> dict[str, dict[str, Any]]:
    if mw is None:
        return {}
    reg = getattr(mw, _REGISTRY_ATTR, None)
    if not isinstance(reg, dict):
        reg = {}
        setattr(mw, _REGISTRY_ATTR, reg)
    return reg


def register_provider(
    *,
    provider_id: str,
    label: str,
    build_settings: Callable[[Any], Any],
    order: int = 100,
) -> bool:
    if mw is None:
        return False
    pid = str(provider_id or "").strip()
    plabel = str(label or "").strip()
    if not pid or not plabel or not callable(build_settings):
        return False
    reg = _ensure_registry()
    reg[pid] = {
        "id": pid,
        "label": plabel,
        "build_settings": build_settings,
        "order": int(order),
    }
    return True


def unregister_provider(*, provider_id: str) -> bool:
    if mw is None:
        return False
    pid = str(provider_id or "").strip()
    if not pid:
        return False
    reg = _ensure_registry()
    if pid not in reg:
        return False
    del reg[pid]
    return True


def list_providers() -> list[dict[str, Any]]:
    reg = _ensure_registry()
    items = list(reg.values())
    items.sort(key=lambda x: (int(x.get("order", 100)), str(x.get("label", ""))))
    return items


def get_global_sync_enabled() -> bool:
    try:
        from .. import config

        config.reload_config()
        return bool(config.RUN_ON_SYNC)
    except Exception:
        return True


def get_global_debug_enabled() -> bool:
    try:
        from .. import config

        config.reload_config()
        return bool(config.DEBUG)
    except Exception:
        return False


def install_settings_api() -> None:
    if mw is None:
        return
    _ensure_registry()
    mw._ajpc_settings_api = {
        "version": SETTINGS_API_VERSION,
        "register": register_provider,
        "unregister": unregister_provider,
        "list": list_providers,
        "get_global_sync_enabled": get_global_sync_enabled,
        "get_global_debug_enabled": get_global_debug_enabled,
    }

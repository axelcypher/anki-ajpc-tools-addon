# ARCHITECTURE GUIDE

## Config Boundaries
- `config.py`
  - Core-only.
  - Owns config load/save helpers (`_load_config`, `_cfg_set`, `cfg_get`) and addon-global runtime flags.
  - Must not expose module-specific runtime keys.
- `config_migrations.py`
  - Owns schema/key migration logic for `config.json`.
  - Called during addon bootstrap before `config.reload_config()`.
- `core/*.py`
  - Fixed architecture components, not dynamic modules.
  - `core/general.py`: startup/runtime hooks and main Settings menu item.
  - `core/info.py`: fixed Info settings tab.
  - `core/debug.py`: debug runtime hooks and debug menu item.
- `modules/*.py`
  - Plug-and-play feature modules only.
  - Must expose `MODULE = ModuleSpec(...)` for dynamic discovery.
  - Own module-local config proxy/runtime keys.
  - Read module-specific settings from config JSON paths.

## Settings Boundaries
- `ui/settings.py` always builds core tabs first in fixed order:
  1. `General` (from `core/general.py`)
  2. `Info` (from `core/info.py`)
  3. `Debug` (from `core/debug.py`, visible only when `debug.enabled`)
- After fixed core tabs, dynamically discovered module tabs are appended.

## Menu Boundaries
- `__init__.py` installs top-level settings items as:
  1. fixed core settings items (`core/general.py`, `core/debug.py`)
  2. dynamic module settings items (`modules/*` via `iter_settings_items`)

## Bootstrap Flow
1. `config_migrations.migrate_legacy_keys()`
2. `config_migrations.migrate_note_type_names_to_ids()`
3. `config_migrations.migrate_template_names_to_ords()`
4. `config.reload_config()`
5. Core hooks init (`core_general.init()`, `core_debug.init()`)
6. Dynamic module init (`discover_modules()` loop)

## Runtime Guardrails
- Config files must be UTF-8 without BOM.
- Keep migration behavior backward compatible for old config key shapes.

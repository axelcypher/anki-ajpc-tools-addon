# ARCHITECTURE GUIDE

## Config Boundaries
- `config.py`
  - Core-only.
  - Owns config load/save helpers (`_load_config`, `_cfg_set`, `cfg_get`) and addon-global runtime flags.
  - Must not expose module-specific runtime keys.
- `config_migrations.py`
  - Owns schema/key migration logic for `config.json`.
  - Called during addon bootstrap before `config.reload_config()`.
- `modules/*.py`
  - Own module-local config proxy/runtime keys.
  - Read module-specific settings from config JSON paths.

## Bootstrap Flow
1. `config_migrations.migrate_legacy_keys()`
2. `config_migrations.migrate_note_type_names_to_ids()`
3. `config_migrations.migrate_template_names_to_ords()`
4. `config.reload_config()`

## Runtime Guardrails
- Config files must be UTF-8 without BOM.
- Keep migration behavior backward compatible for old config key shapes.

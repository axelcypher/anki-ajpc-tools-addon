# REFERENCE

## Current Status
- 2026-02-16 19:32:00: Root config architecture split is active.
- `config.py` is core-only and module-agnostic.
- `config_migrations.py` owns config schema/key migrations.
- Module-specific runtime config remains in `modules/*.py`.
- 2026-02-16 19:34:30: `debug`, `general`, and `info` were moved from dynamic `modules/` to fixed `core/` architecture components.
- Dynamic module discovery now excludes those concerns by design (only plug-and-play feature modules stay in `modules/*.py`).

## Debug Clarification Status
- 2026-02-16 19:34:30: No open debug investigation in this change set.
- Debug UI/runtime is now a fixed core component (`core/debug.py`), not a pluggable module.

## Notes
- Companion compatibility target: `ajpc-tools-graph_dev` remains unchanged by this config split.

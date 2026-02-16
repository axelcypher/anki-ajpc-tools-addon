# REFERENCE

## Current Status
- 2026-02-16 19:32:00: Root config architecture split is active.
- `config.py` is core-only and module-agnostic.
- `config_migrations.py` owns config schema/key migrations.
- Module-specific runtime config remains in `modules/*.py`.

## Debug Clarification Status
- 2026-02-16 19:32:00: No open debug investigation in this change set.

## Notes
- Companion compatibility target: `ajpc-tools-graph_dev` remains unchanged by this config split.

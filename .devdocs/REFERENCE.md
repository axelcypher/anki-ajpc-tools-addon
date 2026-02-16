# REFERENCE

## Current Status
- 2026-02-16 19:32:00: Root config architecture split is active.
- `config.py` is core-only and module-agnostic.
- `config_migrations.py` owns config schema/key migrations.
- Module-specific runtime config remains in `modules/*.py`.
- 2026-02-16 19:34:30: `debug`, `general`, and `info` were moved from dynamic `modules/` to fixed `core/` architecture components.
- Dynamic module discovery now excludes those concerns by design (only plug-and-play feature modules stay in `modules/*.py`).
- 2026-02-16 20:49:00: Link-Core ownership refactor stage applied.
  - Helpers moved under `modules/_link_core/*` (`renderer`, `note_editor`, `force_graph_view`, `dep_tree_view`, `browser_graph`).
  - Browser graph panel init now runs through `modules/link_core.py`; `modules/browser_graph.py` is no longer a dynamic module.
- 2026-02-16 20:49:00: Family module hard-rename active.
  - `family_gate` -> `family_priority` in module id, provider id, and config namespace.
  - Config hardcut: runtime reads `family_priority.*` only (no legacy `family_gate.*` reads).
- 2026-02-16 20:49:00: Main-addon editor API hardcut applied.
  - `_ajpc_note_editor_api` removed.
  - Editor fallback keys removed from `_ajpc_graph_api`.
- 2026-02-16 20:49:00: Restart extracted from debug core into `modules/restart.py`; top-toolbar restart icon is module-owned and always available when module is active.
- 2026-02-16 21:08:00: Restart helper folder moved from addon root `restart_helper/` into module scope `modules/restart_helper/`; runtime path in `modules/restart.py` was updated accordingly.
- 2026-02-16 21:17:00: Example Unlocker mapping diagnostics are now reason-grouped in logs (`reason=count`) with `nid:reason` examples for faster root-cause triage.

## Debug Clarification Status
- 2026-02-16 19:34:30: No open debug investigation in this change set.
- Debug UI/runtime is now a fixed core component (`core/debug.py`), not a pluggable module.
- 2026-02-16 20:49:00: Debug no longer owns restart runtime or restart visibility settings.

## Notes
- Companion compatibility target: `ajpc-tools-graph_dev` remains unchanged by this config split.

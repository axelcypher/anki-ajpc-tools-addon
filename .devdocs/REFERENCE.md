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
- 2026-02-16 21:33:00: Example Unlocker settings now include NID-based mapping debug lookup (popup output includes detected lemma + lookup term + Browser filter for related notes).
- 2026-02-16 21:40:00: Family Priority family-id search logging now distinguishes fallback stages: `WARN` for failed single attempts, `ERROR` only when all query variants fail.
- 2026-02-16 21:55:00: Example Unlocker mapping now resolves up to 2 target cards per example; unlock requires threshold pass on all resolved targets. `data-lemma` template marker is preferred when `cloze == lemma`.
- 2026-02-16 22:08:00: Example Unlocker lemma path now includes a single-kanji guard (`single_kanji_surface_guard`) to avoid semantic remaps between distinct single CJK ideographs.
- 2026-02-16 22:16:00: Example Unlocker ambiguous-lemma handling now performs a literal cloze-to-key disambiguation pass (`key_literal`) before returning `ambiguous_lemma`.
- 2026-02-16 22:26:00: Example Unlocker now normalizes furigana parser spacing before kanji/`[` on both cloze extraction and vocab-key indexing paths to avoid spacing-induced first-token truncation.
- 2026-02-16 22:56:54: Example Unlocker honorific handling was narrowed to honorific-equivalent lemma/cloze reconciliation (`御X` <-> `おX`/`ごX`) with cloze-key + literal disambiguation; broad variant fallback was removed.
- 2026-02-16 23:23:43: Example Unlocker now includes a normalized reading fallback (`VocabReading` index) for unresolved lemma/canonicalization cases; fallback selection is guarded by key/literal checks and may report `ambiguous_reading:<reading>`.
- 2026-02-16 23:33:13: Example Unlocker now adds a strict `suru`-verb fallback for ambiguous-tokenization forms (`...します` -> `...する`), and only accepts candidates explicitly marked as `suru` verbs.

## Debug Clarification Status
- 2026-02-16 19:34:30: No open debug investigation in this change set.
- Debug UI/runtime is now a fixed core component (`core/debug.py`), not a pluggable module.
- 2026-02-16 20:49:00: Debug no longer owns restart runtime or restart visibility settings.

## Notes
- Companion compatibility target: `ajpc-tools-graph_dev` remains unchanged by this config split.

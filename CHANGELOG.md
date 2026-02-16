# Changelog

## Unreleased - 2026-02-16

### Major Updates
- Two-stage refactor started (main addon stage complete):
  - Link-Core helper ownership moved into `modules/_link_core/*`.
  - `family_gate` hard-renamed to `family_priority` (module id/provider id/config namespace).
  - Restart extracted into dedicated `modules/restart.py` module.
  - Main-addon editor bridge API hardcut (`_ajpc_note_editor_api` removed, editor keys removed from `_ajpc_graph_api`).

### Minor Updates
- Refactored root `config.py` to module-agnostic core runtime/config handling only.
- Extracted config schema migrations into dedicated `config_migrations.py`.
- Added migration validation script `scripts/check_config_migrations.py`.
- Added documentation section `Configuration Architecture` to `README.md`.
- Promoted `general`, `info`, and `debug` from dynamic `modules/` entries to fixed architecture components in `core/`.
- Browser graph helper initialization is now performed by `modules/link_core.py` (`install_browser_graph()`), while keeping List/Graph/Deps editor buttons active.
- Added neutral deck-stats registry (`modules/_widgets/deck_stats_registry.py`) and switched widget providers to module registration.
- Added Example Unlocker mapping-debug lookup in settings (`NID + Search`) with result popup showing detected lemma/lookup term and Browser filter action for related notes.

### Fixes
- Removed UTF-8 BOM from `config.py` and `config_migrations.py` to comply with Anki config-loader guardrail.
- Removed obsolete debug setting `debug.show_restart_button`.
- Removed tracked restart build artifacts from version control and ignored `modules/restart_helper/build/`.
- Fixed Family Priority family lookup queries for family IDs containing spaces by using quoted regex query path with compatibility fallback.
- Tightened Family Priority family lookup logging: single query-attempt failures now log `WARN`, and only full fallback failure logs `ERROR`.
- Improved Example Unlocker mapping diagnostics: warning/info summaries now include reason buckets and `nid:reason` examples.
- Example Unlocker target-card resolution now supports up to 2 matched cards and requires threshold pass on all matched targets; added `data-lemma` marker preference for `cloze == lemma` cases.
- Added single-kanji lemma guard in Example Unlocker to prevent semantic remaps like `歳 -> 年` from overriding the original surface lookup term.
- Added Example Unlocker literal key disambiguation for ambiguous lemma matches (uses raw cloze text, e.g. `五[ご]` vs `五[いつ]`, before failing with `ambiguous_lemma`).
- Normalized furigana parser spacing before kanji on both cloze and vocab-key paths in Example Unlocker to avoid false first-token truncation (e.g. `お 洒落[...]` -> `お洒落[...]` for matching).
- Replaced broad honorific variant fallback in Example Unlocker with narrow honorific-equivalence handling (`御X` <-> `おX`/`ごX`) plus cloze-literal disambiguation to avoid false ambiguous matches.

## 1.0.0-beta.1 - 2026-02-14

### Major Updates
- None.

### Minor Updates
- Added `Preload graph on startup` in the General settings tab.
- The preload option is only shown when `ajpc-tools-graph_dev` is installed.
- Added `Show in AJpC Graph` to Browser Link-Core sidepanel context menus:
  - Linked-note list
  - Mini graph
  - Dependency tree
- Reworked Mass Linker rules to dynamic rule tabs (add/remove freely) instead of note-type generated tabs.
- Added Mass Linker advanced modes:
  - `Basic` (legacy tag-based note links)
  - `Advanced: Tag source` (tag base + configurable selector separator)
  - `Advanced: NoteType source` (with `target_mode = note|card`)
- Added per-rule Mass Linker grouped rendering with configurable group name.
- Added Graph API endpoint `get_link_provider_edges` (alias `get_provider_link_edges`) to return provider-resolved link edges for companion graph layer building.
- Optimized Graph provider-edge collection: request-local provider caches, provider target-note-type scope prefilter, provider-side gating, and timing counters for easier bottleneck tracing.

### Fixes
- Standardized graph handoff context action text to English (`Show in AJpC Graph`).
- Added clickable rendering/handling for `cid...` links (preview/editor commands for card-target links).

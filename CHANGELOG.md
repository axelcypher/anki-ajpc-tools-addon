# Changelog

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

# STYLING GUIDE

## Scope
- This document tracks CSS-relevant UI elements for `ajpc-tools_dev`.
- Update when UI structure/classes/ids or style behavior changes.

## Current Change Context
- 2026-02-16 19:32:30: No UI/CSS changes in this config-architecture change set.
- 2026-02-16 19:35:11: `debug/general/info` moved from `modules/` to `core/`; no CSS classes/ids/layout styling contracts changed.
- 2026-02-16 20:49:00: Link-Core helper relocation (`modules/_link_core/*`), Family Priority rename, and Restart module extraction changed runtime ownership only; no CSS selector or stylesheet contract changes.
- 2026-02-16 21:08:00: restart helper assets moved to `modules/restart_helper/*`; no CSS classes/ids/layout styling contracts changed.
- 2026-02-16 21:17:00: Example Unlocker mapping diagnostics were expanded (runtime/logging only); no CSS classes/ids/layout styling contracts changed.
- 2026-02-16 21:33:00: Example Unlocker settings received a new Qt row (`Mapping debug`) with inline NID input + Search button and popup actions; this is Qt-widget layout only, no CSS selector/id contract changes.
- 2026-02-16 21:40:00: Family Priority fallback logging behavior adjusted (warn-vs-error split); no CSS classes/ids/layout styling contracts changed.
- 2026-02-16 21:55:00: Example Unlocker target-card resolution was updated for up-to-2 targets plus `data-lemma` preference; no CSS classes/ids/layout styling contracts changed.
- 2026-02-16 22:08:00: Example Unlocker single-kanji lemma guard added (runtime matching only); no CSS classes/ids/layout styling contracts changed.
- 2026-02-16 22:16:00: Example Unlocker literal cloze-key disambiguation added (runtime matching only); no CSS classes/ids/layout styling contracts changed.
- 2026-02-16 22:26:00: Example Unlocker furigana-spacing normalization added in matching pipeline (runtime only); no CSS classes/ids/layout styling contracts changed.
- 2026-02-16 22:56:54: Example Unlocker honorific matching was narrowed to honorific-equivalent lemma/cloze reconciliation plus literal disambiguation (runtime only); no CSS classes/ids/layout styling contracts changed.
- 2026-02-16 23:23:43: Example Unlocker reading-index fallback (`VocabReading` normalized) added in matching pipeline (runtime only); no CSS classes/ids/layout styling contracts changed.

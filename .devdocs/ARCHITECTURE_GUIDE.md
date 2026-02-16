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
  - `browser_graph` is no longer a dynamic module; it is owned by `modules/link_core.py` via `modules/_link_core/browser_graph.py`.
- `modules/_link_core/*.py`
  - Link-Core-owned helper package.
  - Hosts renderer/editor/browser sidepanel helpers:
    - `renderer.py`
    - `note_editor.py`
    - `force_graph_view.py`
    - `dep_tree_view.py`
    - `browser_graph.py`
- `modules/restart.py`
  - Dedicated Restart module with top-toolbar action lifecycle.
  - Restart is no longer part of `core/debug.py`.
  - Restart helper runtime artifacts are colocated at `modules/restart_helper/*`.
- `modules/_widgets/deck_stats_registry.py`
  - Neutral deck-stats provider registry.
  - Feature modules register provider callbacks; renderer module (`onigiri_widgets`) stays decoupled from module internals.

## Settings Boundaries
- `ui/settings.py` always builds core tabs first in fixed order:
  1. `General` (from `core/general.py`)
  2. `Info` (from `core/info.py`)
  3. `Debug` (from `core/debug.py`, visible only when `debug.enabled`)
- After fixed core tabs, dynamically discovered module tabs are appended.
- `modules/example_gate.py` owns an inline Settings-side debug lookup UI (`Mapping debug`) for single-note mapping diagnostics. It must stay module-local and reuse the same mapping pipeline as runtime apply logic.

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

## API Boundaries
- Removed public editor API endpoint `_ajpc_note_editor_api`.
- `_ajpc_graph_api` no longer exposes editor fallback functions; graph/editor opening is handled by module-local runtime paths.
- Family provider id was hard-cut from `family_gate` to `family_priority` for Link Core provider contracts.

## Runtime Guardrails
- Config files must be UTF-8 without BOM.
- Keep migration behavior backward compatible for old config key shapes.
- Example Unlocker mapping diagnostics must log grouped reason counts plus compact `nid:reason` samples for warn/info mapping summaries.
- Mapping debug lookups should include the detected lemma and the concrete lookup term used for matching to avoid hidden matching-state ambiguity.
- Family Priority fallback searches should only emit hard `ERROR` when all query variants fail; individual variant failures stay on `WARN`.
- Example Unlocker target resolution supports one or two target cards; if two targets are resolved, unlock gating must require both stabilities to pass threshold. `data-lemma` is the preferred selector when `cloze == lemma`.
- Example Unlocker lemma normalization must preserve single-kanji surfaces when lemma resolves to a different single CJK ideograph (single-kanji remap guard).
- Example Unlocker ambiguous-lemma path should attempt literal cloze-vs-key disambiguation (`key_literal`) before failing hard, to preserve furigana-distinguished homographs.
- Example Unlocker must normalize parser-required whitespace before kanji/`[` consistently in both cloze and vocab-key normalization paths before applying token/lemma matching.
- Example Unlocker honorific handling must be narrow: treat only honorific-equivalent lemma/cloze pairs (`御X` <-> `おX`/`ごX`) as equivalent, then run cloze-key lookup with literal disambiguation before surface fallback.

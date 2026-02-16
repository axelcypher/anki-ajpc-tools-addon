# Logging Call Map

This file lists only module functions that call logging paths, and which level they emit.

## `modules/card_sorter.py`
- `dbg` -> `TRACE`
- `log_info` -> `INFO`
- `log_warn` -> `WARN`
- `log_error` -> `ERROR`
- `note_ids_for_note_types` -> `TRACE`, `WARN`
- `_ensure_decks` -> `WARN`
- `_sort_notes` -> `TRACE`
- `sort_all` -> `WARN`
- `run_card_sorter` -> `TRACE`, `INFO`, `ERROR`
- `_init` -> `WARN`

## `modules/card_stages.py`
- `dbg` -> `TRACE`
- `log_info` -> `INFO`
- `log_warn` -> `WARN`
- `log_error` -> `ERROR`
- `_verify_suspended` -> `TRACE`
- `card_stages_apply` -> `TRACE`, `INFO`, `WARN`
- `run_card_stages` -> `TRACE`, `INFO`, `WARN`, `ERROR`

## `modules/example_gate.py`
- `dbg` -> `TRACE`
- `log_info` -> `INFO`
- `log_warn` -> `WARN`
- `_verify_suspended` -> `TRACE`
- `_fugashi_tagger` -> `INFO`, `WARN`
- `note_ids_for_deck` -> `TRACE`
- `example_gate_apply` -> `TRACE`, `INFO`, `WARN`
- `run_example_gate` -> `TRACE`, `INFO`, `WARN`, `ERROR`

## `modules/family_priority.py`
- `dbg` -> `TRACE`
- `log_info` -> `INFO`
- `log_warn` -> `WARN`
- `log_error` -> `ERROR`
- `_verify_suspended` -> `TRACE`
- `note_ids_for_note_types` -> `TRACE`
- `_family_find_nids` -> `TRACE`, `WARN`
- `family_priority_apply` -> `TRACE`, `INFO`, `WARN`
- `run_family_priority` -> `TRACE`, `INFO`, `WARN`, `ERROR`

## `modules/kanji_gate.py`
- `dbg` -> `TRACE`
- `log_info` -> `INFO`
- `log_warn` -> `WARN`
- `log_error` -> `ERROR`
- `_verify_suspended` -> `TRACE`
- `note_ids_for_note_types` -> `TRACE`
- `kanji_gate_apply` -> `TRACE`, `INFO`, `WARN`
- `run_kanji_gate` -> `TRACE`, `INFO`, `WARN`, `ERROR`

## `modules/mass_linker.py`
- `dbg` -> `TRACE`
- `log_info` -> `INFO`
- `log_warn` -> `WARN`
- `log_error` -> `ERROR`
- `_dbg` -> `TRACE`
- `_copy_note_link_for_browser` -> `WARN`
- `_link_refs_for_tag` -> `WARN`

## `core/debug.py`
- no logging calls

## `core/info.py`
- `build_settings` -> `WARN`

## `ui/settings.py`
- `open_settings_dialog` -> `DEBUG`, `WARN`, `ERROR`

## `ui/menu.py`
- `_mark_notetypes_installed` -> `WARN`
- `reset_notetypes_installed` -> `WARN`

## `__init__.py`
- module init block -> `DEBUG`
- core init block (`core_general.init`, `core_debug.init`) -> `ERROR`
- module init loop (`for mod in modules`) -> `ERROR`

## `modules/restart.py`
- `_build_target_cmd` -> `DEBUG`
- `_start_restart_helper` -> `DEBUG`, `WARN`, `ERROR`
- `_delayed_restart_anki` -> `DEBUG`, `WARN`, `ERROR`

## `modules/_link_core/browser_graph.py`
- `_show_note_in_ajpc_graph` -> `DEBUG`, `WARN`
- `_focus_companion_graph_note` -> `DEBUG`, `WARN`

## `core/general.py`
- `_try_preload_graph_once` -> `DEBUG`, `INFO`, `WARN`

## `modules/link_core.py`
- no logging calls

## `modules/onigiri_widgets.py`
- no logging calls

## `modules/_link_core/force_graph_view.py`
- no logging calls

## `modules/_link_core/renderer.py`
- no logging calls

## `modules/_link_core/note_editor.py`
- no logging calls

## `modules/_link_core/dep_tree_view.py`
- no logging calls

## `modules/__init__.py`
- no logging calls

## `ui/settings_common.py`
- no logging calls

## `ui/__init__.py`
- no logging calls

## `api/graph_api.py`
- `get_link_provider_edges` -> `DEBUG` (provider/source resolution and timing counters)

## `api/settings_api.py`
- no logging calls

## `api/__init__.py`
- no logging calls

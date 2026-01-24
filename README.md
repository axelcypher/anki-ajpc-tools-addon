# Anki Add-on: Family Gate Suspension

This add-on provides gating, tagging, and sorting tools for Anki study decks.

Features
- Family Gate: gate card availability by family groups and stage stability thresholds.
- Example Gate: unlock example cards based on matching vocab progress.
- JLPT Tagger: apply JLPT and common tags to notes.
- Card Sorter: move cards to decks by note type and template.

Usage
- Open Tools -> AJpC.
- Run "Run Family Gate", "Run Example Gate", "Run JLPT Tagger", or "Run Card Sorter".
- Auto-run behavior is controlled by `config.json` (sync hooks and add-note hooks).

Configuration
- Edit `config.json`.
- `family_gate.note_types` defines stages, template names, and thresholds per note type.
- `example_gate` links vocab and example decks and fields.
- `jlpt_tagger` limits decks and note types and maps tags.
- `card_sorter` defines deck routing per note type and template.

Development
- Location: `addons21/1000000000`
- Enable debug in `config.json` to write `ajpc_debug.log`.

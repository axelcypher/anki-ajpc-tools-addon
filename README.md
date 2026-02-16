# AJpC Add-on Documentation (Card Stages, Family Priority, Example Unlocker, Kanji Unlocker, Card Sorter, Mass Linker & Note Linker)

## What this add-on does

This add-on helps you control *when* Anki cards become available, so you can learn in a structured order:

1. **Card Stages**
   Keeps "advanced" cards hidden until the "base" cards are learned well enough.
2. **Family Priority**
   Keeps related notes like compound words hidden until the "base" notes are learned well enough.
3. **Example Unlocker**
   Unlocks example sentence cards only after the related vocabulary is ready.
4. **Kanji Unlocker**
   Unlocks kanji/components based on vocab thresholds and behavior mode.
5. **Card Sorter**
   Moves cards into preconfigured decks based on note type and card template.
6. **Link Core**
   Handles note/card links and provides a useful link sidepanel for the editor.
7. **Mass Linker**
   Auto-generate note links based on tags.

This add-on relies primarily on **FSRS** stability ratings, so you must use FSRS to use it!

I recommend using it with its companion add-on: [anki-ajpc-tools-graph-addon](https://github.com/axelcypher/anki-ajpc-tools-graph-addon). It adds a nice, force-graph-based GUI for connecting notes and editing relationships between them. (I highly recommend it, because I may have overengineered this add-on to the point where even I can't fully comprehend what connects to what without proper visualization.)

Note types are referenced internally by their **model ID** (not the visible name). The settings UI shows names, so you only need to care about IDs if you edit the JSON config manually.

---

## Why->

As you can probably guess, I created this add-on mainly to study Japanese. 
However, **you can use a big portion of it with any learning material you want**.

Although parts of this add-on's functionality are heavily inspired by other add-ons **(more in the "Credits" section)**, those add-ons caused issues for me or didn't had specific features I needed. Also, some use plain JSON for their configs, which I strongly dislike.

So the only viable conclusion was: *to write my own version!*

I may extend the functionality over time. ~~Also, if you want to use it for Japanese, I suggest you check out my note templates,~~ 
~~which I built the gate logic around.~~ (Coming soon -- I need to test them a bit more to make sure everything works correctly)

---

## Card Stages

### Goal

Only show the next set of cards when you have learned the prerequisite cards to a certain quality level.

### Stages: learning steps inside one note

For each note type, you define **Stages**:

* **Stage 0** is the "foundation stage" (usually the main recognition/production cards).
* Later stages are "extra" cards (conjugations, variations, additional/extended versions, etc.).

Each stage contains:

* Which **cards** belong to it (by template name)
* A **threshold** (how well you must know those cards before the stage is considered "ready")

### What "threshold" means

Threshold is measured in **FSRS Stability**, and the values are treated as **days**.

* Higher stability means Anki expects you to remember it longer.
* A stage becomes "ready" when the cards in that stage reach the configured stability requirement (in days).

### How unlocking works inside a note (stage chain)

Within a single note:

* If the gate is open for that note, **Stage 0** cards are allowed (unsuspended).
* **Stage 1** cards are allowed only if **Stage 0 is ready**.
* **Stage 2** cards are allowed only if **Stage 1 is ready**, and so on.

So within one note, stages unlock like a chain.

---

## Family Priority (learning order between related notes)

### Why priority exists

Sometimes you want multiple related notes, but not all at once. Each note can contain one or more entries in the 
**FamilyID**(or however you want to name it) field.

* Notes that share the same FamilyID entry are treated as related.
* This relation is used to control availability across related notes.

**Priority** is how you enforce that order **between notes** (for example: base words first, then a pattern/suffix, then a compound).

### How it behaves

You attach a "priority number" to a FamilyID entry inside the FamilyID field:

* **Priority 0** = available first
* **Priority 1** = unlocks only after all priority 0 notes in that family are **Stage 0 ready**
* **Priority 2** = unlocks only after all priority 1 notes are **Stage 0 ready**
  ...and so on.

Family IDs can contain spaces (for example `kita guchi`) and are handled as normal IDs.
Family IDs with regex-relevant characters (for example `[` or `]`) are queried via
fallback search variants; single-attempt failures are logged as warn attempts, and only
when all variants fail the module logs a hard error.

If a note contains multiple family links, **all of them must be satisfied** before the note can unlock.

### Example: deguchi / kita / ~guchi / kita-guchi

Setup:

* **kita** has: kita at priority 0 (kita or kita@0)
* **deguchi** has: deguchi at priority 0 (deguchi or deguchi@0)
* **~guchi** has: deguchi at priority 1 (deguchi@1)
* **kita-guchi** has: kita at priority 1 and deguchi at priority 2 (kita@1; deguchi@2)

Learning order:

1. **deguchi + kita** (priority 0 -> available first)
2. **~guchi** (waits until deguchi is Stage 0 ready)
3. **kita-guchi** (waits until kita is Stage 0 ready AND deguchi is Stage 1 ready)

This ensures the compound appears only after its components (and the pattern) are established.

---

## Example Unlocker

### Goal

Example sentences should appear only when the vocab is ready.

### How matching works

* You have two note types:

  * a **vocab note**
  * an **example note**
* Both vocab notes and example notes contain a key field (e.g., `Vocab`).
* The add-on uses an **exact match**:

  * The example note's key field must be **identical** to the vocab note's key field.

### When an example card unlocks

An example card is allowed only if:

* the matching vocab entry exists (exact key match), and
* the vocab entry is ready according to the configured stability requirement (days)

(There is no optional stage selection via suffix; example unlocking is driven by stability readiness.)

If mapping cannot be resolved, the module logs grouped diagnostics with reason keys
(for example `ambiguous_target_card`, `ambiguous_lemma`, `force_nid_not_found`) and
example note IDs in `nid:reason` format.

Target-card resolution now allows up to **2** matched cards for one example. In that case,
unlocking requires that **both** target cards meet the configured threshold. For `cloze == lemma`,
cards marked with `data-lemma` are preferred for this resolution path.
Additionally, single-kanji cloze surfaces are protected from semantic lemma remaps
(for example `歳 -> 年`) by falling back to the original surface as lookup term.
When multiple lemma candidates exist, the module now tries a literal cloze-key
disambiguation first (for example `五[ご]` vs `五[いつ]`) before emitting `ambiguous_lemma`.
Spacing inserted before kanji for furigana parsing is normalized away on both sides
(cloze extraction and vocab key indexing) before matching.

### Mapping debug lookup (Settings)

In the **Example Unlocker** settings tab, there is a dedicated **Mapping debug** row:

* Enter an **example note NID**
* Click **Search**
* A popup shows:
  * cloze surface
  * detected lemma
  * the exact lookup term used for matching
  * match reason and target note/card IDs
* From the popup, **Filter Notes** opens the Browser with related note IDs (example + mapping candidates).

---

## Kanji Unlocker

### Goal

Unlock kanji, components, and radicals based on vocab templates and FSRS thresholds.

### How it works

* Configure one or more **vocab note types** with:
  * a **furigana field**
  * **base templates** (Grundform)
  * **kanjiform templates**
  * a **base threshold** (FSRS stability)
* The add-on removes anything inside `[...]` and extracts kanji characters.
* You choose one behavior mode:
  * **Kanji Only**: base threshold unlocks kanji + vocab kanjiform cards.
  * **Kanji then Components**: base threshold unlocks kanji + kanjiform; once kanji reaches its threshold, components + radicals unlock.
  * **Components then Kanji**: base threshold unlocks components first; when all components reach their threshold, the parent kanji (and kanjiform) unlocks. Radicals are synced but do not gate.
  * **Kanji and Components**: base threshold unlocks kanji, components, and radicals together.
* Stability aggregation can be set to min/max/avg.

Tip: use a dedicated base template if you want a clean, explicit unlock trigger.

---

## Card Sorter

### Goal

Automatically move cards into the correct deck so your study order stays clean and predictable.

### How it works

* You pick one or more **note types**.
* For each note type, you either:

  * send **all cards** to one deck, or
  * map **each card template** to a specific deck.
* Excluded decks and tags are ignored.
* The sorter can run on add note, on sync, or manually from the AJpC menu.

### Example

Note type: **JP Vocab**

* Template "Front -> Back" -> deck "Japanese::Vocab"
* Template "Back -> Front" -> deck "Japanese::Vocab::Reverse"

Result: each card goes to the exact deck you want without manual dragging.

---

## Mass Linker

### Goal

Mass Linker provides specific cards with links based upon tags automatically. 

### How it works

* Each note type that wants to utilize this feature **needs a field "LinkedNotes"** in the card template.
* Mass links are inserted into the **parent element of the "LinkedNotes" field** in the card template.
  * Example: `<div id="links-wrapper">{{LinkedNotes}}</div>` -> links are injected into `#links-wrapper` even if "LinkedNotes" is empty.
* Rules are now configured as **dynamic tabs** (add/remove freely), not generated from General note-type selection.
* Every rule tab supports:
  * **Group name** (links are rendered grouped like Family links)
  * **Mode**:
    * `Basic`: tag-based `nid` links (legacy behavior)
    * `Advanced: Tag source`: tag-base + free selector separator (`;`, `--`, `::`, ...)
    * `Advanced: NoteType source`: source note type with `target_mode = note|card`
  * **Targeting**:
    * optional target note types
    * optional target template ords
    * condition blocks with `AND|OR|ANY` and `NOT`
  * **Source conditions** with the same condition logic
* In `target_mode = card`, links are generated as `cid...` and rendered as clickable links.

---

## Usage

In Anki you have an AJpC menu with:

* **Run All** (runs all enabled modules)
* **Run -> Run Family Priority**
* **Run -> Run Example Unlocker**
* **Run -> Run Kanji Unlocker**
* **Run -> Run Card Sorter**
* Top toolbar includes a **Restart** icon (`⟳`) managed by the dedicated `restart` module.

All settings are configured via the Add-on Settings UI:

* **Settings -> Main Settings**
* Field explanations are available via **hover tooltips on labels**.
* Link rendering in `link_core` is always handled directly by AJpC (`convert_links(...)`).
* General tab includes **Preload graph on startup** (shown only when AJpC Tools Graph Companion is installed) to warm-load the graph window in background.
* Browser Link-Core sidepanel context menus (list, mini-graph, dep-tree) include **Show in AJpC Graph** for direct handoff to the companion graph.

Note: You should always ***back up your collection before using add-ons.*** While this add-on can't delete cards, it uses tags for some functionality, 
and ***misconfiguration could scramble up your decks!***

---

## Companion Graph API

For AJpC Tools Graph, the graph API now exposes provider-resolved link edges:

- `get_link_provider_edges(...)` (alias: `get_provider_link_edges(...)`)
  - Executes registered Link Core providers directly.
  - Returns a normalized `providers` list and resolved `edges` list.
  - Edge rows include `provider_id`, `source_nid`, `target_kind`, `target_id`, and resolved `target_nid`.
  - Family provider edges can be excluded via `include_family=False` (default), so graph-family rendering stays on the graph side.

This avoids duplicating provider/config parsing in the companion graph add-on when rule structures change.

Editor fallback APIs were removed from the graph bridge surface:

- `_ajpc_note_editor_api` is no longer published.
- `_ajpc_graph_api` no longer includes editor-open helper functions.

---

## Configuration Architecture

The add-on uses a split config architecture:

- `config.py` is module-agnostic core infrastructure (load/save helpers, global runtime toggles, debug flags).
- `config_migrations.py` owns schema/key migrations for `config.json`.
- Fixed architecture components live in `core/*.py` (`general`, `info`, `debug`) and are not part of dynamic module discovery.
- Feature modules in `modules/*.py` own their own runtime config proxies and module-specific keys.
- Link-Core-owned helpers live in `modules/_link_core/*` and are initialized through `modules/link_core.py`.
- Restart helper runtime assets are colocated under `modules/restart_helper/*` and consumed by `modules/restart.py`.
- Deck progress widgets use a neutral provider registry (`modules/_widgets/deck_stats_registry.py`) so gate modules register stats without direct cross-imports.
- Family module namespace is hard-cut to `family_priority.*` (legacy `family_gate.*` keys are not read).

This keeps modules plug-and-play and avoids cross-module coupling through a central config singleton.

---

## Development (Vendor Bootstrap)

After cloning, install local vendor dependencies with:

```bash
make vendor
```

If `make` is not installed, use:

```bash
python scripts/bootstrap_vendor.py --target local
```

Other useful targets:

```bash
make vendor-check
make vendor-all
make vendor-clean
python scripts/check_config_migrations.py
```

This creates platform-separated vendor folders used by runtime loading:
`vendor/win`, `vendor/linux`, `vendor/macos_x86_64`, `vendor/macos_arm64`, `vendor/common`.

---

## Credits
Those add-ons inspired some of the functionallity of this add-on. Due to unwanted behavior, deprecation or special needs that those addons didn't provide, i had to create my own implementations.

- [Kanji Unlock Addon](https://ankiweb.net/shared/info/953200781) - Technically, nothing in this add-on is based on it, nor did I get the idea for the “Kanji Unlocker” from it. I discovered it after my first working prototype, but due to the similarity, I didn’t want to exclude it from this list.
- [Automatically Sort Cards Into Decks (Card Sorter)](https://ankiweb.net/shared/info/1310787152) - The "Card Sorter" feature is based on this add-on. It's a rework of the original that didn't work properly because of deprecated code and edge-case issues.
- [🔂AnkiRestart - Quick Anki Rebooter, for Customize & Develop (Created by Shigeඞ)](https://ankiweb.net/shared/info/237169833) - The restart workflow is inspired by shigeඞs restart strategy and is now implemented as a dedicated `restart` module with helper-based delayed relaunch.

---

## License
Project code: MIT - see `LICENSE`.

Vendored third-party components (`fugashi`, `unidic-lite`) use their own licenses.
See `THIRD_PARTY_LICENSES.md` and the copied license texts in `licenses/`.

# AJpC Add-on Documentation (Family Gate, Example Gate, Kanji Gate, Card Sorter, Mass Linker)

## What this add-on does

This add-on helps you control *when* Anki cards become available, so you can learn in a structured order:

1. **Family Gate**
   Keeps "advanced" cards hidden until the "base" cards are learned well enough.
2. **Example Gate**
   Unlocks example sentence cards only after the related vocabulary is ready.
3. **Kanji Gate**
   Unlocks kanji/components based on vocab thresholds and behavior mode.
4. **Card Sorter**
   Moves cards into preconfigured decks based on note type and card template.
5. **Mass Linker & Auto Links**
   Adds fallback note links if Anki Note Linker is missing and can auto-generate links based on tags.

This add-on relies primarily on **FSRS** stability ratings, so you must use FSRS to use it!

I recommend using it with its companion add-on: [anki-ajpc-family-graph-addon](https://github.com/axelcypher/anki-ajpc-family-graph-addon). It adds a nice, force-graph-based GUI for connecting notes and editing relationships between them. (I highly recommend it, because I may have overengineered this add-on to the point where even I canâ€™t fully comprehend what connects to what without proper visualization.)

Note types are referenced internally by their **model ID** (not the visible name). The settings UI shows names,
so you only need to care about IDs if you edit the JSON config manually.

---

## Why?

As you can probably guess, I created this add-on mainly to study Japanese. 
However, **you can use it with any learning material you want**.

Although some of this add-onâ€™s functionality is heavily inspired by other add-ons **(Card Sorter)**, those add-ons 
caused issues for me. Also, they used plain JSON for their configs, which I strongly dislike â€” especially if youâ€™re not familiar 
with formats like JSON. Lastly, **I couldnâ€™t find any add-on that provides the gate functionality** (more on that below). 

So the only viable conclusion was: *to write my own version!*

I may extend the functionality over time. ~~Also, if you want to use it for Japanese, I suggest you check out my note templates,~~ 
~~which I built the gate logic around.~~ (Coming soon â€” I need to test them a bit more to make sure everything works correctly)

---

## Family Gate

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

## Family Gate Priority (learning order between related notes)

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

## Example Gate

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

---

## Kanji Gate

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

Credit: [https://ankiweb.net/shared/info/1310787152](https://ankiweb.net/shared/info/1310787152) - The Card Sorter feature is based on this add-on.
Itâ€™s a rework of the original that didnâ€™t work properly because of deprecated code and edge-case issues.

---

## Mass Linker (ANL Fallback + Auto Links)

### Goal

Mass Linker provides note links that work even without Anki Note Linker, and can optionally generate link lists automatically.

### How it works

* If Anki Note Linker is **not installed or disabled**, AJpC converts `[label|nid1234567890123]` into:
  * left-click = preview
  * right-click = open editor
* Auto links can be configured per note type:
  * **Target field** to insert the links
  * **Tag** to search for linked notes
  * **Templates** to include (leave empty = all)
  * **Side** (front/back/both)
  * **Label field** (optional; defaults to first field)
* Placement rule: auto links are inserted into the **parent element of the target field** in the card template.
  * Example: `<div id="links-wrapper">{{LinkedNotes}}</div>` â†’ links are injected into `#links-wrapper` even if the field is empty.

---

## Usage

In Anki you have an AJpC menu with:

* **Run All** (runs all enabled modules)
* **Run -> Run Family Gate**
* **Run -> Run Example Gate**
* **Run -> Run Kanji Gate**
* **Run -> Run Card Sorter**

All settings are configured via the Add-on Settings UI:

* **Settings -> Main Settings**

Note: You should always ***back up your collection before using add-ons.*** While this add-on canâ€™t delete cards, it uses tags for some functionality, 
and ***misconfiguration could scramble up your decks!***

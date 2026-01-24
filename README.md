# AJpC Add-on Documentation (Family Gate, Example Gate, JLPT Tagger, Card Sorter)

## What this add-on does

This add-on helps you control *when* Anki cards become available, so you can learn in a structured order:

1. **Family Gate**
   Keeps "advanced" cards hidden until the "base" cards are learned well enough.
2. **Example Gate**
   Unlocks example sentence cards only after the related vocabulary is ready.
3. **JLPT Tagger**
   Looks up a word on Jisho, verifies it using the reading, and adds helpful tags (JLPT level + "common" where applicable).
4. **Card Sorter**
   Moves cards into preconfigured decks based on note type and card template.

This add-on relies primarily on **FSRS** stability ratings, so you must use FSRS to use it!

---

## Why?

As you can probably guess, I created this add-on mainly to study Japanese. 
However, **you can use it with any learning material you want** (except for the JLPT Tagger, obviously).

Although some of this add-on’s functionality is heavily inspired by other add-ons **(JLPT Tagger & Card Sorter)**, those add-ons 
caused issues for me. Also, they used plain JSON for their configs, which I strongly dislike — especially if you’re not familiar 
with formats like JSON. Lastly, **I couldn’t find any add-on that provides the gate functionality** (more on that below). 

So the only viable conclusion was: *to write my own version!*

I may extend the functionality over time. ~~Also, if you want to use it for Japanese, I suggest you check out my note templates,~~ 
~~which I built the gate logic around.~~ (Coming soon — I need to test them a bit more to make sure everything works correctly)

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

## JLPT Tagger

### Goal

Automatically tag your vocab with:

* JLPT level (N5-N1 where available)
* "common" if Jisho marks it as common
* a fallback tag if no JLPT level exists

### How it works

1. The add-on reads the word from your **Vocab** field.
2. It searches Jisho for that term.
3. It compares the reading from Anki to the reading from Jisho.
4. Only if it matches, tags are applied.

### Tag rules

* If multiple JLPT levels appear, the lowest level (easiest) is chosen.
* If no JLPT level exists, it applies your configured "no JLPT" tag.
* Adds "common" if the entry is marked common.

Credit: [https://ankiweb.net/shared/info/368576817](https://ankiweb.net/shared/info/368576817) - I got the idea for the tagger from this add-on. 
Since it doesn’t work reliably with the current Anki version, I implemented my own.

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
It’s a rework of the original that didn’t work properly because of deprecated code and edge-case issues.

---

## Usage

In Anki you have an AJpC menu with:

* **Run Family Gate**
* **Run Example Gate**
* **Run JLPT Tagger**
* **Run Card Sorter**

All settings are configured via the Add-on Settings UI.


Note: You should always ***back up your collection before using add-ons.*** While this add-on can’t delete cards, it uses tags for some functionality, 
and ***misconfiguration could scramble up your decks!***

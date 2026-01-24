from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from typing import Any

from anki.collection import Collection

from .. import config, logging
from ..utils import note_ids_for_deck

_BRACKET_RE = re.compile(r"\[[^\]]*\]")
_JLPT_RE = re.compile(r"jlpt[\s\-_]?n([1-5])", re.IGNORECASE)


def _strip_brackets(s: str) -> str:
    return _BRACKET_RE.sub("", s or "").strip()


def _normalize_value(s: str) -> str:
    return _strip_brackets(s).strip()


def _fetch_jisho(keyword: str) -> list[dict[str, Any]] | None:
    q = keyword.strip()
    if not q:
        return None
    url = "https://jisho.org/api/v1/search/words?keyword=" + urllib.parse.quote(q)
    req = urllib.request.Request(url, headers={"User-Agent": "AJpC-Tools/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            payload = resp.read().decode("utf-8")
        data = json.loads(payload)
        items = data.get("data", [])
        if isinstance(items, list):
            return items
    except Exception as exc:
        logging.dbg("jlpt_tagger: fetch failed", q, repr(exc))
    return None


def _extract_jlpt_levels(entry: dict[str, Any]) -> list[int]:
    levels: list[int] = []
    tags = entry.get("jlpt", []) or []
    if isinstance(tags, list):
        for t in tags:
            s = str(t)
            m = _JLPT_RE.search(s)
            if m:
                try:
                    levels.append(int(m.group(1)))
                except Exception:
                    continue
    return levels


def _reading_matches(entry: dict[str, Any], target_reading: str) -> bool:
    if not target_reading:
        return False
    jp_list = entry.get("japanese", []) or []
    for jp in jp_list:
        if not isinstance(jp, dict):
            continue
        reading = _normalize_value(str(jp.get("reading", "")))
        if reading and reading == target_reading:
            return True
    return False


def _pick_lowest_level(levels: list[int]) -> int | None:
    if not levels:
        return None
    return max(levels)


def _resolve_tag(tag_map: dict[str, str], key: str, fallback: str) -> str:
    key_l = key.lower()
    v = tag_map.get(key_l)
    if v is None or v == "":
        alt = key_l.replace("-", "")
        v = tag_map.get(alt)
    if v is None or v == "":
        return fallback
    return str(v)


def _jlpt_tag_candidates(tag_map: dict[str, str]) -> set[str]:
    keys = ["jlpt-n5", "jlpt-n4", "jlpt-n3", "jlpt-n2", "jlpt-n1", "jlpt-none"]
    out: set[str] = set()
    for k in keys:
        mapped = tag_map.get(k)
        if mapped:
            out.add(str(mapped))
        mapped_alt = tag_map.get(k.replace("-", ""))
        if mapped_alt:
            out.add(str(mapped_alt))
    return {t for t in out if t}


def _note_has_jlpt_tag(note, candidates: set[str]) -> bool:
    if not candidates:
        return False
    note_tags = set(note.tags)
    note_tags_lower = {t.lower() for t in note_tags}
    for cand in candidates:
        if cand in note_tags or cand.lower() in note_tags_lower:
            return True
    return False


def _should_cancel() -> bool:
    try:
        from aqt import mw

        if mw is None:
            return False
        return bool(mw.progress.want_cancel())
    except Exception:
        return False


def _add_tags(note, tags: list[str]) -> int:
    added = 0
    for t in tags:
        if not t:
            continue
        if t not in note.tags:
            note.add_tag(t)
            added += 1
    if added:
        note.flush()
    return added


def jlpt_tagger_apply(col: Collection, ui_set, counters: dict[str, int]) -> None:
    if not config.JLPT_TAGGER_DECKS:
        logging.dbg("jlpt_tagger: no decks configured")
        return
    if not config.JLPT_TAGGER_NOTE_TYPES:
        logging.dbg("jlpt_tagger: no note types configured")
        return

    note_ids_set: set[int] = set()
    for deck in config.JLPT_TAGGER_DECKS:
        note_ids_set.update(note_ids_for_deck(col, deck))

    note_ids = list(note_ids_set)
    total = len(note_ids)
    logging.dbg("jlpt_tagger: candidate notes", total)

    cache: dict[str, list[dict[str, Any]] | None] = {}
    raw_map = config.JLPT_TAGGER_TAG_MAP or config.DEFAULT_JLPT_TAG_MAP
    tag_map = {str(k).lower(): str(v) for k, v in raw_map.items()}
    jlpt_tag_candidates = _jlpt_tag_candidates(tag_map)

    cancelled = False
    for i, nid in enumerate(note_ids):
        try:
            if _should_cancel():
                logging.dbg("jlpt_tagger: cancelled")
                cancelled = True
                break
            note = col.get_note(nid)
            model = col.models.get(note.mid)
            nt_name = str(model.get("name", ""))
            if nt_name not in config.JLPT_TAGGER_NOTE_TYPES:
                continue

            fields_cfg = config.JLPT_TAGGER_FIELDS.get(nt_name, {}) or {}
            vocab_field = str(fields_cfg.get("vocab_field", "")).strip()
            reading_field = str(fields_cfg.get("reading_field", "")).strip()
            if not vocab_field or not reading_field:
                logging.dbg("jlpt_tagger: missing field mapping", "note_type=", nt_name)
                continue
            if vocab_field not in note or reading_field not in note:
                logging.dbg("jlpt_tagger: field not in note", "nid=", nid, "note_type=", nt_name)
                continue

            raw_vocab = str(note[vocab_field] or "")
            raw_reading = str(note[reading_field] or "")
            vocab = _normalize_value(raw_vocab)
            reading = _normalize_value(raw_reading)
            if not vocab:
                logging.dbg("jlpt_tagger: empty vocab", "nid=", nid, "field=", vocab_field)
                continue
            if not reading:
                logging.dbg("jlpt_tagger: empty reading", "nid=", nid, "field=", reading_field)
                continue
            if _note_has_jlpt_tag(note, jlpt_tag_candidates):
                if config.DEBUG:
                    logging.dbg("jlpt_tagger: skip (already tagged)", "nid=", nid, "note_type=", nt_name)
                continue

            ui_set(
                f"JLPT Tagger: {i + 1}/{total} | {vocab} [{reading}]",
                i + 1,
                total or 1,
            )

            if vocab in cache:
                items = cache[vocab]
            else:
                if _should_cancel():
                    logging.dbg("jlpt_tagger: cancelled (before fetch)")
                    cancelled = True
                    break
                items = _fetch_jisho(vocab)
                cache[vocab] = items

            if not items:
                logging.dbg("jlpt_tagger: no results", "nid=", nid, "vocab=", vocab)
                continue

            matched = [entry for entry in items if _reading_matches(entry, reading)]
            if not matched:
                logging.dbg("jlpt_tagger: reading mismatch", "nid=", nid, "vocab=", vocab, "reading=", reading)
                continue

            all_levels: list[int] = []
            is_common = False
            for entry in matched:
                all_levels.extend(_extract_jlpt_levels(entry))
                if entry.get("is_common"):
                    is_common = True
                tags = entry.get("tags", []) or []
                if isinstance(tags, list) and "common" in [str(t).lower() for t in tags]:
                    is_common = True

            level = _pick_lowest_level(all_levels)
            tags_to_add: list[str] = []
            if level is None:
                jlpt_key = "jlpt-none"
                logging.dbg("jlpt_tagger: no jlpt tag", "nid=", nid, "vocab=", vocab, "reading=", reading)
            else:
                jlpt_key = f"jlpt-n{level}"

            jlpt_tag = _resolve_tag(tag_map, jlpt_key, jlpt_key)
            tags_to_add.append(jlpt_tag)

            if is_common:
                common_tag = _resolve_tag(tag_map, "common", "common")
                tags_to_add.append(common_tag)

            added = _add_tags(note, tags_to_add)
            if added:
                counters["notes_tagged"] += 1
                counters["tags_added"] += added
                if level is None:
                    counters["no_jlpt_tagged"] += 1
                else:
                    counters["jlpt_tagged"] += 1
                if is_common:
                    counters["common_tagged"] += 1

        except Exception as exc:
            logging.dbg("jlpt_tagger: exception", nid, repr(exc))

    if cancelled:
        ui_set(
            f"JLPT Tagger: cancelled | tagged={counters['notes_tagged']}",
            total,
            total or 1,
        )
        return

    ui_set(
        f"JLPT Tagger: done | tagged={counters['notes_tagged']}",
        total,
        total or 1,
    )

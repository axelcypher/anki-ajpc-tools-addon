from __future__ import annotations

import re
import traceback
import unicodedata
from dataclasses import dataclass
from typing import Any, Iterable

from anki.collection import Collection

from . import config, logging

DEFAULT_STICKY_TAG_BASE = "_intern::family_gate::unlocked"
DEFAULT_STAGE_TAG_PREFIX = "_intern::family_gate::unlocked::stage"
DEFAULT_EXAMPLE_TAG_PREFIX = "_intern::family_gate::unlocked::example_stage"

_LOGGED_TEMPLATE_MISS: set[tuple[str, int]] = set()

_HTML_RE = re.compile(r"<.*?>", re.DOTALL)
_FURIGANA_BR_RE = re.compile(r"\[[^\]]*\]")


def _strip_html(s: str) -> str:
    return _HTML_RE.sub("", s)


def norm_text(s: str) -> str:
    s = s or ""
    if config.KEY_STRIP_HTML:
        s = _strip_html(s)
    if config.KEY_STRIP_FURIGANA_BR:
        s = _FURIGANA_BR_RE.sub("", s)
    if config.KEY_TRIM:
        s = s.strip()
    if config.KEY_NFC:
        s = unicodedata.normalize("NFC", s)
    if config.KEY_FIRST_TOKEN:
        s = s.split(" ")[0] if s else ""
    return s


@dataclass(frozen=True)
class FamilyRef:
    fid: str
    prio: int


def parse_family_field(raw: str) -> list[FamilyRef]:
    out: list[FamilyRef] = []
    if not raw:
        return out

    for part in raw.split(config.FAMILY_SEP):
        p = part.strip()
        if not p:
            continue
        if "@" in p:
            left, right = p.rsplit("@", 1)
            fid = unicodedata.normalize("NFC", left.strip())
            if not fid:
                continue
            try:
                prio = int(right.strip())
            except Exception:
                prio = config.FAMILY_DEFAULT_PRIO
            out.append(FamilyRef(fid=fid, prio=prio))
        else:
            fid = unicodedata.normalize("NFC", p)
            if fid:
                out.append(FamilyRef(fid=fid, prio=config.FAMILY_DEFAULT_PRIO))

    return out


@dataclass(frozen=True)
class ExampleRef:
    key: str
    stage: int


def parse_example_key(raw: str) -> ExampleRef:
    s = norm_text(raw or "")
    if not s:
        return ExampleRef(key="", stage=config.EX_STAGE_DEFAULT)

    if config.EX_STAGE_SEP and config.EX_STAGE_SEP in s:
        left, right = s.rsplit(config.EX_STAGE_SEP, 1)
        key = norm_text(left)
        try:
            stage = int(right.strip())
        except Exception:
            stage = config.EX_STAGE_DEFAULT
        return ExampleRef(key=key, stage=stage)

    return ExampleRef(key=s, stage=config.EX_STAGE_DEFAULT)


def stage_tag(stage_index: int) -> str:
    return f"{DEFAULT_STAGE_TAG_PREFIX}{stage_index}"


def example_stage_tag(stage_index: int) -> str:
    return f"{DEFAULT_EXAMPLE_TAG_PREFIX}{stage_index}"


def _memory_state(card):
    try:
        ms_attr = getattr(card, "memory_state", None)
    except Exception:
        return None

    if ms_attr is None:
        return None

    try:
        return ms_attr() if callable(ms_attr) else ms_attr
    except Exception:
        return None


def card_stability(card) -> float | None:
    ms = _memory_state(card)
    stab = getattr(ms, "stability", None) if ms is not None else None
    if stab is None:
        return None
    try:
        return float(stab)
    except Exception:
        return None


def agg(vals: list[float]) -> float | None:
    if not vals:
        return None
    if config.STABILITY_AGG == "max":
        return max(vals)
    if config.STABILITY_AGG == "avg":
        return sum(vals) / len(vals)
    return min(vals)


def _dbg_card_state(card, tmpl_name: str) -> str:
    try:
        ms = _memory_state(card)
        ms_s = getattr(ms, "stability", None) if ms is not None else None
        ms_d = getattr(ms, "difficulty", None) if ms is not None else None
    except Exception as e:
        ms = None
        ms_s = None
        ms_d = None
        ms_err = repr(e)
    else:
        ms_err = ""

    try:
        return (
            f"cid={card.id} ord={getattr(card,'ord',None)} tmpl={tmpl_name!r} "
            f"queue={getattr(card,'queue',None)} type={getattr(card,'type',None)} "
            f"reps={getattr(card,'reps',None)} lapses={getattr(card,'lapses',None)} "
            f"ivl={getattr(card,'ivl',None)} due={getattr(card,'due',None)} "
            f"ms_stab={ms_s} ms_diff={ms_d}"
            + (f" ms_err={ms_err}" if ms_err else "")
        )
    except Exception as e:
        return f"cid={getattr(card,'id',None)} tmpl={tmpl_name!r} _dbg_fail={repr(e)}"


def _chunks(items: Iterable[int], size: int = 1000) -> Iterable[list[int]]:
    buf: list[int] = []
    for x in items:
        buf.append(x)
        if len(buf) >= size:
            yield buf
            buf = []
    if buf:
        yield buf


def suspend_cards(col: Collection, cids: list[int]) -> None:
    if not cids:
        return
    try:
        for chunk in _chunks(cids, 1000):
            col.sched.suspend_cards(chunk)
        return
    except Exception:
        pass

    for cid in cids:
        try:
            c = col.get_card(cid)
            if c.queue != -1:
                c.queue = -1
                col.update_card(c)
        except Exception:
            continue


def unsuspend_cards(col: Collection, cids: list[int]) -> None:
    if not cids:
        return
    try:
        for chunk in _chunks(cids, 1000):
            col.sched.unsuspend_cards(chunk)
        return
    except Exception:
        pass

    for cid in cids:
        try:
            c = col.get_card(cid)
            if c.queue == -1:
                c.queue = 0
                col.update_card(c)
        except Exception:
            continue


def _verify_suspended(col: Collection, cids: list[int], *, label: str) -> None:
    if not config.DEBUG or not config.DEBUG_VERIFY_SUSPENSION or not cids:
        return

    suspended = 0
    total = 0

    for chunk in _chunks(cids, 400):
        qmarks = ",".join(["?"] * len(chunk))
        rows = col.db.all(f"select queue from cards where id in ({qmarks})", *chunk)
        total += len(rows)
        suspended += sum(1 for (q,) in rows if q == -1)

    logging.dbg(
        "verify",
        label,
        "targets=",
        len(cids),
        "rows=",
        total,
        "suspended_now=",
        suspended,
        "not_suspended_now=",
        total - suspended,
    )


@dataclass
class StageCfg:
    templates: list[str]
    threshold: float


def get_stage_cfg_for_note_type(note_type_name: str) -> list[StageCfg]:
    nt = config.FAMILY_NOTE_TYPES.get(note_type_name) or {}
    stages = nt.get("stages") or []
    out: list[StageCfg] = []

    for st in stages:
        if isinstance(st, dict):
            tmpls = [str(x) for x in (st.get("templates") or [])]
            thr = float(st.get("threshold", config.STABILITY_DEFAULT_THRESHOLD))
            out.append(StageCfg(templates=tmpls, threshold=thr))
        elif isinstance(st, list):
            out.append(StageCfg(templates=[str(x) for x in st], threshold=config.STABILITY_DEFAULT_THRESHOLD))

    return out


def _tmpl_by_ord(col: Collection, note) -> dict[int, str]:
    out: dict[int, str] = {}
    try:
        model = col.models.get(note.mid)
        tmpls = model.get("tmpls", [])
        for i, t in enumerate(tmpls):
            out[i] = str(t.get("name", ""))
    except Exception:
        pass
    return out


def compute_stage_stabilities(col: Collection, note, note_type_name: str) -> list[float | None]:
    stages = get_stage_cfg_for_note_type(note_type_name)
    if not stages:
        return []

    cards = note.cards()
    name_by_ord = _tmpl_by_ord(col, note)

    stabs: list[float | None] = []
    for st in stages:
        wanted = set(st.templates)
        vals: list[float] = []
        saw_any = False
        has_unknown = False

        for c in cards:
            if (name_by_ord.get(c.ord) or "") in wanted:
                saw_any = True
                s = card_stability(c)
                if s is None:
                    has_unknown = True
                else:
                    vals.append(s)

        if not saw_any:
            stabs.append(None)
        elif has_unknown:
            stabs.append(None)
        else:
            stabs.append(agg(vals))

    return stabs


def stage_is_ready(note_type_name: str, stage_index: int, stage_stab: float | None) -> bool:
    stages = get_stage_cfg_for_note_type(note_type_name)
    if stage_index < 0 or stage_index >= len(stages):
        return False
    if stage_stab is None:
        return False
    return stage_stab >= float(stages[stage_index].threshold)


def stage_card_ids(col: Collection, note, note_type_name: str, stage_index: int) -> list[int]:
    stages = get_stage_cfg_for_note_type(note_type_name)
    if stage_index < 0 or stage_index >= len(stages):
        return []

    wanted = set(stages[stage_index].templates)
    name_by_ord = _tmpl_by_ord(col, note)

    cids: list[int] = []
    for c in note.cards():
        if (name_by_ord.get(c.ord) or "") in wanted:
            cids.append(c.id)

    if config.DEBUG and not cids:
        key = (note_type_name, stage_index)
        if key not in _LOGGED_TEMPLATE_MISS:
            _LOGGED_TEMPLATE_MISS.add(key)
            avail = sorted({v for v in name_by_ord.values() if v})
            logging.dbg(
                "stage_card_ids: no cards matched stage",
                "note_type=",
                note_type_name,
                "stage=",
                stage_index,
                "wanted=",
                sorted(wanted),
                "available_templates=",
                avail,
            )

    return cids


def debug_template_coverage(col: Collection) -> None:
    if not config.DEBUG:
        return
    for nt_name in config.FAMILY_NOTE_TYPES.keys():
        m = col.models.by_name(nt_name)
        if not m:
            logging.dbg("coverage", nt_name, "model_not_found")
            continue

        model_names = [str(t.get("name", "")) for t in (m.get("tmpls") or [])]
        cfg_names: set[str] = set()
        for st in get_stage_cfg_for_note_type(nt_name):
            cfg_names |= set(st.templates)

        missing = [n for n in model_names if n and n not in cfg_names]
        extra = [n for n in sorted(cfg_names) if n and n not in model_names]

        if missing or extra:
            logging.dbg(
                "coverage",
                nt_name,
                "missing_from_cfg=",
                [repr(x) for x in missing],
                "cfg_unknown=",
                [repr(x) for x in extra],
            )


def _anki_quote(s: str) -> str:
    return (s or "").replace("\\", "\\\\").replace('"', '\\"')


def note_ids_for_note_types(col: Collection, note_types: list[str]) -> list[int]:
    nids: list[int] = []
    for nt in note_types:
        q = f'note:"{_anki_quote(nt)}"'
        if config.DEBUG:
            logging.dbg("note_ids_for_note_types", nt, "->", q)
        try:
            found = col.find_notes(q)
            if config.DEBUG:
                logging.dbg("note_ids_for_note_types count", nt, len(found))
            nids.extend(found)
        except Exception:
            if config.DEBUG:
                logging.dbg("note_ids_for_note_types failed", nt)
                logging.dbg(traceback.format_exc())
            continue
    return nids


def note_ids_for_deck(col: Collection, deck_name: str) -> list[int]:
    dn = _anki_quote(deck_name)
    q = f'deck:"{dn}"'
    if config.DEBUG:
        logging.dbg("note_ids_for_deck", deck_name, "->", q)
    try:
        found = col.find_notes(q)
        if config.DEBUG:
            logging.dbg("note_ids_for_deck count", deck_name, len(found))
        return found
    except Exception:
        if config.DEBUG:
            logging.dbg("note_ids_for_deck failed", q)
            logging.dbg(traceback.format_exc())
        return []

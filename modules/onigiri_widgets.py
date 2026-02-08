from __future__ import annotations

from dataclasses import dataclass
import html
import time
from typing import Iterable

from aqt import gui_hooks, mw

from . import ModuleSpec


_CACHE_TTL_SEC = 8.0
_CACHE_TS = 0.0
_CACHE_HTML = ""


@dataclass(frozen=True)
class GateProgress:
    label: str
    enabled: bool
    tracked: int
    free: int


def _chunks(items: Iterable[int], size: int = 400) -> Iterable[list[int]]:
    buf: list[int] = []
    for x in items:
        buf.append(int(x))
        if len(buf) >= size:
            yield buf
            buf = []
    if buf:
        yield buf


def _count_unsuspended_cards(cids: set[int]) -> int:
    if not cids or mw is None or not getattr(mw, "col", None):
        return 0
    total = 0
    for chunk in _chunks(cids, 400):
        qmarks = ",".join(["?"] * len(chunk))
        try:
            rows = mw.col.db.all(
                f"select queue from cards where id in ({qmarks})",
                *chunk,
            )
        except Exception:
            continue
        total += sum(1 for (q,) in rows if int(q) != -1)
    return int(total)


def _progress_card_stages() -> GateProgress:
    try:
        from . import card_stages as mod

        mod.config.reload_config()
        enabled = bool(mod.config.CARD_STAGES_ENABLED)
        tracked: set[int] = set()
        if enabled and mw is not None and getattr(mw, "col", None):
            note_types = list((mod.config.CARD_STAGES_NOTE_TYPES or {}).keys())
            nids = mod.note_ids_for_note_types(mw.col, note_types)
            for nid in nids:
                try:
                    note = mw.col.get_note(int(nid))
                except Exception:
                    continue
                stages = mod.get_stage_cfg_for_note_type(int(note.mid))
                wanted = {str(t) for st in stages for t in (st.templates or [])}
                if not wanted:
                    continue
                for card in note.cards():
                    if str(card.ord) in wanted:
                        tracked.add(int(card.id))
        free = _count_unsuspended_cards(tracked)
        return GateProgress("Card Stages completed", enabled, len(tracked), free)
    except Exception:
        return GateProgress("Card Stages completed", False, 0, 0)


def _progress_family_gate() -> GateProgress:
    try:
        from . import family_gate as mod

        mod.config.reload_config()
        enabled = bool(mod.config.FAMILY_GATE_ENABLED)
        tracked: set[int] = set()
        if enabled and mw is not None and getattr(mw, "col", None):
            note_types = list((mod.config.FAMILY_NOTE_TYPES or {}).keys())
            nids = mod.note_ids_for_note_types(mw.col, note_types)
            family_field = str(mod.config.FAMILY_FIELD or "").strip()
            for nid in nids:
                try:
                    note = mw.col.get_note(int(nid))
                except Exception:
                    continue
                if not family_field or family_field not in note:
                    continue
                refs = mod.parse_family_field(str(note[family_field] or ""))
                if not refs:
                    continue
                for card in note.cards():
                    tracked.add(int(card.id))
        free = _count_unsuspended_cards(tracked)
        return GateProgress("Family Priority progression", enabled, len(tracked), free)
    except Exception:
        return GateProgress("Family Priority progression", False, 0, 0)


def _progress_example_gate() -> GateProgress:
    try:
        from . import example_gate as mod

        mod.config.reload_config()
        enabled = bool(mod.config.EXAMPLE_GATE_ENABLED)
        tracked: set[int] = set()
        if enabled and mw is not None and getattr(mw, "col", None):
            ex_deck = str(mod.config.EXAMPLE_DECK or "").strip()
            if ex_deck:
                ex_nids = mod.note_ids_for_deck(mw.col, ex_deck)
                apply_all = bool(mod.config.EX_APPLY_ALL_CARDS)
                for nid in ex_nids:
                    try:
                        note = mw.col.get_note(int(nid))
                    except Exception:
                        continue
                    cloze_surface = mod._extract_first_cloze_target(note)
                    if not cloze_surface:
                        continue
                    cards = note.cards()
                    if not cards:
                        continue
                    if apply_all:
                        for card in cards:
                            tracked.add(int(card.id))
                    else:
                        tracked.add(int(cards[0].id))
        free = _count_unsuspended_cards(tracked)
        return GateProgress("Examples unlocked", enabled, len(tracked), free)
    except Exception:
        return GateProgress("Examples unlocked", False, 0, 0)


def _progress_kanji_gate() -> GateProgress:
    try:
        from . import kanji_gate as mod

        mod.config.reload_config()
        enabled = bool(mod.config.KANJI_GATE_ENABLED)
        tracked: set[int] = set()
        if not enabled or mw is None or not getattr(mw, "col", None):
            return GateProgress("Kanji", enabled, 0, 0)

        behavior = str(mod.config.KANJI_GATE_BEHAVIOR or "").strip()
        if behavior not in (
            "kanji_only",
            "kanji_then_components",
            "components_then_kanji",
            "kanji_and_components",
        ):
            return GateProgress("Kanji", enabled, 0, 0)

        vocab_cfgs = mod._get_vocab_cfgs()
        kanji_note_type = str(mod.config.KANJI_GATE_KANJI_NOTE_TYPE or "").strip()
        kanji_fields = [str(x).strip() for x in (mod.config.KANJI_GATE_KANJI_FIELDS or []) if str(x).strip()]
        components_field = str(mod.config.KANJI_GATE_COMPONENTS_FIELD or "").strip()
        kanji_radical_field = str(mod.config.KANJI_GATE_KANJI_RADICAL_FIELD or "").strip()
        radical_note_type = str(mod.config.KANJI_GATE_RADICAL_NOTE_TYPE or "").strip()
        radical_field = str(mod.config.KANJI_GATE_RADICAL_FIELD or "").strip()
        use_components = behavior in ("kanji_then_components", "components_then_kanji", "kanji_and_components")
        radicals_enabled = bool(use_components and kanji_radical_field and radical_note_type and radical_field)
        if not vocab_cfgs or not kanji_note_type or not kanji_fields:
            return GateProgress("Kanji unlocked", enabled, 0, 0)
        if use_components and not components_field:
            return GateProgress("Kanji unlocked", enabled, 0, 0)

        note_cache: dict[int, object] = {}

        def _get_note(nid: int):
            if nid not in note_cache:
                note_cache[nid] = mw.col.get_note(int(nid))
            return note_cache[nid]

        vocab_scope_cards: set[int] = set()
        target_kanji: set[str] = set()
        vocab_nids = mod.note_ids_for_note_types(mw.col, list(vocab_cfgs.keys()))
        for nid in vocab_nids:
            try:
                note = _get_note(int(nid))
            except Exception:
                continue
            nt_id = str(getattr(note, "mid", ""))
            cfg = vocab_cfgs.get(nt_id)
            if not cfg or cfg.reading_field not in note:
                continue
            raw = str(note[cfg.reading_field] or "")
            cleaned = mod.strip_reading_brackets(raw)
            kanji_list = mod.extract_kanji(cleaned)
            if not kanji_list:
                continue
            base_templates = set(cfg.base_templates or [])
            base_stab = mod._templates_stability(note, base_templates, "min")
            base_ready = bool(base_stab is not None and float(base_stab) >= float(cfg.base_threshold))
            kanji_templates = set(cfg.kanji_templates or [])
            if kanji_templates:
                for card in note.cards():
                    if str(card.ord) in kanji_templates:
                        vocab_scope_cards.add(int(card.id))
            if base_ready:
                target_kanji.update(kanji_list)

        root_chars = set(target_kanji)

        kanji_index: dict[str, list[mod.KanjiNoteEntry]] = {}
        note_chars: dict[int, set[str]] = {}
        all_radicals: set[str] = set()
        kanji_nids = mod.note_ids_for_note_types(mw.col, [kanji_note_type])
        for nid in kanji_nids:
            try:
                note = _get_note(int(nid))
            except Exception:
                continue
            keys: list[str] = []
            for field_name in kanji_fields:
                if field_name in note:
                    keys.extend(mod.extract_kanji(str(note[field_name] or "")))
            if not keys:
                continue
            comps: list[str] = []
            if use_components and components_field in note:
                comps = mod.extract_kanji(str(note[components_field] or ""))
            radicals: list[str] = []
            if radicals_enabled and kanji_radical_field in note:
                radicals = mod.extract_kanji(str(note[kanji_radical_field] or ""))
            key_set = set(keys)
            note_chars[int(nid)] = key_set
            entry = mod.KanjiNoteEntry(nid=int(nid), components=comps, radicals=radicals)
            for k in key_set:
                kanji_index.setdefault(k, []).append(entry)
            if radicals:
                all_radicals.update(radicals)

        radical_index: dict[str, list[int]] = {}
        if radicals_enabled:
            radical_nids = mod.note_ids_for_note_types(mw.col, [radical_note_type])
            for nid in radical_nids:
                try:
                    note = _get_note(int(nid))
                except Exception:
                    continue
                if radical_field not in note:
                    continue
                rads = mod.extract_kanji(str(note[radical_field] or ""))
                if not rads:
                    continue
                for rad in set(rads):
                    radical_index.setdefault(rad, []).append(int(nid))

        radical_scope_note_ids: set[int] = set()
        if radicals_enabled and all_radicals:
            for rad in all_radicals:
                for rnid in radical_index.get(rad, []):
                    radical_scope_note_ids.add(int(rnid))

        def _add_note_cards(nid: int, out: set[int]) -> None:
            note = _get_note(int(nid))
            for card in note.cards():
                out.add(int(card.id))

        kanji_scope_cards: set[int] = set()
        component_scope_cards: set[int] = set()
        for nid, chars in note_chars.items():
            if chars & root_chars:
                _add_note_cards(nid, kanji_scope_cards)
            else:
                _add_note_cards(nid, component_scope_cards)

        radical_scope_cards: set[int] = set()
        if radicals_enabled:
            for rnid in radical_scope_note_ids:
                _add_note_cards(rnid, radical_scope_cards)

        tracked = vocab_scope_cards | kanji_scope_cards | component_scope_cards | radical_scope_cards
        free = _count_unsuspended_cards(tracked)
        return GateProgress("Kanji unlocked", enabled, len(tracked), free)
    except Exception:
        return GateProgress("Kanji unlocked", False, 0, 0)


def _render_widget_html() -> str:
    gates = [
        _progress_card_stages(),
        _progress_family_gate(),
        _progress_example_gate(),
        _progress_kanji_gate(),
    ]
    cells: list[str] = []
    for g in gates:
        if not g.enabled:
            pct_txt = "-"
            cnt_txt = "disabled"
        elif g.tracked <= 0:
            pct_txt = "0.0%"
            cnt_txt = "0/0"
        else:
            pct = (float(g.free) / float(g.tracked)) * 100.0
            pct_txt = f"{pct:.1f}%"
            cnt_txt = f"{g.free}/{g.tracked}"
        cells.append(
            f"<div style=\"padding:2px 0;text-align:left;\">{html.escape(g.label)}</div>"
            f"<div style=\"padding:2px 0;text-align:right;font-weight:600;\">{html.escape(pct_txt)}</div>"
            f"<div style=\"padding:2px 0;text-align:right;opacity:.8;\">{html.escape(cnt_txt)}</div>"
        )
    joined = "".join(cells)
    return (
        "<div class=\"stat-card\" style=\"padding:12px;\">"
        "<h3>AJpC Progress</h3>"
        "<div style=\"display:grid;grid-template-columns:minmax(80px,1fr) auto 80px;column-gap:12px;row-gap:0px;align-items:center;\">"
        f"{joined}"
        "</div>"
        "</div>"
    )


def _invalidate_cache(*_args, **_kwargs) -> None:
    global _CACHE_TS
    _CACHE_TS = 0.0


def _on_deck_browser_render(_deck_browser, content) -> None:
    global _CACHE_TS, _CACHE_HTML
    now = time.monotonic()
    if _CACHE_HTML and (now - _CACHE_TS) < _CACHE_TTL_SEC:
        html_block = _CACHE_HTML
    else:
        html_block = _render_widget_html()
        _CACHE_HTML = html_block
        _CACHE_TS = now
    existing = getattr(content, "stats", "")
    content.stats = f"{existing}{html_block}"


def _init() -> None:
    if mw is None:
        return
    if getattr(mw, "_ajpc_onigiri_widgets_installed", False):
        return
    gui_hooks.deck_browser_will_render_content.append(_on_deck_browser_render)
    op_hook = getattr(gui_hooks, "operation_did_execute", None)
    if op_hook is not None:
        op_hook.append(_invalidate_cache)
    add_note_hook = getattr(gui_hooks, "add_cards_did_add_note", None)
    if add_note_hook is not None:
        add_note_hook.append(_invalidate_cache)
    sync_start_hook = getattr(gui_hooks, "sync_will_start", None)
    if sync_start_hook is not None:
        sync_start_hook.append(_invalidate_cache)
    sync_finish_hook = getattr(gui_hooks, "sync_did_finish", None)
    if sync_finish_hook is not None:
        sync_finish_hook.append(_invalidate_cache)
    mw._ajpc_onigiri_widgets_installed = True


MODULE = ModuleSpec(
    id="onigiri_widgets",
    label="Onigiri Widgets",
    order=96,
    init=_init,
)

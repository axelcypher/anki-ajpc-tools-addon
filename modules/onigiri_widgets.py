from __future__ import annotations

import html
import time

from aqt import gui_hooks, mw

from . import ModuleSpec
from ._widgets.deck_stats_registry import collect_entries


_CACHE_TTL_SEC = 8.0
_CACHE_TS = 0.0
_CACHE_HTML = ""


def _render_widget_html() -> str:
    gates = collect_entries()
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


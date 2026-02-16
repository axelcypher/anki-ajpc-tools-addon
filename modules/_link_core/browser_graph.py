from __future__ import annotations

import json
import os
import re
import weakref
from dataclasses import dataclass
from typing import Any

import aqt.editor
from aqt import gui_hooks, mw
from aqt.qt import (
    QApplication,
    QBrush,
    QColor,
    QCursor,
    QFont,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPalette,
    QSplitter,
    QSize,
    QSizePolicy,
    QTimer,
    QVBoxLayout,
    QWidget,
    Qt,
)
from aqt.editor import Editor
from aqt.browser.previewer import Previewer
from anki.cards import Card

from ... import logging
from .dep_tree_view import PrioChainView
from .force_graph_view import ForceGraphView
from .note_editor import open_note_editor

_RAW_LINK_RE = re.compile(r"\[((?:[^\[]|\\\[)*?)\|(nid|cid)(\d+)\]", re.IGNORECASE)
_BROWSERS: "weakref.WeakSet[Any]" = weakref.WeakSet()
_ADDON_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
_CONFIG_PATH = os.path.join(_ADDON_DIR, "config.json")


@dataclass(frozen=True)
class ParsedLink:
    label: str
    kind: str
    target_id: int


@dataclass(frozen=True)
class PanelItem:
    text: str
    open_nid: int
    link_kind: str
    link_id: int
    bucket: str = ""
    is_header: bool = False
    clickable: bool = True


@dataclass(frozen=True)
class _FamilyRef:
    fid: str
    prio: int
    explicit: bool


def _parse_raw_links(text: str) -> list[ParsedLink]:
    out: list[ParsedLink] = []
    if not text:
        return out
    for m in _RAW_LINK_RE.finditer(text):
        label = str(m.group(1) or "").replace("\\[", "[")
        kind = str(m.group(2) or "").lower()
        try:
            target = int(m.group(3))
        except Exception:
            continue
        out.append(ParsedLink(label=label, kind=kind, target_id=target))
    return out


def _family_cfg() -> tuple[str, str, int]:
    field = "FamilyID"
    sep = ";"
    default_prio = 0
    try:
        with open(_CONFIG_PATH, "r", encoding="utf-8-sig") as f:
            cfg = json.load(f)
        fg = cfg.get("family_priority", {}) if isinstance(cfg, dict) else {}
        family = fg.get("family", {}) if isinstance(fg, dict) else {}
        field = str(family.get("field", field) or field).strip() or field
        sep = str(family.get("separator", sep) or sep).strip() or sep
        try:
            default_prio = int(family.get("default_prio", 0))
        except Exception:
            default_prio = 0
    except Exception:
        pass
    return field, sep, default_prio


def _parse_family_refs(raw: str, sep: str, default_prio: int) -> list[_FamilyRef]:
    out: list[_FamilyRef] = []
    if not raw:
        return out
    for part in str(raw).split(sep):
        token = str(part or "").strip()
        if not token:
            continue
        if "@" in token:
            left, right = token.rsplit("@", 1)
            fid = str(left or "").strip()
            if not fid:
                continue
            try:
                prio = int(str(right or "").strip())
            except Exception:
                prio = int(default_prio)
            out.append(_FamilyRef(fid=fid, prio=prio, explicit=True))
        else:
            fid = token
            if fid:
                out.append(_FamilyRef(fid=fid, prio=int(default_prio), explicit=False))
    return out


def _note_labels_by_nid(nids: set[int]) -> dict[int, str]:
    out: dict[int, str] = {}
    if not nids:
        return out
    if mw is None or not getattr(mw, "col", None):
        return out
    ids = sorted(int(x) for x in nids if int(x) > 0)
    if not ids:
        return out
    placeholders = ",".join("?" for _ in ids)
    try:
        rows = mw.col.db.all(
            f"select id, sfld from notes where id in ({placeholders})",
            *ids,
        )
    except Exception:
        return out
    for row in rows:
        try:
            nid = int(row[0])
        except Exception:
            continue
        label = str(row[1] or "").strip()
        out[nid] = label or str(nid)
    return out


def _family_prio_chain(current_nid: int) -> tuple[set[int], list[tuple[int, int]], dict[int, str]]:
    chain_nodes: set[int] = set()
    chain_edges: list[tuple[int, int]] = []
    labels: dict[int, str] = {}
    if current_nid <= 0:
        return chain_nodes, chain_edges, labels
    if mw is None or not getattr(mw, "col", None):
        return chain_nodes, chain_edges, labels

    try:
        note = mw.col.get_note(int(current_nid))
    except Exception:
        return chain_nodes, chain_edges, labels

    family_field, family_sep, default_prio = _family_cfg()
    if family_field not in note:
        return chain_nodes, chain_edges, labels

    cur_refs = _parse_family_refs(str(note[family_field] or ""), family_sep, default_prio)
    if not cur_refs:
        return chain_nodes, chain_edges, labels

    fids = sorted({r.fid for r in cur_refs if r.fid})
    if not fids:
        return chain_nodes, chain_edges, labels

    edge_seen: set[tuple[int, int]] = set()
    for fid in fids:
        like = f"%{fid}%"
        try:
            rows = mw.col.db.all("select id from notes where flds like ?", like)
        except Exception:
            rows = []
        nids = {int(current_nid)}
        for row in rows:
            try:
                nids.add(int(row[0]))
            except Exception:
                continue

        by_prio: dict[int, set[int]] = {}
        explicit_any = False
        for nid in sorted(nids):
            try:
                n = mw.col.get_note(int(nid))
            except Exception:
                continue
            if family_field not in n:
                continue
            refs = _parse_family_refs(str(n[family_field] or ""), family_sep, default_prio)
            for ref in refs:
                if ref.fid != fid:
                    continue
                by_prio.setdefault(int(ref.prio), set()).add(int(nid))
                if ref.explicit:
                    explicit_any = True

        prios = sorted(by_prio.keys())
        if len(prios) <= 1 and not explicit_any:
            continue

        for p in prios:
            chain_nodes.update(by_prio.get(p, set()))
        for i in range(len(prios) - 1):
            src_pr = prios[i]
            dst_pr = prios[i + 1]
            for src in by_prio.get(src_pr, set()):
                for dst in by_prio.get(dst_pr, set()):
                    if src == dst:
                        continue
                    key = (int(src), int(dst))
                    if key in edge_seen:
                        continue
                    edge_seen.add(key)
                    chain_edges.append(key)

    if chain_edges:
        forward: dict[int, set[int]] = {}
        reverse: dict[int, set[int]] = {}
        for src, dst in chain_edges:
            forward.setdefault(int(src), set()).add(int(dst))
            reverse.setdefault(int(dst), set()).add(int(src))

        # Keep only the subgraph that is actually connected to current note:
        # ancestors(current) U descendants(current) U current.
        relevant: set[int] = {int(current_nid)}
        stack = [int(current_nid)]
        while stack:
            cur = int(stack.pop())
            for parent in reverse.get(cur, set()):
                if parent in relevant:
                    continue
                relevant.add(parent)
                stack.append(parent)
        stack = [int(current_nid)]
        while stack:
            cur = int(stack.pop())
            for child in forward.get(cur, set()):
                if child in relevant:
                    continue
                relevant.add(child)
                stack.append(child)

        filtered_edges: list[tuple[int, int]] = []
        for src, dst in chain_edges:
            if int(src) in relevant and int(dst) in relevant:
                filtered_edges.append((int(src), int(dst)))
        chain_edges = filtered_edges
        chain_nodes = {int(n) for n in chain_nodes if int(n) in relevant}
        chain_nodes.add(int(current_nid))

    if chain_nodes:
        labels = _note_labels_by_nid(set(chain_nodes))
    return chain_nodes, chain_edges, labels


def _accent_colors_for_nids(nids: set[int]) -> dict[int, str]:
    out: dict[int, str] = {}
    if not nids:
        return out
    if mw is None or not getattr(mw, "col", None):
        return out

    mid_cache: dict[int, str] = {}
    for nid in sorted(int(x) for x in nids if int(x) > 0):
        try:
            note = mw.col.get_note(int(nid))
            mid = int(note.mid)
        except Exception:
            continue
        if mid not in mid_cache:
            color = ""
            try:
                model = mw.col.models.get(mid)
                css = str(model.get("css", "") or "") if isinstance(model, dict) else ""
                m = re.search(r"--accent\s*:\s*([^;]+);", css, re.IGNORECASE)
                if m:
                    color = str(m.group(1) or "").strip()
            except Exception:
                color = ""
            mid_cache[mid] = color
        if mid_cache.get(mid):
            out[int(nid)] = mid_cache[mid]
    return out


def _cid_note_data(cids: set[int]) -> dict[int, tuple[int, str]]:
    out: dict[int, tuple[int, str]] = {}
    if not cids:
        return out
    if mw is None or not getattr(mw, "col", None):
        return out
    ids = sorted(int(x) for x in cids if int(x) > 0)
    if not ids:
        return out
    placeholders = ",".join("?" for _ in ids)
    try:
        rows = mw.col.db.all(
            f"select c.id, n.id, n.sfld from cards c join notes n on n.id = c.nid where c.id in ({placeholders})",
            *ids,
        )
    except Exception:
        return out
    for row in rows:
        try:
            cid = int(row[0])
            nid = int(row[1])
        except Exception:
            continue
        label = str(row[2] or "").strip() or str(nid)
        out[cid] = (nid, label)
    return out


def _current_nid(browser) -> int:
    try:
        card = getattr(browser, "card", None)
        if card is not None:
            return int(card.note().id)
    except Exception:
        pass
    try:
        nids = list(browser.selectedNotes() or [])
        if nids:
            return int(nids[0])
    except Exception:
        pass
    return 0


def _current_cid(browser) -> int:
    try:
        card = getattr(browser, "card", None)
        if card is not None:
            return int(card.id)
    except Exception:
        pass
    return 0


def _current_card(browser):
    try:
        card = getattr(browser, "card", None)
        if card is not None:
            return card
    except Exception:
        pass
    nid = _current_nid(browser)
    if nid <= 0:
        return None
    if mw is None or not getattr(mw, "col", None):
        return None
    try:
        note = mw.col.get_note(int(nid))
    except Exception:
        return None
    try:
        cards = note.cards()
    except Exception:
        cards = []
    return cards[0] if cards else None


def _collect_manual_outgoing(nid: int) -> list[ParsedLink]:
    if nid <= 0:
        return []
    if mw is None or not getattr(mw, "col", None):
        return []
    try:
        note = mw.col.get_note(int(nid))
    except Exception:
        return []
    seen: set[tuple[str, int, str]] = set()
    out: list[ParsedLink] = []
    for field in list(getattr(note, "fields", []) or []):
        for ref in _parse_raw_links(str(field or "")):
            key = (ref.kind, int(ref.target_id), str(ref.label))
            if key in seen:
                continue
            seen.add(key)
            out.append(ref)
    return out


def _provider_refs(payload) -> list[ParsedLink]:
    out: list[ParsedLink] = []
    links = getattr(payload, "links", None) or []
    groups = getattr(payload, "groups", None) or []

    for ref in links:
        try:
            out.append(
                ParsedLink(
                    label=str(getattr(ref, "label", "") or ""),
                    kind=str(getattr(ref, "kind", "nid") or "nid").lower(),
                    target_id=int(getattr(ref, "target_id", 0) or 0),
                )
            )
        except Exception:
            continue
    for grp in groups:
        summary = getattr(grp, "summary", None)
        if summary is not None:
            try:
                out.append(
                    ParsedLink(
                        label=str(getattr(summary, "label", "") or ""),
                        kind=str(getattr(summary, "kind", "nid") or "nid").lower(),
                        target_id=int(getattr(summary, "target_id", 0) or 0),
                    )
                )
            except Exception:
                pass
        for ref in (getattr(grp, "links", None) or []):
            try:
                out.append(
                    ParsedLink(
                        label=str(getattr(ref, "label", "") or ""),
                        kind=str(getattr(ref, "kind", "nid") or "nid").lower(),
                        target_id=int(getattr(ref, "target_id", 0) or 0),
                    )
                )
            except Exception:
                continue
    return out


def _iter_link_core_providers():
    try:
        from . import link_core
    except Exception:
        return []
    try:
        items = list(link_core._iter_providers())  # type: ignore[attr-defined]
        return items
    except Exception:
        pass
    providers = getattr(link_core, "_PROVIDERS", {})
    out: list[tuple[str, int, Any]] = []
    if isinstance(providers, dict):
        for provider_id, payload in providers.items():
            try:
                prio, fn = payload
                out.append((str(provider_id), int(prio), fn))
            except Exception:
                continue
    out.sort(key=lambda x: (x[1], x[0]))
    return out


def _provider_category(provider_id: str) -> str:
    pid = str(provider_id or "").strip().lower()
    if pid == "family_priority" or pid.startswith("family_") or "family" in pid:
        return "family"
    if (
        pid == "mass_linker"
        or pid == "note_linker"
        or pid.startswith("mass_")
        or "mass" in pid
        or "note_linker" in pid
    ):
        return "mass"
    return "other"


def _collect_auto_outgoing(card, manual_refs: list[ParsedLink]) -> list[tuple[str, ParsedLink]]:
    if card is None:
        return []
    if mw is None or not getattr(mw, "col", None):
        return []
    try:
        note = card.note()
    except Exception:
        return []

    try:
        from . import link_core
    except Exception:
        return []

    base_nids = {int(ref.target_id) for ref in manual_refs if ref.kind == "nid"}
    base_cids = {int(ref.target_id) for ref in manual_refs if ref.kind == "cid"}

    seen: set[tuple[str, int, str]] = set()
    out: list[tuple[str, ParsedLink]] = []
    for kind in ("reviewQuestion", "reviewAnswer"):
        known_nids = set(base_nids)
        known_cids = set(base_cids)
        for provider_id, _prio, provider in _iter_link_core_providers():
            try:
                ctx = link_core.ProviderContext(
                    card=card,
                    kind=kind,
                    note=note,
                    html="",
                    existing_nids=set(known_nids),
                    existing_cids=set(known_cids),
                )
                payloads = provider(ctx) or []
            except Exception:
                continue
            category = _provider_category(provider_id)
            if category not in ("family", "mass"):
                continue
            for payload in payloads:
                for ref in _provider_refs(payload):
                    if ref.target_id <= 0:
                        continue
                    key = (ref.kind, int(ref.target_id), str(ref.label))
                    if key in seen:
                        continue
                    seen.add(key)
                    out.append((category, ref))
                    if ref.kind == "cid":
                        known_cids.add(int(ref.target_id))
                    else:
                        known_nids.add(int(ref.target_id))
    return out


def _collect_incoming(nid: int, cid: int) -> list[tuple[int, ParsedLink]]:
    if not nid and not cid:
        return []
    if mw is None or not getattr(mw, "col", None):
        return []

    queries: list[tuple[str, int]] = []
    if nid > 0:
        queries.append(("nid", int(nid)))
    if cid > 0:
        queries.append(("cid", int(cid)))

    seen: set[tuple[int, str, int, str]] = set()
    out: list[tuple[int, ParsedLink]] = []
    for kind, target in queries:
        like = f"%|{kind}{target}]%"
        try:
            rows = mw.col.db.all(
                "select id, flds from notes where id != ? and flds like ?",
                int(nid) if nid > 0 else -1,
                like,
            )
        except Exception:
            continue
        for src_nid_raw, flds in rows:
            try:
                src_nid = int(src_nid_raw)
            except Exception:
                continue
            for field_text in str(flds or "").split("\x1f"):
                for ref in _parse_raw_links(field_text):
                    if ref.kind != kind or int(ref.target_id) != target:
                        continue
                    key = (src_nid, ref.kind, int(ref.target_id), str(ref.label))
                    if key in seen:
                        continue
                    seen.add(key)
                    out.append((src_nid, ref))
    return out


def _set_list_items(widget: QListWidget, values: list[PanelItem], empty_text: str) -> None:
    widget.clear()
    if not values:
        item = QListWidgetItem(empty_text)
        item.setData(
            Qt.ItemDataRole.UserRole,
            {"open_nid": 0, "link_kind": "", "link_id": 0, "bucket": "", "is_header": False},
        )
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
        widget.addItem(item)
        return
    for row in values:
        item = QListWidgetItem(row.text)
        item.setData(
            Qt.ItemDataRole.UserRole,
            {
                "open_nid": int(row.open_nid) if int(row.open_nid) > 0 else 0,
                "link_kind": str(row.link_kind or "").lower(),
                "link_id": int(row.link_id) if int(row.link_id) > 0 else 0,
                "bucket": str(row.bucket or "").strip().lower(),
                "is_header": bool(row.is_header),
            },
        )
        if not bool(row.clickable):
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
        if bool(row.is_header):
            font = QFont(item.font())
            font.setBold(True)
            item.setFont(font)
            item.setForeground(QBrush(QColor("#9aa0aa")))
        elif not bool(row.clickable):
            item.setForeground(QBrush(QColor("#7d838a")))
        widget.addItem(item)
    _apply_list_item_heights(widget, max_lines=2)


def _apply_list_item_heights(widget: QListWidget, *, max_lines: int = 2) -> None:
    if widget is None:
        return
    try:
        avail_w = max(40, int(widget.viewport().width()) - 14)
    except Exception:
        return
    fm = widget.fontMetrics()
    line_h = max(1, int(fm.lineSpacing()))
    wrap_flags = int(Qt.TextFlag.TextWordWrap | Qt.AlignmentFlag.AlignLeft)
    for i in range(widget.count()):
        item = widget.item(i)
        if item is None:
            continue
        text = str(item.text() or "")
        open_nid, _kind, _link_id, _bucket, is_header = _item_meta(item)
        is_sep = (open_nid <= 0) and (not is_header) and text.strip("-").strip() == ""
        if is_sep:
            h = max(6, int(line_h * 0.6))
            item.setSizeHint(QSize(0, h))
            continue
        if is_header:
            h = max(line_h + 8, int(line_h * 1.35))
            item.setSizeHint(QSize(0, h))
            continue
        rect = fm.boundingRect(0, 0, avail_w, 2000, wrap_flags, text)
        lines = max(1, int((rect.height() + line_h - 1) // line_h))
        lines = min(max(1, int(max_lines)), lines)
        h = max(line_h + 8, int(lines * line_h + 8))
        item.setSizeHint(QSize(0, h))


def _open_note_editor(nid: int) -> None:
    open_note_editor(int(nid), title="AJpC Note Editor")


def _open_note_preview(nid: int) -> None:
    if nid <= 0:
        return
    if mw is None or not getattr(mw, "col", None):
        return
    try:
        note = mw.col.get_note(int(nid))
    except Exception:
        return
    try:
        cards = note.cards()
    except Exception:
        cards = []
    if not cards:
        return
    card = cards[0]

    class _SingleCardPreviewer(Previewer):
        def __init__(self, card: Card, mw, on_close):
            self._card = card
            super().__init__(parent=None, mw=mw, on_close=on_close)

        def card(self) -> Card | None:
            return self._card

        def card_changed(self) -> bool:
            return False

    previewers = getattr(mw, "_ajpc_browser_graph_previewers", None)
    if not isinstance(previewers, list):
        previewers = []
        mw._ajpc_browser_graph_previewers = previewers

    previewer: _SingleCardPreviewer | None = None

    def _on_close() -> None:
        if previewer in previewers:
            previewers.remove(previewer)

    previewer = _SingleCardPreviewer(card, mw, _on_close)
    previewers.append(previewer)
    previewer.open()


def _find_companion_graph_open_callback():
    if mw is None:
        return None
    reg = getattr(mw, "_ajpc_menu_registry", None)
    if not isinstance(reg, dict):
        return None
    top_items = list(reg.get("top_internal", []) or []) + list(reg.get("top_external", []) or [])
    for item in top_items:
        label = str(item.get("label", "") or "").strip().lower()
        if label != "show graph":
            continue
        cb = item.get("callback")
        if callable(cb):
            return cb
    return None


def _focus_companion_graph_note(nid: int, attempt: int = 1) -> None:
    if mw is None:
        return
    target = int(nid or 0)
    if target <= 0:
        return
    win = getattr(mw, "_ajpc_tools_graph_win", None)
    if win is not None and hasattr(win, "_request_focus_note_in_graph"):
        try:
            win._request_focus_note_in_graph(target)
            logging.dbg("browser graph: focused companion graph note", target, source="browser_graph")
        except Exception as exc:
            logging.warn(
                "browser graph: focus companion graph note failed",
                target,
                repr(exc),
                source="browser_graph",
            )
        return
    if attempt >= 25:
        logging.warn("browser graph: companion graph window not available", target, source="browser_graph")
        return
    QTimer.singleShot(120, lambda n=target, a=attempt + 1: _focus_companion_graph_note(n, a))


def _show_note_in_ajpc_graph(nid: int) -> None:
    target = int(nid or 0)
    if target <= 0:
        return
    cb = _find_companion_graph_open_callback()
    if not callable(cb):
        logging.warn("browser graph: companion graph callback missing", source="browser_graph")
        return
    try:
        cb()
        logging.dbg("browser graph: companion graph open requested", target, source="browser_graph")
    except Exception as exc:
        logging.warn("browser graph: companion graph open failed", repr(exc), source="browser_graph")
        return
    _focus_companion_graph_note(target, 1)


def _item_meta(item: QListWidgetItem) -> tuple[int, str, int, str, bool]:
    raw = item.data(Qt.ItemDataRole.UserRole)
    if not isinstance(raw, dict):
        return 0, "", 0, "", False
    try:
        open_nid = int(raw.get("open_nid", 0) or 0)
    except Exception:
        open_nid = 0
    kind = str(raw.get("link_kind", "") or "").lower().strip()
    try:
        link_id = int(raw.get("link_id", 0) or 0)
    except Exception:
        link_id = 0
    bucket = str(raw.get("bucket", "") or "").lower().strip()
    is_header = bool(raw.get("is_header", False))
    return open_nid, kind, link_id, bucket, is_header


def _copy_text(value: str) -> None:
    try:
        QApplication.clipboard().setText(str(value))
    except Exception:
        return


def _on_item_double_clicked(item: QListWidgetItem) -> None:
    try:
        open_nid, _kind, _link_id, _bucket, _is_header = _item_meta(item)
    except Exception:
        open_nid = 0
    if open_nid > 0:
        _open_note_editor(open_nid)


def _panel_for_item(item: QListWidgetItem):
    lw = item.listWidget()
    if lw is None:
        return None
    w = lw.parentWidget()
    while w is not None:
        if hasattr(w, "graph_view"):
            return w
        w = w.parentWidget()
    return None


def _on_item_clicked(item: QListWidgetItem) -> None:
    panel = _panel_for_item(item)
    if panel is None:
        return
    gv = getattr(panel, "graph_view", None)
    if gv is None:
        return
    pv = getattr(panel, "prio_view", None)
    try:
        open_nid, _kind, _link_id, bucket, is_header = _item_meta(item)
    except Exception:
        return
    if is_header and bucket:
        if pv is not None:
            pv.select_nid(0)
        gv.highlight_bucket(bucket)
        return
    if open_nid > 0:
        if pv is not None:
            pv.select_nid(int(open_nid))
        gv.select_nid(int(open_nid))
        gv.highlight_nid(int(open_nid))
        return
    if pv is not None:
        pv.select_nid(0)
    gv.clear_highlight()


def _show_item_menu(widget: QListWidget, pos) -> None:
    item = widget.itemAt(pos)
    if item is None:
        return
    open_nid, kind, link_id, _bucket, is_header = _item_meta(item)
    if is_header:
        return
    if not (open_nid > 0 or (kind in ("nid", "cid") and link_id > 0)):
        return

    menu = QMenu(widget)
    action_editor = None
    action_preview = None
    action_show_graph = None
    action_copy_nid = None
    action_copy_cid = None

    if open_nid > 0:
        action_editor = menu.addAction("Open Editor")
        action_preview = menu.addAction("Open Preview")
        action_show_graph = menu.addAction("Show in AJpC Graph")
    if open_nid > 0 and (kind in ("nid", "cid") and link_id > 0):
        menu.addSeparator()
    if kind == "nid" and link_id > 0:
        action_copy_nid = menu.addAction("Copy Note ID")
    if kind == "cid" and link_id > 0:
        action_copy_cid = menu.addAction("Copy Card ID")

    chosen = menu.exec(widget.mapToGlobal(pos))
    if chosen is action_editor and open_nid > 0:
        _open_note_editor(open_nid)
        return
    if chosen is action_preview and open_nid > 0:
        _open_note_preview(open_nid)
        return
    if chosen is action_show_graph and open_nid > 0:
        _show_note_in_ajpc_graph(open_nid)
        return
    if chosen is action_copy_nid and kind == "nid" and link_id > 0:
        _copy_text(str(link_id))
        return
    if chosen is action_copy_cid and kind == "cid" and link_id > 0:
        _copy_text(str(link_id))
        return


def _show_note_context_menu(widget: QWidget, nid: int) -> None:
    target = int(nid or 0)
    if target <= 0:
        return
    menu = QMenu(widget)
    action_editor = menu.addAction("Open Editor")
    action_preview = menu.addAction("Open Preview")
    action_show_graph = menu.addAction("Show in AJpC Graph")
    menu.addSeparator()
    action_copy_nid = menu.addAction("Copy Note ID")

    chosen = menu.exec(QCursor.pos())
    if chosen is action_editor:
        _open_note_editor(target)
        return
    if chosen is action_preview:
        _open_note_preview(target)
        return
    if chosen is action_show_graph:
        _show_note_in_ajpc_graph(target)
        return
    if chosen is action_copy_nid:
        _copy_text(str(target))


def _select_item_by_nid(widget: QListWidget, nid: int) -> bool:
    target = int(nid or 0)
    if target <= 0:
        return False
    for i in range(widget.count()):
        item = widget.item(i)
        if item is None:
            continue
        open_nid, _kind, _link_id, _bucket, is_header = _item_meta(item)
        if is_header:
            continue
        if int(open_nid) != target:
            continue
        widget.setCurrentItem(item)
        widget.scrollToItem(item)
        return True
    return False


def _sync_list_selection_from_graph(panel, nid: int) -> None:
    try:
        panel.outgoing_list.clearSelection()
        panel.outgoing_list.setCurrentRow(-1)
        panel.incoming_list.clearSelection()
        panel.incoming_list.setCurrentRow(-1)
    except Exception:
        pass
    target = int(nid or 0)
    pv = getattr(panel, "prio_view", None)
    if pv is not None:
        pv.select_nid(target)
    if target <= 0:
        gv = getattr(panel, "graph_view", None)
        if gv is not None:
            gv.clear_highlight()
        return
    if _select_item_by_nid(panel.outgoing_list, target):
        gv = getattr(panel, "graph_view", None)
        if gv is not None:
            gv.select_nid(target)
            gv.highlight_nid(target)
        return
    _select_item_by_nid(panel.incoming_list, target)
    gv = getattr(panel, "graph_view", None)
    if gv is not None:
        gv.select_nid(target)
        gv.highlight_nid(target)


def _on_prio_needed_height(panel, height: int) -> None:
    if panel is None:
        return
    try:
        h = int(height)
    except Exception:
        return
    if h <= 0:
        return
    fn = getattr(panel, "set_prio_data_visible", None)
    if callable(fn):
        fn(bool(getattr(panel, "_has_prio_data", False)), height=h)


def _toggle_browser_graph_panel(editor: Editor) -> None:
    browser = getattr(editor, "parentWindow", None)
    if browser is None:
        return
    panel = getattr(browser, "_ajpc_browser_graph_panel", None)
    if panel is None:
        _attach_panel(browser)
        panel = getattr(browser, "_ajpc_browser_graph_panel", None)
    if panel is None:
        return
    current = bool(getattr(panel, "_links_user_visible", True))
    panel._links_user_visible = not current
    _refresh_panel(browser)


def _toggle_browser_graph_canvas(editor: Editor) -> None:
    browser = getattr(editor, "parentWindow", None)
    if browser is None:
        return
    panel = getattr(browser, "_ajpc_browser_graph_panel", None)
    if panel is None:
        _attach_panel(browser)
        panel = getattr(browser, "_ajpc_browser_graph_panel", None)
    if panel is None:
        return
    current = bool(getattr(panel, "_graph_user_visible", True))
    panel._graph_user_visible = not current
    _refresh_panel(browser)


def _toggle_browser_graph_prio(editor: Editor) -> None:
    browser = getattr(editor, "parentWindow", None)
    if browser is None:
        return
    panel = getattr(browser, "_ajpc_browser_graph_panel", None)
    if panel is None:
        _attach_panel(browser)
        panel = getattr(browser, "_ajpc_browser_graph_panel", None)
    if panel is None:
        return
    current = bool(getattr(panel, "_prio_user_visible", True))
    panel._prio_user_visible = not current
    _refresh_panel(browser)


def _inject_editor_toggle_buttons(buttons: list[str], editor: Editor) -> None:
    try:
        mode = getattr(editor, "editorMode", None)
    except Exception:
        mode = None
    if mode not in (aqt.editor.EditorMode.BROWSER, aqt.editor.EditorMode.EDIT_CURRENT):
        return
    if mode == aqt.editor.EditorMode.EDIT_CURRENT:
        try:
            parent = getattr(editor, "parentWindow", None)
            if parent is None or getattr(parent, "_ajpc_browser_graph_panel", None) is None:
                return
        except Exception:
            return
    list_btn = editor.addButton(
        icon=None,
        cmd="_ajpc_browser_graph_toggle",
        func=_toggle_browser_graph_panel,
        tip="Toggle Link Lists",
        label="List",
        disables=False,
    )
    graph_btn = editor.addButton(
        icon=None,
        cmd="_ajpc_browser_graph_toggle_graph",
        func=_toggle_browser_graph_canvas,
        tip="Toggle Force Graph",
        label="Graph",
        disables=False,
    )
    prio_btn = editor.addButton(
        icon=None,
        cmd="_ajpc_browser_graph_toggle_prio",
        func=_toggle_browser_graph_prio,
        tip="Toggle Dependency Tree",
        label="Deps",
        disables=False,
    )
    buttons.append(list_btn)
    buttons.append(graph_btn)
    buttons.append(prio_btn)


def _label_from_ref(ref: ParsedLink) -> str:
    return (ref.label or "").strip() or "Link"


def _note_label(nid: int) -> str:
    if nid <= 0:
        return "Current"
    if mw is None or not getattr(mw, "col", None):
        return str(nid)
    try:
        val = mw.col.db.scalar("select sfld from notes where id = ?", int(nid))
    except Exception:
        val = None
    txt = str(val or "").strip()
    return txt or str(nid)


def _sectioned_items(
    sections: list[tuple[str, str, list[PanelItem]]],
) -> list[PanelItem]:
    out: list[PanelItem] = []
    present = [(title, bucket, items) for title, bucket, items in sections if items]
    for _i, (title, bucket, items) in enumerate(present):
        out.append(
            PanelItem(
                text=title,
                open_nid=0,
                link_kind="",
                link_id=0,
                bucket=bucket,
                is_header=True,
                clickable=True,
            )
        )
        out.extend(items)
    return out


def _build_force_graph_payload(
    current_nid: int,
    outgoing_manual: list[PanelItem],
    outgoing_family: list[PanelItem],
    outgoing_mass: list[PanelItem],
    incoming_manual: list[PanelItem],
    family_prio_nodes: set[int],
    family_prio_edges: list[tuple[int, int]],
    family_prio_labels: dict[int, str],
) -> dict[str, Any]:
    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []

    involved_nids: set[int] = {int(current_nid)}
    involved_nids.update(int(it.open_nid) for it in outgoing_manual if int(it.open_nid) > 0)
    involved_nids.update(int(it.open_nid) for it in outgoing_family if int(it.open_nid) > 0)
    involved_nids.update(int(it.open_nid) for it in outgoing_mass if int(it.open_nid) > 0)
    involved_nids.update(int(it.open_nid) for it in incoming_manual if int(it.open_nid) > 0)
    involved_nids.update(int(x) for x in family_prio_nodes if int(x) > 0)
    accent_by_nid = _accent_colors_for_nids(involved_nids)

    cur_id = f"n{int(current_nid)}"
    nodes[cur_id] = {
        "id": cur_id,
        "nid": int(current_nid),
        "label": _note_label(int(current_nid)),
        "role": "current",
        "bucket": "manual",
        "color": accent_by_nid.get(int(current_nid), ""),
    }

    def _ensure(nid: int, label: str, bucket: str) -> str | None:
        if int(nid) <= 0:
            return None
        node_id = f"n{int(nid)}"
        if node_id not in nodes:
            nodes[node_id] = {
                "id": node_id,
                "nid": int(nid),
                "label": str(label or "").strip() or _note_label(int(nid)),
                "role": "linked",
                "bucket": str(bucket or "manual"),
                "color": accent_by_nid.get(int(nid), ""),
            }
        elif str(bucket or "") == "family_prio":
            nodes[node_id]["bucket"] = "family_prio"
            if str(label or "").strip():
                nodes[node_id]["label"] = str(label).strip()
            if accent_by_nid.get(int(nid)):
                nodes[node_id]["color"] = accent_by_nid.get(int(nid), "")
        return node_id

    def _add_out(items: list[PanelItem], bucket: str, skip_nids: set[int] | None = None) -> None:
        for it in items:
            nid = int(it.open_nid or 0)
            if skip_nids and nid in skip_nids:
                continue
            target = _ensure(nid, str(it.text or ""), bucket)
            if not target:
                continue
            edges.append(
                {
                    "source": cur_id,
                    "target": target,
                    "bucket": bucket,
                    "direction": "outgoing",
                    "kind": str(it.link_kind or ""),
                }
            )

    def _add_in(items: list[PanelItem], bucket: str) -> None:
        for it in items:
            nid = int(it.open_nid or 0)
            source = _ensure(nid, str(it.text or ""), bucket)
            if not source:
                continue
            edges.append(
                {
                    "source": source,
                    "target": cur_id,
                    "bucket": bucket,
                    "direction": "incoming",
                    "kind": str(it.link_kind or ""),
                }
            )

    _add_out(outgoing_manual, "manual")
    chain_edge_nids: set[int] = set()
    for src_nid, dst_nid in family_prio_edges:
        if int(src_nid) > 0:
            chain_edge_nids.add(int(src_nid))
        if int(dst_nid) > 0:
            chain_edge_nids.add(int(dst_nid))
    # Only suppress direct family edges when there is an actual prio chain edge.
    _add_out(
        outgoing_family,
        "family",
        skip_nids=chain_edge_nids if family_prio_edges and chain_edge_nids else None,
    )
    _add_out(outgoing_mass, "mass")
    _add_in(incoming_manual, "manual")

    for nid in sorted(family_prio_nodes):
        _ensure(int(nid), family_prio_labels.get(int(nid), ""), "family_prio")
    for src_nid, dst_nid in family_prio_edges:
        src = _ensure(int(src_nid), family_prio_labels.get(int(src_nid), ""), "family_prio")
        dst = _ensure(int(dst_nid), family_prio_labels.get(int(dst_nid), ""), "family_prio")
        if not src or not dst:
            continue
        edges.append(
            {
                "source": src,
                "target": dst,
                "bucket": "family_prio",
                "direction": "outgoing",
                "kind": "nid",
            }
        )

    return {
        "nodes": list(nodes.values()),
        "edges": edges,
        "current_id": cur_id,
    }


def _build_prio_chain_payload(
    current_nid: int,
    family_prio_nodes: set[int],
    family_prio_edges: list[tuple[int, int]],
    family_prio_labels: dict[int, str],
) -> dict[str, Any]:
    if not family_prio_nodes or not family_prio_edges:
        return {"nodes": [], "edges": [], "current_nid": int(current_nid)}
    nids = {int(x) for x in family_prio_nodes if int(x) > 0}
    colors = _accent_colors_for_nids(nids)
    nodes: list[dict[str, Any]] = []
    for nid in sorted(nids):
        nodes.append(
            {
                "id": f"n{nid}",
                "nid": int(nid),
                "label": str(family_prio_labels.get(int(nid), "") or _note_label(int(nid))),
                "color": str(colors.get(int(nid), "") or "#3d95e7"),
            }
        )
    edges: list[dict[str, Any]] = []
    for src, dst in family_prio_edges:
        s = int(src)
        d = int(dst)
        if s <= 0 or d <= 0:
            continue
        edges.append({"source": f"n{s}", "target": f"n{d}"})
    return {"nodes": nodes, "edges": edges, "current_nid": int(current_nid)}


def _prio_row_count(current_nid: int, edges: list[tuple[int, int]]) -> int:
    cur = int(current_nid or 0)
    if cur <= 0:
        return 0
    if not edges:
        return 0
    outs: dict[int, set[int]] = {}
    preds: dict[int, set[int]] = {}
    nodes: set[int] = {cur}
    for src, dst in edges:
        s = int(src)
        d = int(dst)
        if s <= 0 or d <= 0:
            continue
        outs.setdefault(s, set()).add(d)
        preds.setdefault(d, set()).add(s)
        nodes.add(s)
        nodes.add(d)
    if not nodes:
        return 0
    depth: dict[int, int] = {cur: 0}
    q = [cur]
    while q:
        nid = int(q.pop(0))
        base = int(depth.get(nid, 0))
        for p in preds.get(nid, set()):
            nd = base - 1
            if p not in depth or nd < int(depth[p]):
                depth[p] = nd
                q.append(int(p))
    q = [cur]
    while q:
        nid = int(q.pop(0))
        base = int(depth.get(nid, 0))
        for c in outs.get(nid, set()):
            nd = base + 1
            if c not in depth or nd > int(depth[c]):
                depth[c] = nd
                q.append(int(c))
    if not depth:
        return 0
    return max(1, len(set(int(v) for v in depth.values())))


def _estimate_prio_needed_height(
    current_nid: int,
    family_prio_nodes: set[int],
    family_prio_edges: list[tuple[int, int]],
    family_prio_labels: dict[int, str],
    view_width: int,
) -> int:
    cur = int(current_nid or 0)
    if cur <= 0 or not family_prio_edges:
        return 0

    outs: dict[int, set[int]] = {}
    preds: dict[int, set[int]] = {}
    nodes: set[int] = {cur}
    for src, dst in family_prio_edges:
        s = int(src)
        d = int(dst)
        if s <= 0 or d <= 0:
            continue
        outs.setdefault(s, set()).add(d)
        preds.setdefault(d, set()).add(s)
        nodes.add(s)
        nodes.add(d)
    nodes.update(int(x) for x in family_prio_nodes if int(x) > 0)
    if not nodes:
        return 0

    depth: dict[int, int] = {cur: 0}
    q = [cur]
    while q:
        nid = int(q.pop(0))
        base = int(depth.get(nid, 0))
        for p in preds.get(nid, set()):
            nd = base - 1
            if p not in depth or nd < int(depth[p]):
                depth[p] = nd
                q.append(int(p))
    q = [cur]
    while q:
        nid = int(q.pop(0))
        base = int(depth.get(nid, 0))
        for c in outs.get(nid, set()):
            nd = base + 1
            if c not in depth or nd > int(depth[c]):
                depth[c] = nd
                q.append(int(c))

    rows: dict[int, list[int]] = {}
    for nid in nodes:
        d = int(depth.get(int(nid), 0))
        rows.setdefault(d, []).append(int(nid))
    if not rows:
        return 0

    # Matches JS constants in modules/_link_core/dep_tree_view.py
    margin_y = 44
    pad_x = 7
    line_h = 12
    pad_y = 5
    max_lines = 3
    single_line_node_h = int(line_h + pad_y * 2)
    min_row_gap = single_line_node_h
    usable_w = max(120, int(view_width) - 72)

    def _char_w(ch: str) -> float:
        c = ord(ch) if ch else 0
        if c >= 0x2E80:
            return 10.4
        if ch in "MW@#%&":
            return 7.2
        if ch in "il.,'`:;!| ":
            return 3.2
        return 6.2

    def _text_w(text: str) -> float:
        return sum(_char_w(ch) for ch in str(text or ""))

    def _wrap_text(text: str, max_w: int, max_lines_in: int) -> list[str]:
        chars = list(str(text or "Node"))
        if not chars:
            return ["Node"]
        lines: list[str] = []
        cur = ""
        for ch in chars:
            nxt = cur + ch
            if _text_w(nxt) <= float(max_w) or not cur:
                cur = nxt
            else:
                lines.append(cur)
                cur = ch
                if len(lines) >= int(max_lines_in):
                    break
        if cur and len(lines) < int(max_lines_in):
            lines.append(cur)
        if len(lines) >= int(max_lines_in) and lines:
            ln = str(lines[max_lines_in - 1] or "")
            if ln:
                lines[max_lines_in - 1] = ln[:-1] + "..."
        return lines or ["Node"]

    def _pack_lanes(boxes: list[tuple[int, int]], min_gap: int, lane_w: int) -> list[list[tuple[int, int]]]:
        lanes: list[list[tuple[int, int]]] = []
        lane: list[tuple[int, int]] = []
        lane_used = 0
        for bw, bh in boxes:
            need = (min_gap + int(bw)) if lane else int(bw)
            if lane and (lane_used + need) > lane_w:
                lanes.append(lane)
                lane = [(int(bw), int(bh))]
                lane_used = int(bw)
            else:
                lane.append((int(bw), int(bh)))
                lane_used += need
        if lane:
            lanes.append(lane)
        return lanes

    total_rows_h = 0
    for d in sorted(rows.keys()):
        items = rows.get(d, [])
        if not items:
            continue
        n = len(items)
        min_gap = single_line_node_h if n > 1 else 0
        lane_gap = single_line_node_h
        max_label_w = max(
            24,
            min(
                150,
                int((usable_w - (min_gap * max(0, n - 1))) / max(1, n) - (pad_x * 2)),
            ),
        )

        def _row_boxes(label_max_w: int) -> list[tuple[int, int]]:
            out: list[tuple[int, int]] = []
            for nid in items:
                label = str(family_prio_labels.get(int(nid), "") or _note_label(int(nid)))
                lines = _wrap_text(label, int(label_max_w), max_lines)
                text_w = 0.0
                for line in lines:
                    text_w = max(text_w, _text_w(line))
                box_w = max(48, int(round(text_w + (pad_x * 2))))
                box_h = max(22, int(round((len(lines) * line_h) + (pad_y * 2))))
                out.append((box_w, box_h))
            return out

        dims = _row_boxes(max_label_w)
        lanes = _pack_lanes(dims, min_gap, usable_w)

        if len(lanes) > 1:
            max_label_w = max(
                24,
                int((usable_w - (min_gap * max(0, n - 1))) / max(1, (n + len(lanes) - 1) // len(lanes)) - (pad_x * 2)),
            )
            dims = _row_boxes(max_label_w)
            lanes = _pack_lanes(dims, min_gap, usable_w)

        lane_hs = [max((h for _w, h in lane), default=22) for lane in lanes]
        row_h = sum(lane_hs) + lane_gap * max(0, len(lane_hs) - 1)
        total_rows_h += int(max(22, row_h))

    row_count = len(rows)
    need = total_rows_h + (min_row_gap * max(0, row_count - 1)) + (margin_y * 2) + 8
    return int(max(96, min(2000, need)))


def _apply_prio_visibility(panel, *, has_data: bool, height: int | None = None) -> None:
    fn = getattr(panel, "set_prio_data_visible", None)
    if callable(fn):
        fn(bool(has_data), height=height)
        return
    pv = getattr(panel, "prio_view", None)
    if pv is not None:
        pv.setVisible(bool(has_data))


def _refresh_panel(browser) -> None:
    panel = getattr(browser, "_ajpc_browser_graph_panel", None)
    if panel is None:
        return
    if mw is None or not getattr(mw, "col", None):
        panel.outgoing_count.setText("Outgoing (0)")
        panel.incoming_count.setText("Incoming (0)")
        _set_list_items(panel.outgoing_list, [], "No links")
        _set_list_items(panel.incoming_list, [], "No links")
        try:
            panel.graph_view.set_data({"nodes": [], "edges": []})
            panel.graph_view.clear_highlight()
            panel.prio_view.set_data({"nodes": [], "edges": []})
            _apply_prio_visibility(panel, has_data=False)
            panel.set_link_counts(0, 0)
        except Exception:
            pass
        return

    nid = _current_nid(browser)
    cid = _current_cid(browser)
    card = _current_card(browser)
    if nid <= 0:
        panel.outgoing_count.setText("Outgoing (0)")
        panel.incoming_count.setText("Incoming (0)")
        _set_list_items(panel.outgoing_list, [], "Select one card")
        _set_list_items(panel.incoming_list, [], "Select one card")
        try:
            panel.graph_view.set_data({"nodes": [], "edges": []})
            panel.graph_view.clear_highlight()
            panel.prio_view.set_data({"nodes": [], "edges": []})
            _apply_prio_visibility(panel, has_data=False)
            panel.set_link_counts(0, 0)
        except Exception:
            pass
        return

    manual_outgoing = _collect_manual_outgoing(nid)
    auto_outgoing = _collect_auto_outgoing(card, manual_outgoing)
    incoming = _collect_incoming(nid, cid)

    target_cids = {ref.target_id for ref in manual_outgoing if ref.kind == "cid"}
    target_cids.update(ref.target_id for _cat, ref in auto_outgoing if ref.kind == "cid")
    cid_map = _cid_note_data(target_cids)

    def _out_item(ref: ParsedLink, bucket: str) -> PanelItem:
        open_nid = 0
        if ref.kind == "nid":
            open_nid = int(ref.target_id)
        elif ref.kind == "cid":
            target = cid_map.get(int(ref.target_id))
            if target is not None:
                open_nid = int(target[0])
        return PanelItem(
            text=_label_from_ref(ref),
            open_nid=open_nid,
            link_kind=str(ref.kind).lower(),
            link_id=int(ref.target_id),
            bucket=str(bucket or "").lower(),
        )

    outgoing_manual: list[PanelItem] = [_out_item(ref, "manual") for ref in manual_outgoing]
    outgoing_family: list[PanelItem] = []
    outgoing_mass: list[PanelItem] = []
    for cat, ref in auto_outgoing:
        if cat == "family":
            outgoing_family.append(_out_item(ref, "family"))
        elif cat == "mass":
            outgoing_mass.append(_out_item(ref, "mass"))

    incoming_manual: list[PanelItem] = []
    for src_nid, ref in incoming:
        incoming_manual.append(
            PanelItem(
                text=_label_from_ref(ref),
                open_nid=int(src_nid),
                link_kind=str(ref.kind).lower(),
                link_id=int(ref.target_id),
                bucket="manual",
            )
        )

    family_prio_nodes, family_prio_edges, family_prio_labels = _family_prio_chain(int(nid))

    outgoing_total = len(outgoing_manual) + len(outgoing_family) + len(outgoing_mass)
    incoming_total = len(incoming_manual)

    panel.outgoing_count.setText(f"Outgoing ({outgoing_total})")
    panel.incoming_count.setText(f"Incoming ({incoming_total})")
    panel.set_link_counts(outgoing_total, incoming_total)
    _set_list_items(
        panel.outgoing_list,
        _sectioned_items(
            [
                ("Manual Links", "manual", outgoing_manual),
                ("Family Links", "family", outgoing_family),
                ("Mass Linker Links", "mass", outgoing_mass),
            ]
        ),
        "No outgoing links",
    )
    _set_list_items(
        panel.incoming_list,
        _sectioned_items([("Manual Links", "manual", incoming_manual)]),
        "No incoming links",
    )
    try:
        prio_payload = _build_prio_chain_payload(
            int(nid),
            family_prio_nodes,
            family_prio_edges,
            family_prio_labels,
        )
        panel.prio_view.set_data(
            prio_payload
        )
        prio_need_h = _estimate_prio_needed_height(
            int(nid),
            family_prio_nodes,
            family_prio_edges,
            family_prio_labels,
            int(panel.splitter.width()),
        )
        _apply_prio_visibility(
            panel,
            has_data=bool((prio_payload.get("nodes") or []) and (prio_payload.get("edges") or [])),
            height=prio_need_h,
        )
        panel.graph_view.set_data(
            _build_force_graph_payload(
                int(nid),
                outgoing_manual,
                outgoing_family,
                outgoing_mass,
                incoming_manual,
                family_prio_nodes,
                family_prio_edges,
                family_prio_labels,
            )
        )
        panel.graph_view.clear_highlight()
    except Exception:
        pass


class _BrowserGraphPanel(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ajpcBrowserGraphPanel")
        self.setMinimumWidth(240)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self._resize_drag_active = False
        self._resize_start_global_x = 0
        self._resize_start_width = 0
        self._resize_grip_width = 8
        self._links_user_visible = True
        self._graph_user_visible = True
        self._prio_user_visible = True
        self._outgoing_items = 0
        self._incoming_items = 0
        self._has_prio_data = False
        self._prio_needed_height = 130
        self._initial_width_applied = False

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 0, 0, 0)
        root.setSpacing(6)

        self.splitter = QSplitter(Qt.Orientation.Vertical, self)
        self.splitter.setHandleWidth(0)
        self.splitter.setChildrenCollapsible(False)
        root.addWidget(self.splitter, 1)

        self.links_container = QWidget(self.splitter)
        self.links_layout = QVBoxLayout(self.links_container)
        self.links_layout.setContentsMargins(0, 0, 0, 0)
        self.links_layout.setSpacing(6)

        self.outgoing_count = QLabel("Outgoing (0)")
        self.outgoing_count.setStyleSheet(
            "font-size: 14px; font-weight: 600; padding-top: 6px; padding-bottom: 6px;"
        )
        self.outgoing_list = QListWidget()
        self.outgoing_list.setObjectName("ajpcBrowserGraphOutgoing")
        self.outgoing_list.setAlternatingRowColors(True)
        self.outgoing_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.outgoing_list.setWordWrap(True)
        self.outgoing_list.setTextElideMode(Qt.TextElideMode.ElideNone)
        self.outgoing_list.itemClicked.connect(_on_item_clicked)
        self.outgoing_list.itemDoubleClicked.connect(_on_item_double_clicked)
        self.outgoing_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.outgoing_list.customContextMenuRequested.connect(
            lambda pos, w=self.outgoing_list: _show_item_menu(w, pos)
        )
        self.links_layout.addWidget(self.outgoing_count)
        self.links_layout.addWidget(self.outgoing_list, 1)

        self.incoming_count = QLabel("Incoming (0)")
        self.incoming_count.setStyleSheet(
            "font-size: 14px; font-weight: 600; padding-top: 6px; padding-bottom: 6px;"
        )
        self.incoming_list = QListWidget()
        self.incoming_list.setObjectName("ajpcBrowserGraphIncoming")
        self.incoming_list.setAlternatingRowColors(True)
        self.incoming_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.incoming_list.setWordWrap(True)
        self.incoming_list.setTextElideMode(Qt.TextElideMode.ElideNone)
        self.incoming_list.itemClicked.connect(_on_item_clicked)
        self.incoming_list.itemDoubleClicked.connect(_on_item_double_clicked)
        self.incoming_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.incoming_list.customContextMenuRequested.connect(
            lambda pos, w=self.incoming_list: _show_item_menu(w, pos)
        )
        self.links_layout.addWidget(self.incoming_count)
        self.links_layout.addWidget(self.incoming_list, 1)

        self.prio_view = PrioChainView(self.splitter)
        self.prio_view.set_open_editor_handler(_open_note_editor)
        self.prio_view.set_select_handler(lambda nid, p=self: _sync_list_selection_from_graph(p, nid))
        self.prio_view.set_context_menu_handler(
            lambda nid, p=self: _show_note_context_menu(p.prio_view, int(nid))
        )
        self.prio_view.set_needed_height_handler(lambda h, p=self: _on_prio_needed_height(p, h))

        self.section_gap = QWidget(self.splitter)
        self.section_gap.setFixedHeight(5)
        self.section_gap.setStyleSheet("background: transparent;")

        self.graph_view = ForceGraphView(self.splitter)
        self.graph_view.set_open_editor_handler(_open_note_editor)
        self.graph_view.set_select_handler(lambda nid, p=self: _sync_list_selection_from_graph(p, nid))
        self.graph_view.set_context_menu_handler(
            lambda nid, p=self: _show_note_context_menu(p.graph_view, int(nid))
        )

        self.splitter.addWidget(self.links_container)
        self.splitter.addWidget(self.prio_view)
        self.splitter.addWidget(self.section_gap)
        self.splitter.addWidget(self.graph_view)
        self.splitter.setSizes([290, 150, 0, 210])
        self._sync_canvas_bg_to_list_alt()
        self._resize_handle = _PanelResizeHandle(self)
        self._resize_handle.setToolTip("Drag to resize AJpC panel")

    def resizeEvent(self, event) -> None:
        try:
            self._resize_handle.setGeometry(0, 0, self._resize_grip_width, self.height())
            self._resize_handle.raise_()
        except Exception:
            pass
        self._sync_canvas_bg_to_list_alt()
        _apply_list_item_heights(self.outgoing_list, max_lines=2)
        _apply_list_item_heights(self.incoming_list, max_lines=2)
        self._reflow_sections()
        super().resizeEvent(event)

    def _begin_resize(self, global_x: int) -> None:
        self._resize_drag_active = True
        self._initial_width_applied = True
        self._resize_start_global_x = int(global_x)
        self._resize_start_width = int(self.width())
        try:
            self._resize_handle.grabMouse()
        except Exception:
            pass

    def _update_resize(self, global_x: int) -> None:
        dx = self._resize_start_global_x - int(global_x)
        new_width = self._resize_start_width + dx
        new_width = max(240, min(980, int(new_width)))
        self.setFixedWidth(new_width)
        self._reflow_sections()

    def _end_resize(self) -> None:
        self._resize_drag_active = False
        try:
            self._resize_handle.releaseMouse()
        except Exception:
            pass
        self._reflow_sections()

    def apply_initial_sidebar_ratio(self, total_width: int, ratio: float = 0.30) -> None:
        if self._initial_width_applied:
            return
        try:
            total = int(total_width)
        except Exception:
            total = 0
        if total <= 0:
            return
        try:
            r = float(ratio)
        except Exception:
            r = 0.30
        if r <= 0.0 or r >= 1.0:
            r = 0.30
        target = int(round(total * r))
        target = max(240, min(980, target))
        self.setFixedWidth(target)
        self._initial_width_applied = True
        self._reflow_sections()

    def set_link_counts(self, outgoing: int, incoming: int) -> None:
        self._outgoing_items = max(0, int(outgoing))
        self._incoming_items = max(0, int(incoming))
        has_out = self._outgoing_items > 0
        has_in = self._incoming_items > 0
        self.outgoing_count.setVisible(has_out)
        self.outgoing_list.setVisible(has_out)
        self.incoming_count.setVisible(has_in)
        self.incoming_list.setVisible(has_in)
        if has_out and has_in:
            self.links_layout.setStretch(1, max(1, self._outgoing_items))
            self.links_layout.setStretch(3, max(1, self._incoming_items))
        elif has_out:
            self.links_layout.setStretch(1, 1)
            self.links_layout.setStretch(3, 0)
        elif has_in:
            self.links_layout.setStretch(1, 0)
            self.links_layout.setStretch(3, 1)
        else:
            self.links_layout.setStretch(1, 0)
            self.links_layout.setStretch(3, 0)
        self._reflow_sections()

    def set_prio_data_visible(self, has_data: bool, *, height: int | None = None) -> None:
        changed = False
        next_has = bool(has_data)
        if next_has != self._has_prio_data:
            self._has_prio_data = next_has
            changed = True
        if height is not None and int(height) > 0:
            next_h = int(max(96, min(2000, int(height))))
            if next_h != self._prio_needed_height:
                self._prio_needed_height = next_h
                changed = True
        if changed:
            self._reflow_sections()

    def _sync_canvas_bg_to_list_alt(self) -> None:
        try:
            pal = self.outgoing_list.palette()
            base = pal.color(QPalette.ColorRole.Base)
            alt = pal.color(QPalette.ColorRole.AlternateBase)
            c = base if float(base.lightnessF()) <= float(alt.lightnessF()) else alt
            hex_color = str(c.name() or "").strip() or "#1f1f1f"
        except Exception:
            hex_color = "#1f1f1f"
        try:
            self.graph_view.set_background(hex_color)
        except Exception:
            pass

    def _list_widget_content_height(self, widget: QListWidget) -> int:
        try:
            count = int(widget.count())
        except Exception:
            count = 0
        if count <= 0:
            return int(widget.frameWidth() * 2)
        row_h = 0
        try:
            row_h = int(widget.sizeHintForRow(0))
        except Exception:
            row_h = 0
        if row_h <= 0:
            try:
                row_h = int(widget.fontMetrics().height() + 8)
            except Exception:
                row_h = 20
        return int((widget.frameWidth() * 2) + (count * row_h) + 2)

    def _links_needed_height(self) -> int:
        has_out = self._outgoing_items > 0
        has_in = self._incoming_items > 0
        if not (has_out or has_in):
            return 0
        widgets_visible = 0
        needed = 0
        if has_out:
            widgets_visible += 2
            needed += int(self.outgoing_count.sizeHint().height())
            needed += self._list_widget_content_height(self.outgoing_list)
        if has_in:
            widgets_visible += 2
            needed += int(self.incoming_count.sizeHint().height())
            needed += self._list_widget_content_height(self.incoming_list)
        spacing = int(self.links_layout.spacing())
        if widgets_visible > 1 and spacing > 0:
            needed += spacing * (widgets_visible - 1)
        return int(max(0, needed))

    def _links_row_height(self) -> int:
        heights: list[int] = []
        for w in (self.outgoing_list, self.incoming_list):
            if not bool(w.isVisible()):
                continue
            h = 0
            try:
                if w.count() > 0:
                    h = int(w.sizeHintForRow(0))
            except Exception:
                h = 0
            if h <= 0:
                try:
                    h = int(w.fontMetrics().height() + 8)
                except Exception:
                    h = 20
            heights.append(max(1, int(h)))
        if not heights:
            return 20
        return int(max(heights))

    def _reflow_sections(self) -> None:
        splitter_h = int(self.splitter.height())
        splitter_w = int(self.splitter.width())
        if splitter_h <= 0 or splitter_w <= 0:
            return

        has_out = self._outgoing_items > 0
        has_in = self._incoming_items > 0
        links_visible = bool(self._links_user_visible and (has_out or has_in))
        prio_visible = bool(self._prio_user_visible and self._has_prio_data)
        graph_visible = bool(self._graph_user_visible)

        self.links_container.setVisible(links_visible)
        self.prio_view.setVisible(prio_visible)
        self.graph_view.setVisible(graph_visible)
        gap_visible = bool(links_visible and graph_visible and not prio_visible)
        self.section_gap.setVisible(gap_visible)

        gap_h = 5 if gap_visible else 0
        deps_h = int(self._prio_needed_height) if prio_visible else 0
        if prio_visible:
            reserve = 0
            if links_visible:
                reserve += 1
            if graph_visible:
                reserve += 1
            deps_h = max(0, min(int(deps_h), int(splitter_h - gap_h - reserve)))
        avail = max(0, splitter_h - deps_h - gap_h)
        list_h = 0
        graph_h = 0

        all_three = bool(links_visible and prio_visible and graph_visible)
        if all_three:
            # Preferred mode trigger: there is enough room for lists under the 50% graph gate.
            graph_50 = min(int(splitter_w), int(avail / 2))
            list_for_50 = max(0, avail - graph_50)
            list_needed = self._links_needed_height()
            two_blank_rows = 2 * self._links_row_height()
            list_target = max(0, int(list_needed + two_blank_rows))
            if list_needed > 0 and list_for_50 >= list_target and list_target <= avail:
                # New rule: list gets exact needed height + 2 blank rows, graph gets the rest.
                list_h = list_target
                graph_h = max(0, avail - list_h)
            else:
                # Fallback rule from previous behavior.
                list_min = int(splitter_h / 3)
                graph_max = int(splitter_h / 3)
                graph_pref = min(int(splitter_w), graph_max, avail)
                graph_h = max(0, graph_pref)
                list_h = max(0, avail - graph_h)
                if list_h < list_min:
                    reduce_by = list_min - list_h
                    graph_h = max(0, graph_h - reduce_by)
                    list_h = max(0, avail - graph_h)
        elif links_visible and graph_visible and not prio_visible:
            # No deps visible -> strict 1/2 : 1/2 split.
            graph_h = int(avail / 2)
            list_h = avail - graph_h
        elif prio_visible and graph_visible and not links_visible:
            # No lists -> graph takes remaining height after deps.
            graph_h = avail
            list_h = 0
        elif links_visible and prio_visible and not graph_visible:
            # No graph -> lists take remaining height after deps.
            graph_h = 0
            list_h = avail
        elif graph_visible:
            graph_h = avail
            list_h = 0
        elif links_visible:
            graph_h = 0
            list_h = avail

        sizes = [
            int(list_h if links_visible else 0),
            int(deps_h if prio_visible else 0),
            int(gap_h if gap_visible else 0),
            int(graph_h if graph_visible else 0),
        ]
        rem = splitter_h - sum(sizes)
        if rem != 0:
            if links_visible:
                sizes[0] += rem
            elif graph_visible:
                sizes[3] += rem
            elif prio_visible:
                sizes[1] += rem
            elif gap_visible:
                sizes[2] += rem
        self.splitter.setSizes(sizes)


class _PanelResizeHandle(QWidget):
    def __init__(self, panel: _BrowserGraphPanel) -> None:
        super().__init__(panel)
        self._panel = panel
        self.setCursor(Qt.CursorShape.SizeHorCursor)
        self.setStyleSheet("background: transparent;")

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._panel._begin_resize(int(event.globalPosition().x()))
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if getattr(self._panel, "_resize_drag_active", False):
            self._panel._update_resize(int(event.globalPosition().x()))
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if getattr(self._panel, "_resize_drag_active", False) and event.button() == Qt.MouseButton.LeftButton:
            self._panel._end_resize()
            event.accept()
            return
        super().mouseReleaseEvent(event)


def _attach_panel(browser) -> None:
    if getattr(browser, "_ajpc_browser_graph_panel", None) is not None:
        return
    form = getattr(browser, "form", None)
    if form is None:
        return
    row_layout = getattr(form, "horizontalLayout2", None)
    if row_layout is None:
        return
    panel = _BrowserGraphPanel(form.verticalLayoutWidget)
    row_layout.addWidget(panel)
    browser._ajpc_browser_graph_panel = panel
    _BROWSERS.add(browser)
    _apply_initial_sidebar_width(browser)
    try:
        QTimer.singleShot(0, lambda b=browser: _apply_initial_sidebar_width(b))
    except Exception:
        pass
    _refresh_panel(browser)


def _apply_initial_sidebar_width(browser) -> None:
    panel = getattr(browser, "_ajpc_browser_graph_panel", None)
    if panel is None:
        return
    try:
        if bool(getattr(panel, "_initial_width_applied", False)):
            return
    except Exception:
        return
    total = 0
    try:
        form = getattr(browser, "form", None)
        row_layout = getattr(form, "horizontalLayout2", None) if form is not None else None
        host = row_layout.parentWidget() if row_layout is not None else None
        if host is not None:
            total = int(host.width())
    except Exception:
        total = 0
    if total <= 0:
        try:
            total = int(browser.width())
        except Exception:
            total = 0
    if total <= 0:
        return
    fn = getattr(panel, "apply_initial_sidebar_ratio", None)
    if callable(fn):
        fn(int(total), ratio=0.30)


def _on_browser_will_show(browser) -> None:
    _attach_panel(browser)


def _on_browser_did_change_row(browser) -> None:
    _refresh_panel(browser)


def _changes_matter_for_links(changes: Any) -> bool:
    if changes is None:
        return True
    for flag in (
        "note_text",
        "note",
        "card",
        "tags",
        "deck",
        "notetype",
        "browser_table",
    ):
        try:
            if bool(getattr(changes, flag, False)):
                return True
        except Exception:
            continue
    return False


def _on_operation_did_execute(changes, _handler) -> None:
    if not _changes_matter_for_links(changes):
        return
    for browser in list(_BROWSERS):
        try:
            if getattr(browser, "_ajpc_browser_graph_panel", None) is not None:
                _refresh_panel(browser)
        except Exception:
            continue


def install_browser_graph() -> None:
    if mw is None:
        return
    if getattr(mw, "_ajpc_browser_graph_installed", False):
        return
    gui_hooks.browser_will_show.append(_on_browser_will_show)
    gui_hooks.browser_did_change_row.append(_on_browser_did_change_row)
    gui_hooks.operation_did_execute.append(_on_operation_did_execute)
    gui_hooks.editor_did_init_buttons.append(_inject_editor_toggle_buttons)
    mw._ajpc_browser_graph_installed = True

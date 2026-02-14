from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Literal

from anki.cards import Card
from aqt import gui_hooks, mw
from aqt.browser.previewer import Previewer
from aqt.qt import QComboBox, QDoubleSpinBox, QFormLayout, QLabel, QSpinBox, QVBoxLayout, QWidget
from aqt.utils import tooltip

from . import ModuleSpec
from ._link_renderer import convert_links, existing_link_targets
from ._note_editor import open_note_editor

ADDON_DIR = os.path.dirname(os.path.dirname(__file__))
CONFIG_PATH = os.path.join(ADDON_DIR, "config.json")

LINK_CORE_INJECTION_FIELD = ""
LINK_CORE_EDITOR_INITIAL_WIDTH = 1180
LINK_CORE_EDITOR_INITIAL_HEIGHT = 820
LINK_CORE_EDITOR_SIDEBAR_RATIO = 0.30


@dataclass(frozen=True)
class LinkRef:
    label: str
    kind: Literal["nid", "cid"] = "nid"
    target_id: int = 0


@dataclass
class LinkGroup:
    key: str
    summary: LinkRef | None = None
    links: list[LinkRef] = field(default_factory=list)
    data_attrs: dict[str, str] = field(default_factory=dict)


@dataclass
class WrapperSpec:
    classes: list[str] = field(default_factory=lambda: ["ajpc-auto-links"])
    data_attrs: dict[str, str] = field(default_factory=dict)


@dataclass
class LinkPayload:
    mode: Literal["flat", "grouped"] = "flat"
    wrapper: WrapperSpec = field(default_factory=WrapperSpec)
    links: list[LinkRef] = field(default_factory=list)
    groups: list[LinkGroup] = field(default_factory=list)
    order: int = 100


@dataclass
class ProviderContext:
    card: Card
    kind: str
    note: Any
    html: str
    existing_nids: set[int]
    existing_cids: set[int]
    cache: dict[str, Any] | None = None


ProviderFn = Callable[[ProviderContext], list[LinkPayload]]
_PROVIDERS: dict[str, tuple[int, ProviderFn]] = {}
_PROVIDER_NAMES: dict[str, str] = {}


def _load_config() -> dict[str, Any]:
    if not os.path.exists(CONFIG_PATH):
        return {}
    with open(CONFIG_PATH, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def _cfg_get(cfg: dict[str, Any], path: str, default: Any = None) -> Any:
    cur: Any = cfg
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return default
        cur = cur[part]
    return cur


def _cfg_set(cfg: dict[str, Any], path: str, value: Any) -> None:
    cur: dict[str, Any] = cfg
    parts = path.split(".")
    for part in parts[:-1]:
        nxt = cur.get(part)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[part] = nxt
        cur = nxt
    cur[parts[-1]] = value


def _reload_config() -> None:
    global LINK_CORE_INJECTION_FIELD
    global LINK_CORE_EDITOR_INITIAL_WIDTH, LINK_CORE_EDITOR_INITIAL_HEIGHT, LINK_CORE_EDITOR_SIDEBAR_RATIO
    cfg = _load_config()
    LINK_CORE_INJECTION_FIELD = str(_cfg_get(cfg, "link_core.injection_field", "")).strip()
    try:
        LINK_CORE_EDITOR_INITIAL_WIDTH = int(_cfg_get(cfg, "link_core.popup_editor.width", 1180))
    except Exception:
        LINK_CORE_EDITOR_INITIAL_WIDTH = 1180
    try:
        LINK_CORE_EDITOR_INITIAL_HEIGHT = int(_cfg_get(cfg, "link_core.popup_editor.height", 820))
    except Exception:
        LINK_CORE_EDITOR_INITIAL_HEIGHT = 820
    try:
        LINK_CORE_EDITOR_SIDEBAR_RATIO = float(_cfg_get(cfg, "link_core.popup_editor.sidebar_ratio", 0.30))
    except Exception:
        LINK_CORE_EDITOR_SIDEBAR_RATIO = 0.30
    LINK_CORE_EDITOR_INITIAL_WIDTH = max(640, min(3840, LINK_CORE_EDITOR_INITIAL_WIDTH))
    LINK_CORE_EDITOR_INITIAL_HEIGHT = max(480, min(2160, LINK_CORE_EDITOR_INITIAL_HEIGHT))
    LINK_CORE_EDITOR_SIDEBAR_RATIO = max(0.10, min(0.60, LINK_CORE_EDITOR_SIDEBAR_RATIO))


def _default_provider_name(provider_id: str) -> str:
    raw = str(provider_id or "").strip()
    if not raw:
        return "Unknown"
    parts = [p for p in re.split(r"[^A-Za-z0-9]+", raw) if p]
    if not parts:
        return raw
    return " ".join(p[:1].upper() + p[1:] for p in parts)


def _provider_name(provider_id: str) -> str:
    pid = str(provider_id or "").strip()
    if not pid:
        return "Unknown"
    name = str(_PROVIDER_NAMES.get(pid, "") or "").strip()
    if name:
        return name
    return _default_provider_name(pid)


def register_provider(
    provider_id: str,
    provider: ProviderFn,
    *,
    order: int = 100,
    name: str = "",
) -> None:
    pid = str(provider_id or "").strip()
    if not pid or not callable(provider):
        return
    _PROVIDERS[pid] = (int(order), provider)
    display_name = str(name or "").strip()
    _PROVIDER_NAMES[pid] = display_name or _default_provider_name(pid)


def _iter_providers() -> list[tuple[str, int, ProviderFn]]:
    items: list[tuple[str, int, ProviderFn]] = []
    for provider_id, payload in _PROVIDERS.items():
        prio, fn = payload
        items.append((provider_id, prio, fn))
    items.sort(key=lambda x: (x[1], x[0]))
    return items


def _iter_provider_meta() -> list[tuple[str, int, ProviderFn, str]]:
    items: list[tuple[str, int, ProviderFn, str]] = []
    for provider_id, prio, fn in _iter_providers():
        items.append((provider_id, prio, fn, _provider_name(provider_id)))
    return items


def _label_to_raw(label: str) -> str:
    return (label or "").replace("[", "\\[")


def _ref_to_raw(ref: LinkRef) -> str:
    return f"[{_label_to_raw(ref.label)}|{ref.kind}{int(ref.target_id)}]"


def _attrs_to_html(data_attrs: dict[str, str]) -> str:
    parts: list[str] = []
    for key, val in (data_attrs or {}).items():
        k = str(key or "").strip().lower().replace("_", "-")
        if not k:
            continue
        if not k.startswith("data-"):
            k = "data-" + k
        v = str(val or "").replace("&", "&amp;").replace('"', "&quot;")
        parts.append(f' {k}="{v}"')
    return "".join(parts)


def _classes_to_html(classes: list[str]) -> str:
    clean = [str(c).strip() for c in (classes or []) if str(c).strip()]
    if not clean:
        clean = ["ajpc-auto-links"]
    return " ".join(clean)


def _render_payload(payload: LinkPayload) -> str:
    if payload.mode == "grouped":
        out: list[str] = []
        for grp in payload.groups:
            body_links: list[str] = []
            summary_html: str
            if grp.summary is not None:
                summary_html = f"<summary>{_ref_to_raw(grp.summary)}</summary>"
            else:
                key = str(grp.key or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                summary_html = f'<summary><div class="link">{key}</div></summary>'
            for ref in grp.links:
                body_links.append(_ref_to_raw(ref))
            details_html = "<details>" + summary_html
            if body_links:
                details_html += " " + " ".join(body_links)
            details_html += "</details>"

            merged_data = dict(payload.wrapper.data_attrs or {})
            merged_data.update(grp.data_attrs or {})
            attrs = _attrs_to_html(merged_data)
            classes = _classes_to_html(payload.wrapper.classes)
            out.append(f'<div class="{classes}"{attrs}>{details_html}</div>')
        return "".join(out)

    links = [_ref_to_raw(ref) for ref in payload.links]
    if not links:
        return ""
    attrs = _attrs_to_html(payload.wrapper.data_attrs)
    classes = _classes_to_html(payload.wrapper.classes)
    return f'<div class="{classes}"{attrs}>' + " ".join(links) + "</div>"


def _payload_targets(payload: LinkPayload) -> tuple[set[int], set[int]]:
    nids: set[int] = set()
    cids: set[int] = set()

    def _add(ref: LinkRef) -> None:
        try:
            target = int(ref.target_id)
        except Exception:
            return
        if str(ref.kind).lower() == "cid":
            cids.add(target)
        else:
            nids.add(target)

    for ref in payload.links:
        _add(ref)
    for grp in payload.groups:
        if grp.summary is not None:
            _add(grp.summary)
        for ref in grp.links:
            _add(ref)
    return nids, cids


def _template_html(card: Card, kind: str) -> str:
    if mw is None or not getattr(mw, "col", None):
        return ""
    try:
        model = mw.col.models.get(card.note().mid)
        tmpls = model.get("tmpls", []) if model else []
        ord_val = getattr(card, "ord", None)
        if ord_val is None or ord_val >= len(tmpls):
            return ""
        tmpl = tmpls[ord_val]
        if not isinstance(tmpl, dict):
            return ""
        is_question = "Question" in kind
        key = "qfmt" if is_question else "afmt"
        return str(tmpl.get(key, "") or "")
    except Exception:
        return ""


_VOID_TAGS = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}


def _selector_from_tag(tag: str) -> tuple[str, str] | None:
    if not tag:
        return None
    m = re.search(r'\bid=["\']([^"\']+)["\']', tag, re.IGNORECASE)
    if m:
        return ("id", m.group(1))
    m = re.search(r'\bclass=["\']([^"\']+)["\']', tag, re.IGNORECASE)
    if m:
        first_class = (m.group(1).strip().split() or [""])[0]
        if first_class:
            return ("class", first_class)
    return None


def _derive_parent_selector(template_html: str, field_name: str) -> tuple[str, str] | None:
    if not template_html or not field_name:
        return None
    field_re = re.compile(r"{{[^}]*\b" + re.escape(field_name) + r"\b[^}]*}}")
    tag_re = re.compile(r"<[^>]+>")

    stack: list[str] = []
    pos = 0
    for m in tag_re.finditer(template_html):
        text_segment = template_html[pos : m.start()]
        if field_re.search(text_segment):
            if stack:
                return _selector_from_tag(stack[-1])
            return None
        tag = m.group(0)
        pos = m.end()
        if tag.startswith("<!--"):
            continue
        if tag.startswith("</"):
            tag_name = re.sub(r"[</>\s].*", "", tag[2:]).lower()
            while stack:
                open_tag = stack.pop()
                open_name = re.sub(r"[<\s].*", "", open_tag[1:]).lower()
                if open_name == tag_name:
                    break
            continue
        tag_name = re.sub(r"[<>\s].*", "", tag[1:]).lower()
        is_self = tag.endswith("/>") or tag_name in _VOID_TAGS
        if not is_self:
            stack.append(tag)

    if field_re.search(template_html[pos:]):
        if stack:
            return _selector_from_tag(stack[-1])
    return None


def _inject_links_into_field(
    html: str,
    field_value: str,
    rendered: str,
    field_name: str,
    parent_selector: tuple[str, str] | None,
) -> str:
    if not rendered:
        return html
    if field_value and field_value in html:
        return html.replace(field_value, rendered + field_value, 1)

    marker = f"<!--AJPC:{field_name}-->" if field_name else ""
    if marker and marker in html:
        return html.replace(marker, rendered, 1)

    if parent_selector:
        sel_type, sel_value = parent_selector
        if sel_type == "id":
            id_pat = re.compile(
                rf'(<[^>]*\bid=["\']{re.escape(sel_value)}["\'][^>]*>)',
                re.IGNORECASE,
            )
            m = id_pat.search(html)
            if m:
                return html[: m.end(1)] + rendered + html[m.end(1) :]
        elif sel_type == "class":
            class_pat = re.compile(
                rf'(<[^>]*\bclass=["\'][^"\']*\b{re.escape(sel_value)}\b[^"\']*["\'][^>]*>)',
                re.IGNORECASE,
            )
            m = class_pat.search(html)
            if m:
                return html[: m.end(1)] + rendered + html[m.end(1) :]

    if field_name:
        escaped = re.escape(field_name)
        id_pat = re.compile(rf'(<[^>]*\bid=["\']{escaped}["\'][^>]*>)', re.IGNORECASE)
        m = id_pat.search(html)
        if m:
            return html[: m.end(1)] + rendered + html[m.end(1) :]

        class_pat = re.compile(
            rf'(<[^>]*\bclass=["\'][^"\']*\b{escaped}\b[^"\']*["\'][^>]*>)',
            re.IGNORECASE,
        )
        m = class_pat.search(html)
        if m:
            return html[: m.end(1)] + rendered + html[m.end(1) :]

    return html + rendered


def _inject_links(text: str, card: Card, kind: str) -> str:
    _reload_config()
    note = card.note()
    html = text

    known_nids, known_cids = existing_link_targets(html)
    payloads: list[LinkPayload] = []

    for _provider_id, _prio, provider in _iter_providers():
        ctx = ProviderContext(
            card=card,
            kind=kind,
            note=note,
            html=html,
            existing_nids=set(known_nids),
            existing_cids=set(known_cids),
        )
        try:
            out = provider(ctx) or []
        except Exception:
            continue
        for payload in out:
            if not isinstance(payload, LinkPayload):
                continue
            payloads.append(payload)
            nids, cids = _payload_targets(payload)
            known_nids.update(nids)
            known_cids.update(cids)

    payloads.sort(key=lambda p: int(p.order))
    field_name = str(LINK_CORE_INJECTION_FIELD or "").strip()
    field_value = ""
    if field_name and field_name in note:
        field_value = str(note[field_name] or "")
    parent_selector = _derive_parent_selector(_template_html(card, kind), field_name)

    for payload in payloads:
        rendered = _render_payload(payload)
        if not rendered:
            continue
        html = _inject_links_into_field(
            html, field_value, rendered, field_name, parent_selector
        )
    return html


def _postprocess_links(text: str, card: Card, kind: str) -> str:
    html = text
    html, _converted = convert_links(html)
    return html


_FRONTSIDE_RE = re.compile(r"\{\{\s*FrontSide\s*\}\}", re.IGNORECASE)
_ANSWER_HR_RE = re.compile(r"<hr[^>]*id\s*=\s*['\"]?answer['\"]?[^>]*>", re.IGNORECASE)
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _card_has_distinct_back(card: Card) -> bool:
    """Return True when the card template appears to render a distinct backside."""
    try:
        model = mw.col.models.get(card.note().mid)
        tmpls = model.get("tmpls", []) if isinstance(model, dict) else []
        ord_val = getattr(card, "ord", None)
        if ord_val is None or ord_val < 0 or ord_val >= len(tmpls):
            return True
        tmpl = tmpls[ord_val]
        if not isinstance(tmpl, dict):
            return True
        afmt = str(tmpl.get("afmt", "") or "")
        if not afmt.strip():
            return False
        reduced = _FRONTSIDE_RE.sub("", afmt)
        reduced = _ANSWER_HR_RE.sub("", reduced)
        reduced = reduced.replace("&nbsp;", " ")
        reduced = _HTML_TAG_RE.sub("", reduced)
        reduced = _WS_RE.sub("", reduced)
        if reduced:
            return True
        # Template only renders FrontSide/answer separator -> treat as no distinct backside.
        return False
    except Exception:
        # Fail open: keep previous behaviour if detection is uncertain.
        return True


def _force_front_if_no_back(previewer: Previewer, card: Card) -> None:
    if _card_has_distinct_back(card):
        return
    try:
        setattr(previewer, "_show_both_sides", False)
        setattr(previewer, "_state", "question")
        previewer.render_card()
    except Exception:
        return


def _handle_pycmd(handled: tuple[bool, Any], message: str, context: Any):
    if not isinstance(message, str):
        return handled
    if message.startswith("AJPCNoteLinker-openPreviewCard"):
        cid = message[len("AJPCNoteLinker-openPreviewCard") :]
        if not cid.isdigit():
            return True, None
        try:
            card = mw.col.get_card(int(cid))
        except Exception:
            tooltip("Linked card not found", period=2500)
            return True, None

        class _SingleCardPreviewer(Previewer):
            def __init__(self, card: Card, mw, on_close):
                self._card = card
                super().__init__(parent=None, mw=mw, on_close=on_close)

            def card(self) -> Card | None:
                return self._card

            def card_changed(self) -> bool:
                return False

        previewers = getattr(mw, "_ajpc_note_linker_previewers", None)
        if not isinstance(previewers, list):
            previewers = []
            mw._ajpc_note_linker_previewers = previewers

        previewer: _SingleCardPreviewer | None = None

        def _on_close() -> None:
            if previewer in previewers:
                previewers.remove(previewer)

        previewer = _SingleCardPreviewer(card, mw, _on_close)
        previewers.append(previewer)
        previewer.open()
        _force_front_if_no_back(previewer, card)
        return True, None
    if message.startswith("AJPCNoteLinker-openEditorCard"):
        cid = message[len("AJPCNoteLinker-openEditorCard") :]
        if not cid.isdigit():
            return True, None
        try:
            card = mw.col.get_card(int(cid))
            open_note_editor(int(card.nid), title="AJpC Note Editor")
        except Exception:
            tooltip("Failed to open linked card note", period=2500)
        return True, None
    if message.startswith("AJPCNoteLinker-openPreview"):
        nid = message[len("AJPCNoteLinker-openPreview") :]
        if not nid.isdigit():
            return True, None
        try:
            note = mw.col.get_note(int(nid))
        except Exception:
            tooltip("Linked note not found", period=2500)
            return True, None
        cards = note.cards()
        if not cards:
            tooltip("Linked note has no cards", period=2500)
            return True, None
        card = cards[0]

        class _SingleCardPreviewer(Previewer):
            def __init__(self, card: Card, mw, on_close):
                self._card = card
                super().__init__(parent=None, mw=mw, on_close=on_close)

            def card(self) -> Card | None:
                return self._card

            def card_changed(self) -> bool:
                return False

        previewers = getattr(mw, "_ajpc_note_linker_previewers", None)
        if not isinstance(previewers, list):
            previewers = []
            mw._ajpc_note_linker_previewers = previewers

        previewer: _SingleCardPreviewer | None = None

        def _on_close() -> None:
            if previewer in previewers:
                previewers.remove(previewer)

        previewer = _SingleCardPreviewer(card, mw, _on_close)
        previewers.append(previewer)
        previewer.open()
        _force_front_if_no_back(previewer, card)
        return True, None
    if message.startswith("AJPCNoteLinker-openEditor"):
        nid = message[len("AJPCNoteLinker-openEditor") :]
        if not nid.isdigit():
            return True, None
        try:
            open_note_editor(int(nid), title="AJpC Note Editor")
        except Exception:
            tooltip("Failed to open note", period=2500)
        return True, None
    return handled


def install_link_core() -> None:
    if mw is None:
        return
    if getattr(mw, "_ajpc_link_core_installed", False):
        return
    hooks = gui_hooks.card_will_show
    try:
        hooks._hooks.insert(0, _inject_links)
    except Exception:
        hooks.append(_inject_links)
    hooks.append(_postprocess_links)
    gui_hooks.webview_did_receive_js_message.append(_handle_pycmd)
    mw._ajpc_link_core_installed = True


def _get_all_field_names() -> list[str]:
    if mw is None or not getattr(mw, "col", None):
        return []
    out: set[str] = set()
    for model in mw.col.models.all():
        fields = model.get("flds", []) if isinstance(model, dict) else []
        for f in fields:
            if isinstance(f, dict):
                name = f.get("name")
            else:
                name = getattr(f, "name", None)
            if name:
                out.add(str(name))
    return sorted(out)


def _combo_value(combo: QComboBox) -> str:
    data = combo.currentData()
    if data is None:
        return str(combo.currentText() or "").strip()
    return str(data).strip()


def _populate_field_combo(combo: QComboBox, field_names: list[str], current_value: str) -> None:
    combo.setEditable(True)
    combo.addItem("", "")
    for name in field_names:
        combo.addItem(name, name)
    cur = (current_value or "").strip()
    if cur:
        idx = combo.findData(cur)
        if idx < 0:
            combo.addItem(f"{cur} (missing)", cur)
            idx = combo.findData(cur)
        if idx >= 0:
            combo.setCurrentIndex(idx)


def _tip_label(text: str, tip: str) -> QLabel:
    label = QLabel(text)
    label.setToolTip(tip)
    label.setWhatsThis(tip)
    return label


def _build_settings(ctx):
    _reload_config()
    tab = QWidget()
    layout = QVBoxLayout()
    tab.setLayout(layout)

    form = QFormLayout()
    layout.addLayout(form)

    injection_combo = QComboBox()
    fields = _get_all_field_names()
    cur = str(LINK_CORE_INJECTION_FIELD or "").strip()
    if cur and cur not in fields:
        fields.append(cur)
    _populate_field_combo(injection_combo, sorted(set(fields)), cur)
    form.addRow(
        _tip_label(
            "Injection field",
            "Field where provider raw links are inserted before rendering.",
        ),
        injection_combo,
    )

    popup_width_spin = QSpinBox()
    popup_width_spin.setRange(640, 3840)
    popup_width_spin.setSuffix(" px")
    popup_width_spin.setValue(int(LINK_CORE_EDITOR_INITIAL_WIDTH))
    form.addRow(
        _tip_label("Popup editor width", "Initial AJpC Note Editor popup width."),
        popup_width_spin,
    )

    popup_height_spin = QSpinBox()
    popup_height_spin.setRange(480, 2160)
    popup_height_spin.setSuffix(" px")
    popup_height_spin.setValue(int(LINK_CORE_EDITOR_INITIAL_HEIGHT))
    form.addRow(
        _tip_label("Popup editor height", "Initial AJpC Note Editor popup height."),
        popup_height_spin,
    )

    sidebar_ratio_spin = QDoubleSpinBox()
    sidebar_ratio_spin.setRange(10.0, 60.0)
    sidebar_ratio_spin.setDecimals(1)
    sidebar_ratio_spin.setSuffix(" %")
    sidebar_ratio_spin.setValue(float(LINK_CORE_EDITOR_SIDEBAR_RATIO) * 100.0)
    form.addRow(
        _tip_label("Popup sidebar ratio", "Width share of the right graph sidebar in the popup editor."),
        sidebar_ratio_spin,
    )

    layout.addStretch(1)

    ctx.add_tab(tab, "Link Core")

    def _save(cfg: dict, errors: list[str]) -> None:
        _cfg_set(cfg, "link_core.injection_field", str(_combo_value(injection_combo) or "").strip())
        _cfg_set(cfg, "link_core.popup_editor.width", int(popup_width_spin.value()))
        _cfg_set(cfg, "link_core.popup_editor.height", int(popup_height_spin.value()))
        _cfg_set(cfg, "link_core.popup_editor.sidebar_ratio", float(sidebar_ratio_spin.value() / 100.0))

    return _save


def _init() -> None:
    _reload_config()
    install_link_core()


MODULE = ModuleSpec(
    id="link_core",
    label="Link Core",
    order=15,
    init=_init,
    build_settings=_build_settings,
)

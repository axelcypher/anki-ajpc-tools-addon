from __future__ import annotations

import re
from typing import Any

from anki.cards import Card
from aqt import gui_hooks, mw
from aqt.browser.previewer import Previewer
from aqt.qt import QAction, QApplication
from aqt.utils import tooltip

from . import config, logging

_LINK_RE = re.compile(r"\[((?:[^\[]|\\\[)*?)\|nid(\d{13})\]")
_ANL_LINK_RE = re.compile(
    r'(<a\b[^>]*\bclass=[\'"]noteLink[\'"][^>]*>)(.*?)(</a>)',
    re.IGNORECASE | re.DOTALL,
)

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


def _is_note_linker_installed() -> bool:
    if mw is None or not getattr(mw, "addonManager", None):
        return False
    try:
        mgr = mw.addonManager
        if hasattr(mgr, "all_addon_meta"):
            for meta in mgr.all_addon_meta():
                if getattr(meta, "dir_name", None) == "1077002392" and getattr(
                    meta, "enabled", True
                ):
                    return True
            return False
        if hasattr(mgr, "allAddons"):
            return "1077002392" in set(mgr.allAddons() or [])
    except Exception:
        return False
    return False


def _note_type_name_from_id(note_type_id: str) -> str:
    if mw is None or not getattr(mw, "col", None):
        return note_type_id
    try:
        mid = int(str(note_type_id))
    except Exception:
        return note_type_id
    model = mw.col.models.get(mid)
    if not model:
        return note_type_id
    return str(model.get("name", note_type_id))


def _note_type_rules() -> dict[str, dict[str, Any]]:
    raw = config.NOTE_LINKER_RULES
    if not isinstance(raw, dict):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for nt_id, cfg in raw.items():
        if not isinstance(cfg, dict):
            continue
        out[str(nt_id)] = cfg
    return out


def _dbg(*args: Any) -> None:
    logging.dbg("NoteLinker", *args)


def _template_name(card: Card) -> str:
    try:
        model = mw.col.models.get(card.note().mid)
        tmpls = model.get("tmpls", []) if model else []
        ord_val = getattr(card, "ord", None)
        if ord_val is None:
            return ""
        for i, t in enumerate(tmpls):
            if i == ord_val:
                return str(t.get("name", ""))
    except Exception:
        return ""
    return ""


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


def _note_field_value(note, field_name: str) -> str:
    if not field_name:
        return ""
    if field_name not in note:
        return ""
    return str(note[field_name] or "")


def _label_for_note(note, label_field: str) -> str:
    if label_field and label_field in note:
        return str(note[label_field] or "")
    # fallback: first field
    try:
        return str(note.fields[0] or "")
    except Exception:
        return ""


def _copy_note_link_for_browser(browser) -> None:
    if mw is None or not getattr(mw, "col", None):
        tooltip("No collection loaded")
        return
    nids: list[int] = []
    try:
        nids = list(browser.selectedNotes() or [])
    except Exception:
        nids = []
    if not nids:
        try:
            card = getattr(browser, "card", None)
            if card:
                nids = [int(card.note().id)]
        except Exception:
            nids = []
    if not nids:
        tooltip("No note selected")
        return
    nid = int(nids[0])
    try:
        note = mw.col.get_note(nid)
    except Exception:
        tooltip("Note not found")
        return

    label_field = str(config.NOTE_LINKER_COPY_LABEL_FIELD or "").strip()
    label = _label_for_note(note, label_field).strip()
    label = label.replace("[", "\\[").replace("]", "\\]")
    link = f"[{label}|nid{nid}]"
    try:
        QApplication.clipboard().setText(link)
        tooltip("Copied note link")
        _dbg("browser copy", nid, "label_field", label_field)
    except Exception:
        tooltip("Failed to copy note link")


def _browser_context_menu(browser, menu, *_args) -> None:
    try:
        action = QAction("Copy current note link and label", menu)
        action.triggered.connect(lambda: _copy_note_link_for_browser(browser))
        menu.addAction(action)
    except Exception:
        return


def _links_for_tag(tag: str, label_field: str) -> list[str]:
    if mw is None or not getattr(mw, "col", None):
        return []
    if not tag:
        return []
    try:
        nids = mw.col.find_notes(f"tag:{tag}")
    except Exception:
        return []
    _dbg("tag search", tag, "matches", len(nids))
    links: list[str] = []
    for nid in nids:
        try:
            note = mw.col.get_note(nid)
        except Exception:
            continue
        label = _label_for_note(note, label_field)
        label = label.replace("[", "\\[")
        links.append(f"[{label}|nid{nid}]")
    return links


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
        _dbg("inject: matched field value", field_name)
        return html.replace(field_value, rendered + field_value, 1)

    marker = f"<!--AJPC:{field_name}-->" if field_name else ""
    if marker and marker in html:
        _dbg("inject: matched marker", marker)
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
                _dbg("inject: matched parent id", sel_value)
                return html[: m.end(1)] + rendered + html[m.end(1) :]
        elif sel_type == "class":
            class_pat = re.compile(
                rf'(<[^>]*\bclass=["\'][^"\']*\b{re.escape(sel_value)}\b[^"\']*["\'][^>]*>)',
                re.IGNORECASE,
            )
            m = class_pat.search(html)
            if m:
                _dbg("inject: matched parent class", sel_value)
                return html[: m.end(1)] + rendered + html[m.end(1) :]

    if field_name:
        escaped = re.escape(field_name)
        id_pat = re.compile(rf'(<[^>]*\bid=["\']{escaped}["\'][^>]*>)', re.IGNORECASE)
        m = id_pat.search(html)
        if m:
            _dbg("inject: matched id", field_name)
            return html[: m.end(1)] + rendered + html[m.end(1) :]

        class_pat = re.compile(
            rf'(<[^>]*\bclass=["\'][^"\']*\b{escaped}\b[^"\']*["\'][^>]*>)',
            re.IGNORECASE,
        )
        m = class_pat.search(html)
        if m:
            _dbg("inject: matched class", field_name)
            return html[: m.end(1)] + rendered + html[m.end(1) :]

    _dbg("inject: appended")
    return html + rendered


def _render_auto_links(card: Card, kind: str, html: str) -> str:
    if not config.NOTE_LINKER_ENABLED:
        return html
    if mw is None or not getattr(mw, "col", None):
        return html

    note = card.note()
    nt_id = str(note.mid)
    rules = _note_type_rules()
    rule = rules.get(nt_id)
    if not rule:
        _dbg("no rule for note type", nt_id, _note_type_name_from_id(nt_id))
        return html

    side = str(rule.get("side", "both")).lower()
    if kind == "reviewQuestion" and side not in ("front", "both"):
        _dbg("skip side front", side)
        return html
    if kind != "reviewQuestion" and side not in ("back", "both"):
        _dbg("skip side back", side)
        return html

    wanted_templates = {str(x) for x in (rule.get("templates") or []) if str(x).strip()}
    tmpl_name = _template_name(card)
    if wanted_templates and tmpl_name not in wanted_templates:
        _dbg("template not in set", tmpl_name, "wanted", wanted_templates)
        return html

    tag = str(rule.get("tag", "")).strip()
    if not tag:
        _dbg("missing tag for note type", nt_id, _note_type_name_from_id(nt_id))
        return html

    label_field = str(rule.get("label_field", "")).strip()
    target_field = str(rule.get("target_field", "")).strip()

    links = _links_for_tag(tag, label_field)
    if not links:
        _dbg("no links for tag", tag)
        return html

    # build raw ANL-style link tags so ANL can still convert them
    rendered_links = '<div class="ajpc-auto-links">' + " ".join(links) + "</div>"
    _dbg("auto links injected", len(links), "tag", tag)

    field_value = _note_field_value(note, target_field)
    template_html = _template_html(card, kind)
    parent_selector = _derive_parent_selector(template_html, target_field)
    if parent_selector:
        _dbg("derived parent selector", parent_selector)
    return _inject_links_into_field(
        html, field_value, rendered_links, target_field, parent_selector
    )


def _convert_links(html: str, *, use_anl: bool) -> tuple[str, int]:
    def repl(match):
        label = match.group(1).replace("\\[", "[")
        nid = match.group(2)
        if use_anl:
            return (
                f'<a class="noteLink" '
                f'href=\'javascript:pycmd(`AnkiNoteLinker-openNoteInPreviewer`+`{nid}`)\' '
                f'oncontextmenu=\'event.preventDefault();pycmd(`AnkiNoteLinker-openNoteInNewEditor`+`{nid}`)\'>'
                f'<div class="ajpc-note-link-text">{label}</div></a>'
            )
        return (
            f'<a class="ajpc-note-link" '
            f'href=\'javascript:pycmd("AJPCNoteLinker-openPreview"+"{nid}")\' '
            f'oncontextmenu=\'event.preventDefault();pycmd("AJPCNoteLinker-openEditor"+"{nid}")\'>'
            f'<div class="ajpc-note-link-text">{label}</div></a>'
        )

    return _LINK_RE.subn(repl, html)


def _wrap_anl_links(html: str) -> tuple[str, int]:
    def repl(match):
        start, inner, end = match.groups()
        if "ajpc-note-link-text" in inner:
            return match.group(0)
        return f'{start}<div class="ajpc-note-link-text">{inner}</div>{end}'

    return _ANL_LINK_RE.subn(repl, html)


def _handle_pycmd(handled: tuple[bool, Any], message: str, context: Any):
    if not isinstance(message, str):
        return handled
    if message.startswith("AJPCNoteLinker-openPreview"):
        nid = message[len("AJPCNoteLinker-openPreview") :]
        if not nid.isdigit():
            return True, None
        try:
            note = mw.col.get_note(int(nid))
        except Exception:
            tooltip("Linked note not found")
            return True, None
        cards = note.cards()
        if not cards:
            tooltip("Linked note has no cards")
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
        return True, None
    if message.startswith("AJPCNoteLinker-openEditor"):
        nid = message[len("AJPCNoteLinker-openEditor") :]
        if not nid.isdigit():
            return True, None
        try:
            from aqt import dialogs
            from aqt.editor import Editor
            from anki.notes import NoteId

            ed = dialogs.open("EditCurrent", mw, NoteId(int(nid)))
            if isinstance(ed, Editor):
                ed.activateWindow()
        except Exception:
            tooltip("Failed to open note")
        return True, None
    return handled


def _inject_auto_links(text: str, card: Card, kind: str) -> str:
    if not config.NOTE_LINKER_ENABLED:
        return text
    html = _render_auto_links(card, kind, text)
    _dbg(
        "inject",
        "card",
        getattr(card, "id", None),
        "kind",
        kind,
    )
    return html


def _postprocess_links(text: str, card: Card, kind: str) -> str:
    html = text
    anl_installed = _is_note_linker_installed()
    _dbg(
        "render",
        "card",
        getattr(card, "id", None),
        "kind",
        kind,
        "anl",
        anl_installed,
        "auto",
        config.NOTE_LINKER_ENABLED,
    )
    if anl_installed:
        html, wrapped = _wrap_anl_links(html)
        if wrapped:
            _dbg("anl wrapped", wrapped)
    else:
        html, converted = _convert_links(html, use_anl=False)
        if converted:
            _dbg("fallback converted", converted)
    return html


def install_note_linker() -> None:
    if mw is None:
        _dbg("install skipped: no mw")
        return
    if getattr(mw, "_ajpc_note_linker_installed", False):
        _dbg("install skipped: already installed")
        return
    hooks = gui_hooks.card_will_show
    try:
        hooks._hooks.insert(0, _inject_auto_links)
    except Exception:
        hooks.append(_inject_auto_links)
    hooks.append(_postprocess_links)
    gui_hooks.webview_did_receive_js_message.append(_handle_pycmd)
    gui_hooks.browser_will_show_context_menu.append(_browser_context_menu)
    mw._ajpc_note_linker_installed = True
    _dbg("installed hooks")


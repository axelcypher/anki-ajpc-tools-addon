from __future__ import annotations

import re
from typing import Any

_LINK_RE = re.compile(r"\[((?:[^\[]|\\\[)*?)\|nid(\d{13})\]")
_ANL_LINK_RE = re.compile(
    r'(<a\b[^>]*\bclass=[\'"]noteLink[\'"][^>]*>)(.*?)(</a>)',
    re.IGNORECASE | re.DOTALL,
)
_RAW_LINK_TARGET_RE = re.compile(r"\[[^\]]*?\|(nid|cid)(\d+)\]", re.IGNORECASE)
_ANL_CMD_TARGET_RE = re.compile(
    r"AnkiNoteLinker-openNoteIn(?:Previewer|NewEditor)[^0-9]*([0-9]+)",
    re.IGNORECASE,
)
_AJPC_CMD_TARGET_RE = re.compile(
    r"AJPCNoteLinker-open(?:Preview|Editor)[^0-9]*([0-9]+)",
    re.IGNORECASE,
)


def existing_link_targets(html: str) -> tuple[set[int], set[int]]:
    nids: set[int] = set()
    cids: set[int] = set()

    if not html:
        return nids, cids

    for m in _RAW_LINK_TARGET_RE.finditer(html):
        kind = (m.group(1) or "").lower()
        try:
            val = int(m.group(2))
        except Exception:
            continue
        if kind == "cid":
            cids.add(val)
        else:
            nids.add(val)

    for m in _ANL_CMD_TARGET_RE.finditer(html):
        try:
            nids.add(int(m.group(1)))
        except Exception:
            continue

    for m in _AJPC_CMD_TARGET_RE.finditer(html):
        try:
            nids.add(int(m.group(1)))
        except Exception:
            continue

    return nids, cids


def convert_links(html: str, *, use_anl: bool) -> tuple[str, int]:
    def repl(match: Any) -> str:
        label = match.group(1).replace("\\[", "[")
        nid = match.group(2)
        if use_anl:
            return (
                f'<a class="noteLink" '
                f'href=\'javascript:pycmd(`AnkiNoteLinker-openNoteInPreviewer`+`{nid}`)\' '
                f'oncontextmenu=\'event.preventDefault();pycmd(`AnkiNoteLinker-openNoteInNewEditor`+`{nid}`)\'>'  # noqa: E501
                f'<div class="ajpc-note-link-text">{label}</div></a>'
            )
        return (
            f'<a class="ajpc-note-link" '
            f'href=\'javascript:pycmd("AJPCNoteLinker-openPreview"+"{nid}")\' '
            f'oncontextmenu=\'event.preventDefault();pycmd("AJPCNoteLinker-openEditor"+"{nid}")\'>'  # noqa: E501
            f'<div class="ajpc-note-link-text">{label}</div></a>'
        )

    return _LINK_RE.subn(repl, html)


def wrap_anl_links(html: str) -> tuple[str, int]:
    def repl(match: Any) -> str:
        start, inner, end = match.groups()
        if "ajpc-note-link-text" in inner:
            return match.group(0)
        return f'{start}<div class="ajpc-note-link-text">{inner}</div>{end}'

    return _ANL_LINK_RE.subn(repl, html)

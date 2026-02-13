from __future__ import annotations

from typing import Any

from aqt import mw

from ..modules._note_editor import open_note_editor


NOTE_EDITOR_API_VERSION = "1.0.0"


def _get_window(nid: int) -> Any:
    if mw is None:
        return None
    try:
        windows = getattr(mw, "_ajpc_note_editor_windows", None)
        if not isinstance(windows, dict):
            return None
        win = windows.get(int(nid))
        if win is None:
            return None
        if hasattr(win, "isVisible") and not win.isVisible():
            return None
        return win
    except Exception:
        return None


def open_editor(nid: int, *, title: str = "AJpC Note Editor") -> bool:
    try:
        return bool(open_note_editor(int(nid), title=str(title or "AJpC Note Editor")))
    except Exception:
        return False


def is_open(nid: int) -> bool:
    return _get_window(int(nid)) is not None


def install_note_editor_api() -> None:
    if mw is None:
        return
    mw._ajpc_note_editor_api = {
        "version": NOTE_EDITOR_API_VERSION,
        "open": open_editor,
        "is_open": is_open,
        "get_window": _get_window,
    }


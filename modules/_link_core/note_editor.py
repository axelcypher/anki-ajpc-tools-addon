from __future__ import annotations

import json
import os

import aqt.forms
import aqt.editor
from aqt import mw
from aqt.editor import Editor
from aqt.qt import QDialogButtonBox, QMainWindow, QSplitter, Qt, QTimer


ADDON_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
CONFIG_PATH = os.path.join(ADDON_DIR, "config.json")


def _load_popup_editor_layout_settings() -> tuple[int, int, float]:
    width = 820
    height = 820
    sidebar_ratio = 0.30
    if not os.path.exists(CONFIG_PATH):
        return (width, height, sidebar_ratio)
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8-sig") as f:
            cfg = json.load(f)
        link_core = cfg.get("link_core") if isinstance(cfg, dict) else None
        popup = link_core.get("popup_editor") if isinstance(link_core, dict) else None
        if isinstance(popup, dict):
            try:
                width = int(popup.get("width", width))
            except Exception:
                pass
            try:
                height = int(popup.get("height", height))
            except Exception:
                pass
            try:
                sidebar_ratio = float(popup.get("sidebar_ratio", sidebar_ratio))
            except Exception:
                pass
    except Exception:
        pass
    width = max(640, min(3840, int(width)))
    height = max(480, min(2160, int(height)))
    sidebar_ratio = max(0.10, min(0.60, float(sidebar_ratio)))
    return (width, height, sidebar_ratio)


class _NoteEditorWindow(QMainWindow):
    def __init__(self, nid: int, title: str) -> None:
        super().__init__(None, Qt.WindowType.Window)
        self._nid = int(nid)
        (
            self._editor_initial_width,
            self._editor_initial_height,
            self._sidebar_ratio,
        ) = _load_popup_editor_layout_settings()
        self.card = None
        self._ajpc_browser_graph_panel = None
        self._ajpc_main_splitter = None
        self.form = aqt.forms.editcurrent.Ui_Dialog()
        self.form.setupUi(self)
        self._init_link_panel()
        self.setWindowTitle(str(title or "AJpC Note Editor"))
        self._editor = Editor(
            mw,
            self.form.fieldsArea,
            self,
            editor_mode=aqt.editor.EditorMode.EDIT_CURRENT,
        )
        close_button = self.form.buttonBox.button(QDialogButtonBox.StandardButton.Close)
        if close_button is not None:
            close_button.setShortcut("Ctrl+Return")
        self._load_note()

    def _apply_main_splitter_ratio(self, sidebar_ratio: float | None = None) -> bool:
        splitter = self._ajpc_main_splitter
        panel = self._ajpc_browser_graph_panel
        if splitter is None or panel is None:
            return False
        try:
            total = int(splitter.width()) or int(self.width())
        except Exception:
            total = 0
        if total <= 0:
            return False
        try:
            ratio = float(self._sidebar_ratio if sidebar_ratio is None else sidebar_ratio)
        except Exception:
            ratio = 0.30
        if ratio <= 0.0 or ratio >= 1.0:
            ratio = 0.30

        min_sidebar = int(max(0, panel.minimumWidth()))
        max_sidebar = int(panel.maximumWidth()) if int(panel.maximumWidth()) > 0 else total
        sidebar = int(round(total * ratio))
        sidebar = max(min_sidebar, min(max_sidebar, sidebar))
        if sidebar >= total:
            sidebar = max(min_sidebar, total - 1)
        main = max(1, total - sidebar)

        splitter.setStretchFactor(0, 7)
        splitter.setStretchFactor(1, 3)
        splitter.setSizes([main, sidebar])
        return True

    def _init_link_panel(self) -> None:
        try:
            from . import browser_graph as _bg
        except Exception:
            return
        try:
            root = getattr(self.form, "verticalLayout", None)
            fields = getattr(self.form, "fieldsArea", None)
            parent = getattr(self.form, "centralwidget", None)
            if root is None or fields is None or parent is None:
                return
            root.removeWidget(fields)
            splitter = QSplitter(Qt.Orientation.Horizontal, parent)
            splitter.setObjectName("ajpcPopupEditorSplitter")
            splitter.setChildrenCollapsible(False)
            splitter.setHandleWidth(6)
            root.insertWidget(0, splitter, 1)

            fields.setParent(splitter)
            splitter.addWidget(fields)

            panel = _bg._BrowserGraphPanel(splitter)  # noqa: SLF001 - shared internal UI
            splitter.addWidget(panel)

            self._ajpc_main_splitter = splitter
            self._ajpc_browser_graph_panel = panel
            QTimer.singleShot(0, self._apply_main_splitter_ratio)
            try:
                _bg._BROWSERS.add(self)  # noqa: SLF001 - reuse existing refresh hook pipeline
            except Exception:
                pass
        except Exception:
            self._ajpc_main_splitter = None
            self._ajpc_browser_graph_panel = None

    def _load_note(self) -> None:
        if mw is None or not getattr(mw, "col", None):
            return
        note = mw.col.get_note(self._nid)
        cards = note.cards()
        self.card = cards[0] if cards else None
        self._editor.card = self.card
        self._editor.set_note(note, focusTo=0)
        self._refresh_link_panel()
        self.resize(int(self._editor_initial_width), int(self._editor_initial_height))
        QTimer.singleShot(0, self._apply_main_splitter_ratio)
        QTimer.singleShot(60, self._apply_main_splitter_ratio)

    def selectedNotes(self) -> list[int]:
        nid = int(self._nid or 0)
        return [nid] if nid > 0 else []

    def _refresh_link_panel(self) -> None:
        if self._ajpc_browser_graph_panel is None:
            return
        try:
            from . import browser_graph as _bg

            _bg._refresh_panel(self)  # noqa: SLF001 - shared panel population code path
        except Exception:
            return

    def closeEvent(self, evt) -> None:
        try:
            self._editor.cleanup()
        except Exception:
            pass
        super().closeEvent(evt)


def open_note_editor(nid: int, *, title: str = "AJpC Note Editor") -> bool:
    if int(nid) <= 0:
        return False
    if mw is None or not getattr(mw, "col", None):
        return False

    try:
        editors = getattr(mw, "_ajpc_note_editor_windows", None)
        if not isinstance(editors, dict):
            editors = {}
            mw._ajpc_note_editor_windows = editors

        key = int(nid)
        existing = editors.get(key)
        if existing is not None and hasattr(existing, "isVisible") and existing.isVisible():
            existing.activateWindow()
            existing.raise_()
            return True

        win = _NoteEditorWindow(int(nid), str(title or "AJpC Note Editor"))
        editors[key] = win

        def _on_destroyed(*_args) -> None:
            try:
                cur = getattr(mw, "_ajpc_note_editor_windows", None)
                if isinstance(cur, dict):
                    cur.pop(key, None)
            except Exception:
                return

        win.destroyed.connect(_on_destroyed)
        win.show()
        win.raise_()
        win.activateWindow()
        return True
    except Exception:
        return False

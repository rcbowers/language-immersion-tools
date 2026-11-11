"""Signal and text tests for small widgets, plus the app entrypoint wiring."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest

from immersion_app import app as app_module
from immersion_app.core.recent_files import add_recent_file
from immersion_app.gui.widgets.queue_dialog import QueueDialog
from immersion_app.gui.widgets.recent_files_menu import RecentFileMenuItem, RecentFilesMenu


# --- QueueDialog ---------------------------------------------------------


def test_queue_dialog_lists_entries(qtbot):
    dialog = QueueDialog()
    qtbot.addWidget(dialog)
    dialog.refresh([
        {"word": "gato", "translation": "cat", "sentence": "El gato duerme."},
        {"word": "perro"},
    ])
    items = [dialog.list_widget.item(i).text() for i in range(dialog.list_widget.count())]
    assert items == ["gato -> cat | El gato duerme.", "perro ->  | "]


def test_queue_dialog_refresh_replaces_previous_contents(qtbot):
    dialog = QueueDialog()
    qtbot.addWidget(dialog)
    dialog.refresh([{"word": "a"}, {"word": "b"}])
    dialog.refresh([])
    assert dialog.list_widget.count() == 0


def test_queue_dialog_process_button_signal(qtbot):
    dialog = QueueDialog()
    qtbot.addWidget(dialog)
    with qtbot.waitSignal(dialog.process_button.clicked, timeout=1000):
        dialog.process_button.click()


# --- RecentFilesMenu -----------------------------------------------------


def _recent(tmp_path, *names):
    data = {"recent_files": []}
    for name in names:
        path = tmp_path / name
        path.write_bytes(b"x")
        if name.endswith(".pdf"):
            add_recent_file(data, str(path), "pdf", {"page_index": 4})
        else:
            add_recent_file(data, str(path), "video", {"video_position_ms": 65_000})
    return data


def test_menu_shows_empty_state_and_browse(qtbot):
    menu = RecentFilesMenu({"recent_files": []})
    qtbot.addWidget(menu)
    texts = [a.text() for a in menu.actions() if a.text()]
    assert texts == ["No recent files", "Browse for file..."]
    assert not menu.actions()[0].isEnabled()


def test_menu_browse_action_emits_signal(qtbot):
    menu = RecentFilesMenu({"recent_files": []})
    qtbot.addWidget(menu)
    browse = [a for a in menu.actions() if a.text() == "Browse for file..."][0]
    with qtbot.waitSignal(menu.browse_requested, timeout=1000):
        browse.trigger()


def test_menu_lists_existing_files_only(qtbot, tmp_path):
    data = _recent(tmp_path, "book.pdf", "clip.mp4")
    add_recent_file(data, str(tmp_path / "deleted.pdf"), "pdf", {})
    menu = RecentFilesMenu(data)
    qtbot.addWidget(menu)
    items = [a.defaultWidget() for a in menu.actions() if hasattr(a, "defaultWidget") and a.defaultWidget()]
    assert sorted(w.file_data["name"] for w in items) == ["book.pdf", "clip.mp4"]


def test_menu_item_shows_position_and_time(qtbot, tmp_path):
    data = _recent(tmp_path, "book.pdf", "clip.mp4")
    video, pdf = (RecentFileMenuItem(e) for e in data["recent_files"])
    qtbot.addWidget(video)
    qtbot.addWidget(pdf)
    assert "Page 5" in pdf.metadata_label.text() and "Just now" in pdf.metadata_label.text()
    assert "1:05" in video.metadata_label.text()
    assert "clip.mp4" in video.filename_label.text()


def test_clicking_item_emits_path_and_type(qtbot, tmp_path):
    data = _recent(tmp_path, "book.pdf")
    item = RecentFileMenuItem(data["recent_files"][0])
    qtbot.addWidget(item)
    with qtbot.waitSignal(item.clicked, timeout=1000) as blocker:
        QTest.mouseClick(item, Qt.MouseButton.LeftButton, pos=QPoint(5, 5))
    assert blocker.args == [data["recent_files"][0]["path"], "pdf"]


def test_menu_forwards_item_selection(qtbot, tmp_path):
    data = _recent(tmp_path, "book.pdf")
    menu = RecentFilesMenu(data)
    qtbot.addWidget(menu)
    item = [a.defaultWidget() for a in menu.actions() if hasattr(a, "defaultWidget") and a.defaultWidget()][0]
    with qtbot.waitSignal(menu.file_selected, timeout=1000) as blocker:
        item.clicked.emit(item.file_path, item.file_type)
    assert blocker.args == [data["recent_files"][0]["path"], "pdf"]


# --- app.main wiring -----------------------------------------------------


def test_main_wires_logging_migration_and_window(monkeypatch):
    order = []

    class _App:
        def __init__(self, argv):
            order.append("qapp")

        def setApplicationName(self, name):
            order.append(("name", name))

        def exec(self):
            order.append("exec")
            return 7

    class _Window:
        def __init__(self):
            order.append("window")

        def showMaximized(self):
            order.append("show")

    monkeypatch.setattr(app_module, "QApplication", _App)
    monkeypatch.setattr(app_module, "UnifiedSentenceMinerWindow", _Window)
    monkeypatch.setattr(app_module, "migrate_legacy_data", lambda: order.append("migrate") or False)
    monkeypatch.setattr(app_module, "ensure_runtime_dirs", lambda: order.append("dirs"))
    monkeypatch.setattr(app_module, "setup_logging", lambda: order.append("logging"))
    monkeypatch.setattr(app_module.QFontDatabase, "addApplicationFont", staticmethod(lambda path: order.append("font") or 0))

    assert app_module.main() == 7
    # Data is migrated before the window loads it; logging is up before the window starts.
    assert order.index("migrate") < order.index("dirs") < order.index("logging") < order.index("window")
    assert order[-2:] == ["show", "exec"]
    assert ("name", "LinguaLoop") in order

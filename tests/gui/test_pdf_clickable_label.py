"""ClickablePdfLabel overlay: highlights are painted over the cached page and update minimally."""

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QColor, QPixmap

from immersion_app.gui.widgets.pdf_clickable_label import ClickablePdfLabel

WHITE = QColor(255, 255, 255)


def _label(qtbot):
    label = ClickablePdfLabel()
    qtbot.addWidget(label)
    pixmap = QPixmap(200, 100)
    pixmap.fill(WHITE)
    label.setPixmap(pixmap)
    label.resize(200, 100)
    return label


def _pixel(label, x, y):
    return label.grab().toImage().pixelColor(x, y)


def test_selection_and_word_highlights_are_painted_over_page(qtbot):
    label = _label(qtbot)
    label.set_word_highlights([(QRect(10, 10, 30, 10), QColor(0, 0, 255))])
    label.set_selection_rects([QRect(100, 10, 30, 10)], QColor(255, 0, 0))

    assert _pixel(label, 15, 15) == QColor(0, 0, 255)
    assert _pixel(label, 105, 15) == QColor(255, 0, 0)
    assert _pixel(label, 60, 60) == WHITE


def test_clearing_selection_restores_page(qtbot):
    label = _label(qtbot)
    label.set_selection_rects([QRect(100, 10, 30, 10)], QColor(255, 0, 0))
    label.set_selection_rects([])
    assert _pixel(label, 105, 15) == WHITE


def test_selection_update_only_dirties_old_and_new_areas(qtbot):
    label = _label(qtbot)
    label.set_selection_rects([QRect(10, 10, 20, 10)], QColor(255, 0, 0))
    dirty = []
    label.update = lambda arg=None: dirty.append(arg)  # capture instead of scheduling a paint

    label.set_selection_rects([QRect(150, 70, 20, 10)])

    assert len(dirty) == 1
    region = dirty[0]
    assert region.boundingRect().width() < 200 or region.boundingRect().height() < 100
    assert region.contains(QPoint(15, 15)) and region.contains(QPoint(155, 75))
    assert not region.contains(QPoint(100, 40))


def test_identical_selection_does_not_repaint(qtbot):
    label = _label(qtbot)
    label.set_selection_rects([QRect(10, 10, 20, 10)], QColor(255, 0, 0))
    dirty = []
    label.update = lambda arg=None: dirty.append(arg)
    label.set_selection_rects([QRect(10, 10, 20, 10)])
    assert dirty == []


def test_mouse_signals_still_emitted(qtbot):
    label = _label(qtbot)
    clicks = []
    label.clicked.connect(lambda point, mods: clicks.append(point))
    qtbot.mouseClick(label, Qt.MouseButton.LeftButton, pos=QPoint(20, 20))
    assert clicks == [QPoint(20, 20)]

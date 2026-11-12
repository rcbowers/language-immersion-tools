"""Settings dialog: Anki, languages, translation, appearance and data folder.

Pure presentation: it shows values it is given, emits signals for actions that
need Anki (refresh lists, create deck), and returns the edited values from
:meth:`values`. The SettingsController does the I/O and applies changes.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from immersion_app import __version__
from immersion_app.core.appearance_manager import available_themes
from immersion_app.gui.theme import Theme


class SettingsDialog(QDialog):
    refresh_anki_requested = Signal(str)  # connect_url
    create_deck_requested = Signal(str, str)  # (connect_url, deck_name)
    open_data_folder_requested = Signal()
    start_anki_requested = Signal()

    def __init__(self, parent: QWidget | None = None, *, languages: list[tuple[str, str]], data_folder: str):
        """``languages``: list of (code, label) pairs."""
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(Theme.SETTINGS_DIALOG_WIDTH)
        self.setStyleSheet(Theme.get_dialog_style())
        self._fields_by_note_type: dict[str, list[str]] = {}
        self._languages = languages

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Theme.DIALOG_MARGIN, Theme.DIALOG_MARGIN, Theme.DIALOG_MARGIN, Theme.DIALOG_MARGIN)
        layout.setSpacing(Theme.DIALOG_SPACING)

        layout.addWidget(self._build_anki_group())
        layout.addWidget(self._build_language_group())
        layout.addWidget(self._build_general_group(data_folder))

        self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        self.button_box.button(QDialogButtonBox.StandardButton.Save).setStyleSheet(Theme.get_button_style("primary"))
        self.button_box.button(QDialogButtonBox.StandardButton.Cancel).setStyleSheet(Theme.get_button_style("secondary"))
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)

    # ---- construction -------------------------------------------------
    def _combo(self, editable: bool = False) -> QComboBox:
        combo = QComboBox()
        combo.setEditable(editable)
        combo.setStyleSheet(Theme.get_combo_style())
        combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        return combo

    def _build_anki_group(self) -> QGroupBox:
        group = QGroupBox("Anki")
        form = QFormLayout(group)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        intro = QLabel(
            "Language Immersion Tools adds cards through the AnkiConnect add-on (code 2055492159). "
            "Keep Anki open while you mine."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet(Theme.get_label_style("caption"))
        form.addRow(intro)

        url_row = QHBoxLayout()
        self.url_edit = QLineEdit()
        self.url_edit.setStyleSheet(Theme.get_input_style())
        self.refresh_button = QPushButton("Load from Anki")
        self.refresh_button.setStyleSheet(Theme.get_button_style("secondary"))
        self.refresh_button.clicked.connect(lambda: self.refresh_anki_requested.emit(self.connect_url()))
        self.start_anki_button = QPushButton("Start Anki")
        self.start_anki_button.setStyleSheet(Theme.get_button_style("ghost"))
        self.start_anki_button.clicked.connect(self.start_anki_requested.emit)
        url_row.addWidget(self.url_edit, 1)
        url_row.addWidget(self.refresh_button)
        url_row.addWidget(self.start_anki_button)
        form.addRow("AnkiConnect URL", url_row)

        deck_row = QHBoxLayout()
        self.deck_combo = self._combo(editable=True)
        self.create_deck_button = QPushButton("Create deck")
        self.create_deck_button.setStyleSheet(Theme.get_button_style("secondary"))
        self.create_deck_button.clicked.connect(
            lambda: self.create_deck_requested.emit(self.connect_url(), self.deck_combo.currentText().strip())
        )
        deck_row.addWidget(self.deck_combo, 1)
        deck_row.addWidget(self.create_deck_button)
        form.addRow("Deck", deck_row)

        self.note_type_combo = self._combo(editable=True)
        self.note_type_combo.currentTextChanged.connect(self._on_note_type_changed)
        form.addRow("Note type", self.note_type_combo)

        self.sentence_field_combo = self._combo(editable=True)
        form.addRow("Sentence field", self.sentence_field_combo)
        self.translation_field_combo = self._combo(editable=True)
        form.addRow("Translation field", self.translation_field_combo)

        self.tags_edit = QLineEdit()
        self.tags_edit.setStyleSheet(Theme.get_input_style())
        self.tags_edit.setPlaceholderText("space-separated, e.g. sentence-mining language-immersion-tools")
        form.addRow("Tags", self.tags_edit)

        self.anki_status_label = QLabel("")
        self.anki_status_label.setWordWrap(True)
        self.anki_status_label.setStyleSheet(Theme.get_status_text_style("muted"))
        form.addRow(self.anki_status_label)
        return group

    def _build_language_group(self) -> QGroupBox:
        group = QGroupBox("Languages")
        form = QFormLayout(group)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.learning_combo = self._combo()
        self.native_combo = self._combo()
        for code, label in self._languages:
            self.learning_combo.addItem(label, code)
            self.native_combo.addItem(label, code)
        form.addRow("I'm learning", self.learning_combo)
        form.addRow("Translate into", self.native_combo)
        return group

    def _build_general_group(self, data_folder: str) -> QGroupBox:
        group = QGroupBox("Translation, appearance and data")
        form = QFormLayout(group)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.translation_combo = self._combo()
        self.translation_combo.addItem("Online (Google Translate, needs internet)", "online")
        self.translation_combo.addItem("Offline (MarianMT, optional install)", "offline")
        form.addRow("Translation", self.translation_combo)

        self.prefetch_checkbox = QCheckBox("Pre-translate words on each page in the background")
        form.addRow("", self.prefetch_checkbox)

        self.theme_combo = self._combo()
        for theme_id, theme_label in available_themes():
            self.theme_combo.addItem(theme_label, theme_id)
        form.addRow("Appearance", self.theme_combo)

        data_row = QHBoxLayout()
        self.data_folder_label = QLabel(data_folder)
        self.data_folder_label.setStyleSheet(Theme.get_label_style("caption"))
        self.data_folder_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.data_folder_label.setWordWrap(True)
        open_button = QPushButton("Open")
        open_button.setStyleSheet(Theme.get_button_style("secondary"))
        open_button.clicked.connect(self.open_data_folder_requested.emit)
        data_row.addWidget(self.data_folder_label, 1)
        data_row.addWidget(open_button)
        form.addRow("Data folder", data_row)

        version_label = QLabel(__version__)
        version_label.setStyleSheet(Theme.get_label_style("caption"))
        form.addRow("Version", version_label)
        return group

    # ---- population ---------------------------------------------------
    def set_values(self, values: dict) -> None:
        anki = values.get("anki", {})
        self.url_edit.setText(anki.get("connect_url", ""))
        self._set_combo_text(self.deck_combo, anki.get("deck_name", ""))
        self._set_combo_text(self.note_type_combo, anki.get("note_type", ""))
        self._set_combo_text(self.sentence_field_combo, anki.get("sentence_field", ""))
        self._set_combo_text(self.translation_field_combo, anki.get("translation_field", ""))
        self.tags_edit.setText(" ".join(anki.get("tags", [])))
        self._select_data(self.learning_combo, values.get("learning_language"))
        self._select_data(self.native_combo, values.get("native_language"))
        self._select_data(self.translation_combo, values.get("translation_mode"))
        self.prefetch_checkbox.setChecked(bool(values.get("prefetch_enabled", True)))
        self._select_data(self.theme_combo, values.get("theme_mode"))

    def set_anki_options(self, decks: list[str], fields_by_note_type: dict[str, list[str]]) -> None:
        """Fill the dropdowns with what exists in Anki, keeping the current choices."""
        self._fields_by_note_type = dict(fields_by_note_type)
        self._replace_items(self.deck_combo, decks)
        self._replace_items(self.note_type_combo, sorted(fields_by_note_type))
        self._on_note_type_changed(self.note_type_combo.currentText())

    def set_anki_status(self, message: str, state: str = "muted") -> None:
        """``state``: "ok", "warning", "error" or "muted"."""
        self.anki_status_label.setText(message)
        self.anki_status_label.setStyleSheet(Theme.get_status_text_style(state))

    def set_anki_busy(self, busy: bool) -> None:
        for button in (self.refresh_button, self.create_deck_button, self.start_anki_button):
            button.setEnabled(not busy)

    # ---- results ------------------------------------------------------
    def connect_url(self) -> str:
        return self.url_edit.text().strip()

    def values(self) -> dict:
        return {
            "anki": {
                "connect_url": self.connect_url(),
                "deck_name": self.deck_combo.currentText().strip(),
                "note_type": self.note_type_combo.currentText().strip(),
                "sentence_field": self.sentence_field_combo.currentText().strip(),
                "translation_field": self.translation_field_combo.currentText().strip(),
                "tags": self.tags_edit.text().replace(",", " ").split(),
            },
            "learning_language": self.learning_combo.currentData(),
            "native_language": self.native_combo.currentData(),
            "translation_mode": self.translation_combo.currentData(),
            "prefetch_enabled": self.prefetch_checkbox.isChecked(),
            "theme_mode": self.theme_combo.currentData(),
        }

    # ---- helpers ------------------------------------------------------
    def _on_note_type_changed(self, note_type: str) -> None:
        fields = self._fields_by_note_type.get(note_type)
        if not fields:
            return
        self._replace_items(self.sentence_field_combo, fields, fallback_index=0)
        self._replace_items(self.translation_field_combo, fields, fallback_index=min(1, len(fields) - 1))

    @staticmethod
    def _set_combo_text(combo: QComboBox, text: str) -> None:
        index = combo.findText(text)
        if index >= 0:
            combo.setCurrentIndex(index)
        else:
            combo.setEditText(text)

    @staticmethod
    def _replace_items(combo: QComboBox, items: list[str], fallback_index: int | None = None) -> None:
        current = combo.currentText()
        combo.blockSignals(True)
        combo.clear()
        combo.addItems(items)
        combo.blockSignals(False)
        index = combo.findText(current)
        if index >= 0:
            combo.setCurrentIndex(index)
        elif fallback_index is not None and items:
            combo.setCurrentIndex(fallback_index)
        else:
            combo.setEditText(current)

    @staticmethod
    def _select_data(combo: QComboBox, data) -> None:
        index = combo.findData(data)
        if index >= 0:
            combo.setCurrentIndex(index)

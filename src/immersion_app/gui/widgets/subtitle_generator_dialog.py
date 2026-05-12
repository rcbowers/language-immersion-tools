from PySide6.QtWidgets import QComboBox, QDialog, QHBoxLayout, QLabel, QLineEdit, QProgressBar, QPushButton, QVBoxLayout

from immersion_app.gui.theme import Theme


class SubtitleGeneratorDialog(QDialog):
    def __init__(self, parent=None, default_language="es"):
        super().__init__(parent)
        self.setWindowTitle("Generate Subtitles")
        self.resize(420, 220)
        self.setStyleSheet(f"QDialog {{ background-color: {Theme.BG}; }}")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        model_row = QHBoxLayout()
        model_label = QLabel("Model:")
        model_label.setStyleSheet(Theme.get_label_style("body"))
        model_row.addWidget(model_label)
        self.model_combo = QComboBox()
        self.model_combo.addItems(["tiny", "base", "small", "medium"])
        self.model_combo.setCurrentText("base")
        model_row.addWidget(self.model_combo)
        layout.addLayout(model_row)

        language_row = QHBoxLayout()
        lang_label = QLabel("Language:")
        lang_label.setStyleSheet(Theme.get_label_style("body"))
        language_row.addWidget(lang_label)
        self.language_input = QLineEdit(default_language or "es")
        self.language_input.setStyleSheet(Theme.get_input_style())
        language_row.addWidget(self.language_input)
        layout.addLayout(language_row)

        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet(Theme.get_label_style("caption"))
        layout.addWidget(self.status_label)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        button_row = QHBoxLayout()
        button_row.setSpacing(8)
        start_button = QPushButton("Generate")
        start_button.setStyleSheet(Theme.get_button_style("primary"))
        cancel_button = QPushButton("Cancel")
        cancel_button.setStyleSheet(Theme.get_button_style("secondary"))
        start_button.clicked.connect(self.accept)
        cancel_button.clicked.connect(self.reject)
        button_row.addWidget(start_button)
        button_row.addWidget(cancel_button)
        layout.addLayout(button_row)

    def refresh_theme(self):
        self.setStyleSheet(f"QDialog {{ background-color: {Theme.BG}; }}")
        self.language_input.setStyleSheet(Theme.get_input_style())
        self.status_label.setStyleSheet(Theme.get_label_style("caption"))

    def selected_model(self):
        return self.model_combo.currentText()

    def selected_language(self):
        return self.language_input.text().strip()

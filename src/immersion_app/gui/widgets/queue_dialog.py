from PySide6.QtWidgets import QDialog, QHBoxLayout, QListWidget, QPushButton, QVBoxLayout

from immersion_app.gui.theme import Theme


class QueueDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Queued Cards")
        self.resize(720, 420)
        self.setStyleSheet(f"QDialog {{ background-color: {Theme.BG}; }}")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        self.list_widget = QListWidget()
        self.list_widget.setStyleSheet(
            f"""
            QListWidget {{
                background-color: {Theme.SURFACE};
                color: {Theme.TEXT};
                border: 1px solid {Theme.BORDER};
                border-radius: 8px;
                padding: 6px;
            }}
            """
        )
        layout.addWidget(self.list_widget, stretch=1)

        button_row = QHBoxLayout()
        self.process_button = QPushButton("Process Queue")
        self.process_button.setStyleSheet(Theme.get_button_style("primary"))
        self.close_button = QPushButton("Close")
        self.close_button.setStyleSheet(Theme.get_button_style("secondary"))
        self.close_button.clicked.connect(self.close)
        button_row.addWidget(self.process_button)
        button_row.addWidget(self.close_button)
        layout.addLayout(button_row)

    def refresh_theme(self):
        self.setStyleSheet(f"QDialog {{ background-color: {Theme.BG}; }}")
        self.process_button.setStyleSheet(Theme.get_button_style("primary"))
        self.close_button.setStyleSheet(Theme.get_button_style("secondary"))

    def refresh(self, entries):
        self.list_widget.clear()
        for entry in entries:
            sentence = entry.get("sentence", "")
            word = entry.get("word", "")
            translation = entry.get("translation", "")
            self.list_widget.addItem(f"{word} -> {translation} | {sentence}")

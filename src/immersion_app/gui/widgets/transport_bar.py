"""
Transport bar widget for video playback control.

Provides play/pause, replay, scrubber, speed control, and volume.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QPushButton,
    QSlider,
    QLabel,
    QComboBox,
    QSizePolicy,
)

from immersion_app.gui.theme import Theme


class TransportBar(QWidget):
    """
    Video transport controls bar.

    Contains play/pause, replay, time display, scrubber, speed, CC, and volume.
    """

    play_pause_clicked = Signal()
    replay_clicked = Signal()
    seek_requested = Signal(int)  # milliseconds
    speed_changed = Signal(float)  # 0.5 to 2.0
    slider_pressed = Signal()
    slider_released = Signal()
    slider_moved = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setFixedHeight(Theme.TRANSPORT_BAR_HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._build_ui()

    def _build_ui(self):
        """Build the transport bar UI."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(12)

        # Play/Pause button (primary action)
        self.play_pause_button = QPushButton("▶")
        self.play_pause_button.setFixedSize(32, 32)
        self.play_pause_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {Theme.ACCENT};
                color: white;
                border: none;
                border-radius: 16px;
                font-size: 14px;
                font-weight: {Theme.FONT_WEIGHT_SEMIBOLD};
            }}
            QPushButton:hover {{
                background-color: #4a5ce6;
            }}
            QPushButton:pressed {{
                background-color: #3d4ed9;
            }}
        """)
        self.play_pause_button.clicked.connect(self.play_pause_clicked.emit)
        layout.addWidget(self.play_pause_button)

        # Replay button (jump to subtitle start)
        self.replay_button = QPushButton("↻")
        self.replay_button.setFixedSize(28, 28)
        self.replay_button.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 16px;
            }}
            QPushButton:hover {{
                background-color: rgba(255, 255, 255, 0.1);
            }}
            QPushButton:pressed {{
                background-color: rgba(255, 255, 255, 0.2);
            }}
        """)
        self.replay_button.clicked.connect(self.replay_clicked.emit)
        layout.addWidget(self.replay_button)

        # Time display
        self.time_label = QLabel("00:00 / 00:00")
        self.time_label.setFixedWidth(110)
        self.time_label.setStyleSheet(f"""
            QLabel {{
                color: white;
                font-family: {Theme.FONT_MONO};
                font-size: 11px;
                font-weight: {Theme.FONT_WEIGHT_MEDIUM};
            }}
        """)
        layout.addWidget(self.time_label)

        # Scrubber (position slider)
        self.position_slider = QSlider(Qt.Orientation.Horizontal)
        self.position_slider.setRange(0, 0)
        self.position_slider.setStyleSheet(f"""
            QSlider::groove:horizontal {{
                background: rgba(255, 255, 255, 0.2);
                height: 4px;
                border-radius: 2px;
            }}
            QSlider::handle:horizontal {{
                background: {Theme.ACCENT};
                width: 12px;
                height: 12px;
                margin: -4px 0;
                border-radius: 6px;
            }}
            QSlider::handle:horizontal:hover {{
                background: #4a5ce6;
            }}
            QSlider::sub-page:horizontal {{
                background: {Theme.ACCENT};
                border-radius: 2px;
            }}
        """)
        self.position_slider.sliderPressed.connect(self.slider_pressed.emit)
        self.position_slider.sliderReleased.connect(self.slider_released.emit)
        self.position_slider.sliderMoved.connect(self.slider_moved.emit)
        layout.addWidget(self.position_slider, stretch=1)

        # Speed control
        self.speed_combo = QComboBox()
        self.speed_combo.addItems(["0.5x", "0.75x", "1x", "1.25x", "1.5x", "2x"])
        self.speed_combo.setCurrentText("1x")
        self.speed_combo.setFixedWidth(70)
        self.speed_combo.setStyleSheet(f"""
            QComboBox {{
                background-color: rgba(255, 255, 255, 0.1);
                color: white;
                border: 1px solid rgba(255, 255, 255, 0.2);
                border-radius: 4px;
                padding: 4px 8px;
                font-family: {Theme.FONT_FAMILY}, {Theme.FONT_FALLBACK};
                font-size: 11px;
                font-weight: {Theme.FONT_WEIGHT_MEDIUM};
            }}
            QComboBox:hover {{
                background-color: rgba(255, 255, 255, 0.15);
            }}
            QComboBox::drop-down {{
                border: none;
            }}
            QComboBox::down-arrow {{
                image: none;
                border-left: 3px solid transparent;
                border-right: 3px solid transparent;
                border-top: 4px solid white;
                margin-right: 5px;
            }}
            QComboBox QAbstractItemView {{
                background-color: #2a2a2a;
                color: white;
                selection-background-color: {Theme.ACCENT};
                border: 1px solid rgba(255, 255, 255, 0.2);
            }}
        """)
        self.speed_combo.currentTextChanged.connect(self._on_speed_changed)
        layout.addWidget(self.speed_combo)

        # CC toggle (for future dual-language feature)
        self.cc_button = QPushButton("CC")
        self.cc_button.setFixedSize(32, 24)
        self.cc_button.setCheckable(True)
        self.cc_button.setChecked(True)
        self.cc_button.setStyleSheet(f"""
            QPushButton {{
                background-color: rgba(255, 255, 255, 0.1);
                color: white;
                border: 1px solid rgba(255, 255, 255, 0.2);
                border-radius: 4px;
                font-family: {Theme.FONT_FAMILY}, {Theme.FONT_FALLBACK};
                font-size: 10px;
                font-weight: {Theme.FONT_WEIGHT_BOLD};
            }}
            QPushButton:checked {{
                background-color: {Theme.ACCENT};
                border-color: {Theme.ACCENT};
            }}
            QPushButton:hover {{
                background-color: rgba(255, 255, 255, 0.2);
            }}
        """)
        layout.addWidget(self.cc_button)

        # Volume slider
        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(100)
        self.volume_slider.setFixedWidth(80)
        self.volume_slider.setStyleSheet(f"""
            QSlider::groove:horizontal {{
                background: rgba(255, 255, 255, 0.2);
                height: 3px;
                border-radius: 1px;
            }}
            QSlider::handle:horizontal {{
                background: white;
                width: 10px;
                height: 10px;
                margin: -4px 0;
                border-radius: 5px;
            }}
            QSlider::sub-page:horizontal {{
                background: white;
                border-radius: 1px;
            }}
        """)
        layout.addWidget(self.volume_slider)
        self.refresh_theme()

    def _on_speed_changed(self, text):
        """Parse speed text and emit signal."""
        try:
            speed = float(text.rstrip('x'))
            self.speed_changed.emit(speed)
        except ValueError:
            pass

    def set_play_state(self, is_playing: bool):
        """Update play/pause button state."""
        self.play_pause_button.setText("⏸" if is_playing else "▶")

    def set_time(self, position_ms: int, duration_ms: int):
        """Update time display."""
        pos_str = self._format_time(position_ms)
        dur_str = self._format_time(duration_ms)
        self.time_label.setText(f"{pos_str} / {dur_str}")

    def set_position(self, position_ms: int):
        """Update slider position without triggering signals."""
        self.position_slider.blockSignals(True)
        self.position_slider.setValue(position_ms)
        self.position_slider.blockSignals(False)

    def set_duration(self, duration_ms: int):
        """Update slider range."""
        self.position_slider.setRange(0, duration_ms)

    def set_volume(self, volume: float):
        """Set volume (0.0 to 1.0)."""
        self.volume_slider.blockSignals(True)
        self.volume_slider.setValue(int(volume * 100))
        self.volume_slider.blockSignals(False)

    def refresh_theme(self):
        self.setStyleSheet(f"""
            QWidget {{
                background-color: rgba(0, 0, 0, 0.9);
            }}
        """)
        self.play_pause_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {Theme.ACCENT};
                color: white;
                border: none;
                border-radius: 16px;
                font-size: 14px;
                font-weight: {Theme.FONT_WEIGHT_SEMIBOLD};
            }}
            QPushButton:hover {{
                background-color: #4a5ce6;
            }}
            QPushButton:pressed {{
                background-color: #3d4ed9;
            }}
        """)
        self.replay_button.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 16px;
            }}
            QPushButton:hover {{
                background-color: rgba(255, 255, 255, 0.1);
            }}
            QPushButton:pressed {{
                background-color: rgba(255, 255, 255, 0.2);
            }}
        """)
        self.time_label.setStyleSheet(f"""
            QLabel {{
                color: white;
                font-family: {Theme.FONT_MONO};
                font-size: 11px;
                font-weight: {Theme.FONT_WEIGHT_MEDIUM};
            }}
        """)
        self.position_slider.setStyleSheet(f"""
            QSlider::groove:horizontal {{
                background: rgba(255, 255, 255, 0.2);
                height: 4px;
                border-radius: 2px;
            }}
            QSlider::handle:horizontal {{
                background: {Theme.ACCENT};
                width: 12px;
                height: 12px;
                margin: -4px 0;
                border-radius: 6px;
            }}
            QSlider::handle:horizontal:hover {{
                background: #4a5ce6;
            }}
            QSlider::sub-page:horizontal {{
                background: {Theme.ACCENT};
                border-radius: 2px;
            }}
        """)
        self.speed_combo.setStyleSheet(f"""
            QComboBox {{
                background-color: rgba(255, 255, 255, 0.1);
                color: white;
                border: 1px solid rgba(255, 255, 255, 0.2);
                border-radius: 4px;
                padding: 4px 8px;
                font-family: {Theme.FONT_FAMILY}, {Theme.FONT_FALLBACK};
                font-size: 11px;
                font-weight: {Theme.FONT_WEIGHT_MEDIUM};
            }}
            QComboBox:hover {{
                background-color: rgba(255, 255, 255, 0.15);
            }}
            QComboBox::drop-down {{
                border: none;
            }}
            QComboBox::down-arrow {{
                image: none;
                border-left: 3px solid transparent;
                border-right: 3px solid transparent;
                border-top: 4px solid white;
                margin-right: 5px;
            }}
            QComboBox QAbstractItemView {{
                background-color: #2a2a2a;
                color: white;
                selection-background-color: {Theme.ACCENT};
                border: 1px solid rgba(255, 255, 255, 0.2);
            }}
        """)
        self.cc_button.setStyleSheet(f"""
            QPushButton {{
                background-color: rgba(255, 255, 255, 0.1);
                color: white;
                border: 1px solid rgba(255, 255, 255, 0.2);
                border-radius: 4px;
                font-family: {Theme.FONT_FAMILY}, {Theme.FONT_FALLBACK};
                font-size: 10px;
                font-weight: {Theme.FONT_WEIGHT_BOLD};
            }}
            QPushButton:checked {{
                background-color: {Theme.ACCENT};
                border-color: {Theme.ACCENT};
            }}
            QPushButton:hover {{
                background-color: rgba(255, 255, 255, 0.2);
            }}
        """)
        self.volume_slider.setStyleSheet(f"""
            QSlider::groove:horizontal {{
                background: rgba(255, 255, 255, 0.2);
                height: 3px;
                border-radius: 1px;
            }}
            QSlider::handle:horizontal {{
                background: white;
                width: 10px;
                height: 10px;
                margin: -4px 0;
                border-radius: 5px;
            }}
            QSlider::sub-page:horizontal {{
                background: white;
                border-radius: 1px;
            }}
        """)
        self.volume_slider.blockSignals(False)

    @staticmethod
    def _format_time(ms: int) -> str:
        """Format milliseconds as MM:SS."""
        total_seconds = ms // 1000
        minutes = total_seconds // 60
        seconds = total_seconds % 60
        return f"{minutes:02d}:{seconds:02d}"

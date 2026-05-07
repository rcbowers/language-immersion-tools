"""Unit tests for mode management."""

import unittest
from PySide6.QtCore import QObject
from immersion_app.core.mode import WorkspaceMode, ModeManager


class SignalCapture(QObject):
    """Helper to capture signals for testing."""
    def __init__(self):
        super().__init__()
        self.mode_changes = []
        self.failures = []

    def on_mode_changed(self, mode):
        self.mode_changes.append(mode)

    def on_transition_failed(self, mode_name, reason):
        self.failures.append((mode_name, reason))


class ModeManagerTests(unittest.TestCase):
    """Test cases for ModeManager."""

    def test_initial_state(self):
        """Test initial state is WELCOME."""
        manager = ModeManager()
        self.assertEqual(manager.current_mode, WorkspaceMode.WELCOME)

    def test_transitions_with_content(self):
        """Test successful mode transitions when content is loaded."""
        manager = ModeManager()
        capture = SignalCapture()
        manager.mode_changed.connect(capture.on_mode_changed)

        # Load PDF and switch to PDF mode
        manager.set_pdf_loaded(True)
        self.assertTrue(manager.set_mode(WorkspaceMode.PDF))
        self.assertEqual(manager.current_mode, WorkspaceMode.PDF)
        self.assertEqual(len(capture.mode_changes), 1)
        self.assertEqual(capture.mode_changes[0], WorkspaceMode.PDF)

        # Load video and switch to video mode
        manager.set_video_loaded(True)
        self.assertTrue(manager.set_mode(WorkspaceMode.VIDEO))
        self.assertEqual(manager.current_mode, WorkspaceMode.VIDEO)
        self.assertEqual(len(capture.mode_changes), 2)

    def test_blocks_transition_without_content(self):
        """Test that mode transitions fail when content is not loaded."""
        manager = ModeManager()
        capture = SignalCapture()
        manager.mode_transition_failed.connect(capture.on_transition_failed)

        # Try to switch to PDF mode without loading PDF
        self.assertFalse(manager.set_mode(WorkspaceMode.PDF))
        self.assertEqual(manager.current_mode, WorkspaceMode.WELCOME)
        self.assertEqual(len(capture.failures), 1)
        self.assertEqual(capture.failures[0][0], "PDF")
        self.assertIn("No PDF loaded", capture.failures[0][1])

    def test_force_transition(self):
        """Test force parameter allows transition without content."""
        manager = ModeManager()

        # Force transition to PDF mode without content
        self.assertTrue(manager.set_mode(WorkspaceMode.PDF, force=True))
        self.assertEqual(manager.current_mode, WorkspaceMode.PDF)

    def test_auto_return_to_welcome(self):
        """Test automatic return to WELCOME when content is unloaded."""
        manager = ModeManager()

        # Load and switch to PDF
        manager.set_pdf_loaded(True)
        manager.set_mode(WorkspaceMode.PDF, force=True)
        self.assertEqual(manager.current_mode, WorkspaceMode.PDF)

        # Unload PDF should auto-return to WELCOME
        manager.set_pdf_loaded(False)
        self.assertEqual(manager.current_mode, WorkspaceMode.WELCOME)

    def test_mode_string(self):
        """Test mode_string returns correct strings."""
        manager = ModeManager()

        self.assertEqual(manager.mode_string(), "")

        manager.set_pdf_loaded(True)
        manager.set_mode(WorkspaceMode.PDF)
        self.assertEqual(manager.mode_string(), "pdf")

        manager.set_video_loaded(True)
        manager.set_mode(WorkspaceMode.VIDEO)
        self.assertEqual(manager.mode_string(), "video")

    def test_no_change_same_mode(self):
        """Test setting same mode returns True and doesn't emit signal."""
        manager = ModeManager()
        capture = SignalCapture()
        manager.mode_changed.connect(capture.on_mode_changed)

        # Already in WELCOME, set to WELCOME again
        self.assertTrue(manager.set_mode(WorkspaceMode.WELCOME))
        self.assertEqual(len(capture.mode_changes), 0)


if __name__ == '__main__':
    unittest.main()

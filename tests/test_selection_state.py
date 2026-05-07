"""Unit tests for selection state management."""

import unittest
from immersion_app.core.selection_state import PdfSelectionState, VideoSelectionState, SelectionState


class SelectionStateTests(unittest.TestCase):
    """Test cases for selection state classes."""

    def test_pdf_selection_state_creation(self):
        """Test PDF selection state creation and defaults."""
        state = PdfSelectionState()
        self.assertEqual(state.selected_words, [])
        self.assertEqual(state.highlight_bboxes, [])
        self.assertIsNone(state.anchor_key)
        self.assertTrue(state.is_empty())

    def test_pdf_selection_state_with_data(self):
        """Test PDF selection state with data."""
        words = [("word1", 0, 0, 10, 10), ("word2", 10, 0, 20, 10)]
        bboxes = [(0.0, 0.0, 10.0, 10.0), (10.0, 0.0, 20.0, 10.0)]
        anchor = (0, 0)

        state = PdfSelectionState(
            selected_words=words,
            highlight_bboxes=bboxes,
            anchor_key=anchor
        )

        self.assertEqual(len(state.selected_words), 2)
        self.assertEqual(len(state.highlight_bboxes), 2)
        self.assertEqual(state.anchor_key, anchor)
        self.assertFalse(state.is_empty())

    def test_pdf_selection_state_clear(self):
        """Test clearing PDF selection state."""
        state = PdfSelectionState(
            selected_words=[("word", 0, 0, 10, 10)],
            highlight_bboxes=[(0.0, 0.0, 10.0, 10.0)],
            anchor_key=(0, 0)
        )

        state.clear()

        self.assertEqual(state.selected_words, [])
        self.assertEqual(state.highlight_bboxes, [])
        self.assertIsNone(state.anchor_key)
        self.assertTrue(state.is_empty())

    def test_video_selection_state_creation(self):
        """Test video selection state creation and defaults."""
        state = VideoSelectionState()
        self.assertEqual(state.selected_indices, [])
        self.assertIsNone(state.anchor)
        self.assertTrue(state.is_empty())

    def test_video_selection_state_with_data(self):
        """Test video selection state with data."""
        indices = [0, 1, 2]
        anchor = (0, 5)

        state = VideoSelectionState(
            selected_indices=indices,
            anchor=anchor
        )

        self.assertEqual(len(state.selected_indices), 3)
        self.assertEqual(state.anchor, anchor)
        self.assertFalse(state.is_empty())

    def test_video_selection_state_clear(self):
        """Test clearing video selection state."""
        state = VideoSelectionState(
            selected_indices=[0, 1, 2],
            anchor=(0, 5)
        )

        state.clear()

        self.assertEqual(state.selected_indices, [])
        self.assertIsNone(state.anchor)
        self.assertTrue(state.is_empty())

    def test_selection_state_creation(self):
        """Test unified selection state creation."""
        state = SelectionState()

        self.assertEqual(state.word, "")
        self.assertEqual(state.sentence, "")
        self.assertEqual(state.translation, "")
        self.assertIsInstance(state.pdf, PdfSelectionState)
        self.assertIsInstance(state.video, VideoSelectionState)

    def test_selection_state_with_data(self):
        """Test unified selection state with data."""
        state = SelectionState(
            word="test",
            sentence="This is a test sentence",
            translation="prueba"
        )

        self.assertEqual(state.word, "test")
        self.assertEqual(state.sentence, "This is a test sentence")
        self.assertEqual(state.translation, "prueba")

    def test_selection_state_clear_all(self):
        """Test clearing all selection state."""
        state = SelectionState(
            word="test",
            sentence="sentence",
            translation="translation"
        )

        # Add PDF selection
        state.pdf.selected_words = [("word", 0, 0, 10, 10)]
        state.pdf.highlight_bboxes = [(0.0, 0.0, 10.0, 10.0)]
        state.pdf.anchor_key = (0, 0)

        # Add video selection
        state.video.selected_indices = [0, 1]
        state.video.anchor = (0, 5)

        # Clear everything
        state.clear_all()

        self.assertEqual(state.word, "")
        self.assertEqual(state.sentence, "")
        self.assertEqual(state.translation, "")
        self.assertTrue(state.pdf.is_empty())
        self.assertTrue(state.video.is_empty())

    def test_selection_state_mode_separation(self):
        """Test that PDF and video selections are independent."""
        state = SelectionState()

        # Set PDF selection
        state.pdf.selected_words = [("word", 0, 0, 10, 10)]
        self.assertFalse(state.pdf.is_empty())
        self.assertTrue(state.video.is_empty())

        # Set video selection
        state.video.selected_indices = [0, 1]
        self.assertFalse(state.video.is_empty())

        # Clear PDF doesn't affect video
        state.pdf.clear()
        self.assertTrue(state.pdf.is_empty())
        self.assertFalse(state.video.is_empty())


if __name__ == '__main__':
    unittest.main()

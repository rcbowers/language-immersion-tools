import unittest

from immersion_app.core.video_service import VideoService
from immersion_app.media.subtitle_parser import SRTParser


class VideoServiceTests(unittest.TestCase):
    def test_resolve_selection_range_extends_from_anchor(self):
        service = VideoService()

        selected_indices, anchor = service.resolve_selection_range(
            token_index=3,
            shift_pressed=True,
            current_anchor=(5, 1),
            subtitle_index=5,
            token_count=6,
        )

        self.assertEqual(selected_indices, [1, 2, 3])
        self.assertEqual(anchor, (5, 1))

    def test_subtitle_lookup_applies_offset(self):
        service = VideoService(subtitle_offset_ms=500)
        service.subtitle_parser = SRTParser.from_text(
            "1\n00:00:01,000 --> 00:00:02,000\nhola mundo"
        )

        subtitle = service.subtitle_at_position(1600)

        self.assertIsNotNone(subtitle)
        self.assertEqual(subtitle.text, "hola mundo")


if __name__ == "__main__":
    unittest.main()

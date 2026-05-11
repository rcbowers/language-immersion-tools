import io
import logging
import unittest
from unittest.mock import patch

from immersion_app.core.logging_config import setup_logging


class LoggingConfigTests(unittest.TestCase):
    def tearDown(self):
        root_logger = logging.getLogger()
        for handler in list(root_logger.handlers):
            handler.close()
            root_logger.removeHandler(handler)

    def test_setup_logging_writes_info_to_terminal_stream(self):
        stream = io.StringIO()

        with patch("immersion_app.core.logging_config.sys.stderr", stream):
            log_file = setup_logging()
            logger = logging.getLogger("tests.logging")
            logger.info("terminal-visible message")

        terminal_output = stream.getvalue()
        self.assertTrue(log_file.exists())
        self.assertIn("[INFO] Logging system initialized:", terminal_output)
        self.assertIn("[INFO] terminal-visible message", terminal_output)

    def test_setup_logging_keeps_debug_in_file_only(self):
        stream = io.StringIO()

        with patch("immersion_app.core.logging_config.sys.stderr", stream):
            log_file = setup_logging()
            logger = logging.getLogger("tests.logging")
            logger.debug("file-only debug message")

        terminal_output = stream.getvalue()
        self.assertNotIn("file-only debug message", terminal_output)
        self.assertIn("file-only debug message", log_file.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()

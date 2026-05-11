"""Comprehensive logging configuration for LinguaLoop.

Provides dual-output logging:
- File logs: DEBUG level, detailed format with timestamps and module info
- UI console: INFO level, simplified format for user display

Creates timestamped log files for each session in data/logs/.
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from immersion_app.core.paths import LOG_DIR

if TYPE_CHECKING:
    from immersion_app.app import ConsoleCapture


class ConsoleCaptureHandler(logging.Handler):
    """Custom logging handler that writes to ConsoleCapture for UI display.

    This handler allows log messages to appear in the UI console pane
    while still being written to the log file with full detail.
    """

    def __init__(self, console_capture: ConsoleCapture, level: int = logging.INFO):
        """Initialize handler with ConsoleCapture instance.

        Args:
            console_capture: The ConsoleCapture instance from app.py
            level: Minimum log level to display in UI (default: INFO)
        """
        super().__init__(level)
        self.console_capture = console_capture
        # Simplified format for UI display: [LEVEL] message
        formatter = logging.Formatter('[%(levelname)s] %(message)s')
        self.setFormatter(formatter)

    def emit(self, record: logging.LogRecord) -> None:
        """Format log record and write to ConsoleCapture.

        Args:
            record: The log record to emit
        """
        try:
            msg = self.format(record)
            self.console_capture.write(msg + '\n')
        except Exception:
            self.handleError(record)


def _suppress_noisy_loggers() -> None:
    """Suppress verbose third-party library loggers.

    Sets noisy HTTP/networking libraries to WARNING level to prevent
    debug spam from flooding log files.
    """
    noisy_loggers = [
        'hpack.hpack',
        'hpack.table',
        'httpcore.http2',
        'httpcore.http11',
        'httpcore.connection',
        'httpx',
        'urllib3',
        'requests',
    ]

    for logger_name in noisy_loggers:
        logging.getLogger(logger_name).setLevel(logging.WARNING)


def _create_log_filename(prefix: str = "session") -> str:
    """Create timestamped log filename.

    Args:
        prefix: Filename prefix (default: "session")

    Returns:
        Filename in format: {prefix}_YYYY-MM-DD_HHMMSS.log
    """
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    return f"{prefix}_{timestamp}.log"


def setup_logging(
    console_capture: ConsoleCapture,
    level: int = logging.INFO,
) -> Path:
    """Configure dual-output logging system for GUI application.

    Sets up two handlers:
    1. FileHandler: Writes DEBUG-level logs to timestamped file with detailed format
    2. ConsoleCaptureHandler: Writes INFO-level logs to UI console with simple format

    Args:
        console_capture: ConsoleCapture instance for UI output
        level: Minimum log level for UI console (default: INFO)

    Returns:
        Path to created log file

    Example:
        >>> from immersion_app.app import ConsoleCapture
        >>> console = ConsoleCapture()
        >>> log_file = setup_logging(console)
        >>> import logging
        >>> logger = logging.getLogger(__name__)
        >>> logger.info("Application started")
    """
    # Ensure log directory exists
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    # Create timestamped log file
    log_filename = _create_log_filename("session")
    log_file_path = LOG_DIR / log_filename

    # Configure root logger to DEBUG level (handlers filter individually)
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    # Clear any existing handlers (avoid duplicates on reconfiguration)
    root_logger.handlers.clear()

    # Create file handler with detailed format
    file_handler = logging.FileHandler(log_file_path, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(
        '[%(asctime)s] [%(levelname)-8s] [%(name)s:%(funcName)s:%(lineno)d] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(file_formatter)
    root_logger.addHandler(file_handler)

    # Create console capture handler with simplified format
    console_handler = ConsoleCaptureHandler(console_capture, level=level)
    root_logger.addHandler(console_handler)

    # Suppress noisy third-party loggers
    _suppress_noisy_loggers()

    # Log initialization success
    logger = logging.getLogger(__name__)
    logger.info(f"Logging system initialized: {log_file_path}")
    logger.debug(f"File log level: DEBUG, UI console level: {logging.getLevelName(level)}")

    return log_file_path


def setup_cli_logging(level: int = logging.INFO) -> Path:
    """Configure logging for CLI tools (file output only, no UI console).

    Sets up FileHandler that writes to timestamped CLI log file with detailed format.

    Args:
        level: Minimum log level (default: INFO)

    Returns:
        Path to created log file

    Example:
        >>> from immersion_app.core.logging_config import setup_cli_logging
        >>> log_file = setup_cli_logging()
        >>> import logging
        >>> logger = logging.getLogger(__name__)
        >>> logger.info("CLI tool started")
    """
    # Ensure log directory exists
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    # Create timestamped log file
    log_filename = _create_log_filename("cli")
    log_file_path = LOG_DIR / log_filename

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Clear any existing handlers
    root_logger.handlers.clear()

    # Create file handler with detailed format
    file_handler = logging.FileHandler(log_file_path, encoding='utf-8')
    file_handler.setLevel(level)
    file_formatter = logging.Formatter(
        '[%(asctime)s] [%(levelname)-8s] [%(name)s:%(funcName)s:%(lineno)d] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(file_formatter)
    root_logger.addHandler(file_handler)

    # Also add console handler for CLI tools (stderr)
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(level)
    console_formatter = logging.Formatter('[%(levelname)s] %(message)s')
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)

    # Suppress noisy third-party loggers
    _suppress_noisy_loggers()

    # Log initialization success
    logger = logging.getLogger(__name__)
    logger.info(f"CLI logging initialized: {log_file_path}")

    return log_file_path


def get_logger(name: str) -> logging.Logger:
    """Convenience function to get a logger for a module.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Logger instance

    Example:
        >>> logger = get_logger(__name__)
        >>> logger.info("Message")
    """
    return logging.getLogger(name)

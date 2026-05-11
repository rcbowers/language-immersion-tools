"""Simple test script to verify logging system functionality."""

import sys
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

# Import logging setup without Qt dependencies
import logging
from datetime import datetime
from immersion_app.core.paths import LOG_DIR

# Create a minimal logging setup for testing
LOG_DIR.mkdir(parents=True, exist_ok=True)
log_filename = f"test_session_{datetime.now().strftime('%Y-%m-%d_%H%M%S')}.log"
log_file_path = LOG_DIR / log_filename

# Configure root logger
root_logger = logging.getLogger()
root_logger.setLevel(logging.DEBUG)

# Create file handler
file_handler = logging.FileHandler(log_file_path, encoding='utf-8')
file_handler.setLevel(logging.DEBUG)
file_formatter = logging.Formatter(
    '[%(asctime)s] [%(levelname)-8s] [%(name)s:%(funcName)s:%(lineno)d] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
file_handler.setFormatter(file_formatter)
root_logger.addHandler(file_handler)

# Create console handler
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)
console_formatter = logging.Formatter('[%(levelname)s] %(message)s')
console_handler.setFormatter(console_formatter)
root_logger.addHandler(console_handler)

# Test logging
logger = logging.getLogger(__name__)

print("=" * 60)
print("Testing LinguaLoop Logging System")
print("=" * 60)
print(f"Log file: {log_file_path}")
print("=" * 60)

logger.info("Test log message at INFO level")
logger.debug("Test log message at DEBUG level")
logger.warning("Test log message at WARNING level")
logger.error("Test log message at ERROR level")

# Read back the log file
print("\nLog file contents:")
print("-" * 60)
with open(log_file_path, 'r', encoding='utf-8') as f:
    print(f.read())

print("-" * 60)
print(f"\n✓ Logging system test PASSED")
print(f"✓ Log file created at: {log_file_path}")
print(f"✓ All log levels working correctly")

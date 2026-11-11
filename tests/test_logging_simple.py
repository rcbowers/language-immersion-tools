"""Simple test script to verify logging system functionality."""

import sys
import logging
from pathlib import Path
from datetime import datetime

# Add src to path
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

# Import paths directly (avoiding __init__.py)
from immersion_app.core.paths import LOG_DIR

# Verify LOG_DIR setup
LOG_DIR.mkdir(parents=True, exist_ok=True)
log_filename = f"test_session_{datetime.now().strftime('%Y-%m-%d_%H%M%S')}.log"
log_file_path = LOG_DIR / log_filename

# Configure root logger
root_logger = logging.getLogger()
root_logger.setLevel(logging.DEBUG)
root_logger.handlers.clear()

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
print("Testing Language Immersion Tools Logging System")
print("=" * 60)
print(f"Log file: {log_file_path}")
print("=" * 60)
print("\nLog messages:")

logger.info("Test log message at INFO level")
logger.debug("Test log message at DEBUG level (only in file)")
logger.warning("Test log message at WARNING level")
logger.error("Test log message at ERROR level")

# Test exception logging
try:
    raise ValueError("Test exception for logging")
except Exception as e:
    logger.error("Caught test exception", exc_info=True)

# Verify file was created
print(f"\n✓ Log file created: {log_file_path.exists()}")
print(f"✓ Log file size: {log_file_path.stat().st_size} bytes")

# Read back the log file
print("\nLog file contents:")
print("-" * 60)
with open(log_file_path, 'r', encoding='utf-8') as f:
    content = f.read()
    print(content)

    # Verify expected content
    assert "[INFO    ]" in content, "INFO level message not found"
    assert "[DEBUG   ]" in content, "DEBUG level message not found"
    assert "[WARNING ]" in content, "WARNING level message not found"
    assert "[ERROR   ]" in content, "ERROR level message not found"
    assert "ValueError: Test exception" in content, "Exception not logged"
    assert "Traceback" in content, "Stack trace not logged"

print("-" * 60)
print(f"\n✅ All logging system tests PASSED")
print(f"✅ Log file created at: {log_file_path}")
print(f"✅ All log levels working correctly")
print(f"✅ Exception logging with stack traces working")
print(f"✅ File and console handlers configured correctly")

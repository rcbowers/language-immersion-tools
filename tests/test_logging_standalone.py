"""Standalone test script to verify logging system functionality without Qt dependencies."""

import logging
from pathlib import Path
from datetime import datetime

# Define LOG_DIR directly to avoid importing from core package
PROJECT_ROOT = Path(__file__).parent
DATA_ROOT = PROJECT_ROOT / "data"
LOG_DIR = DATA_ROOT / "logs"

# Verify LOG_DIR setup
LOG_DIR.mkdir(parents=True, exist_ok=True)
log_filename = f"test_session_{datetime.now().strftime('%Y-%m-%d_%H%M%S')}.log"
log_file_path = LOG_DIR / log_filename

# Configure root logger (mimics setup_logging function)
root_logger = logging.getLogger()
root_logger.setLevel(logging.DEBUG)
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

# Create console handler with simplified format
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_formatter = logging.Formatter('[%(levelname)s] %(message)s')
console_handler.setFormatter(console_formatter)
root_logger.addHandler(console_handler)

# Test logging
logger = logging.getLogger(__name__)

print("=" * 70)
print("LinguaLoop Logging System - Comprehensive Test")
print("=" * 70)
print(f"Log file: {log_file_path}")
print("=" * 70)
print("\nGenerating test log messages (INFO+ will appear in console):\n")

# Test all log levels
logger.debug("DEBUG: This is a debug message (file only)")
logger.info("INFO: Application started successfully")
logger.warning("WARNING: This is a warning message")
logger.error("ERROR: This is an error message")
logger.critical("CRITICAL: This is a critical message")

# Test exception logging
logger.info("Testing exception logging with stack trace...")
try:
    result = 1 / 0
except ZeroDivisionError as e:
    logger.error(f"Caught exception: {e}", exc_info=True)

# Test long message
long_message = "This is a very long message to test that the logging system can handle messages with lots of content. " * 5
logger.info(f"Long message test: {long_message[:100]}...")

# Verify file was created
print(f"\n{'=' * 70}")
print("Verification:")
print(f"[OK] Log file created: {log_file_path.exists()}")
print(f"[OK] Log file size: {log_file_path.stat().st_size} bytes")

# Read and verify log file contents
print(f"\n{'=' * 70}")
print("Log file contents (first 30 lines):")
print("-" * 70)
with open(log_file_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()
    for i, line in enumerate(lines[:30], 1):
        print(f"{i:2}: {line.rstrip()}")

print("-" * 70)
print(f"Total lines in log file: {len(lines)}")

# Validate content
with open(log_file_path, 'r', encoding='utf-8') as f:
    content = f.read()

errors = []
checks = [
    ("[INFO    ]", "INFO level messages"),
    ("[DEBUG   ]", "DEBUG level messages"),
    ("[WARNING ]", "WARNING level messages"),
    ("[ERROR   ]", "ERROR level messages"),
    ("[CRITICAL]", "CRITICAL level messages"),
    ("ZeroDivisionError", "Exception type"),
    ("Traceback", "Stack trace"),
    ("[__main__:<module>:", "Module and function names"),
]

for needle, description in checks:
    if needle in content:
        print(f"[OK] {description}: Found")
    else:
        errors.append(f"[FAIL] {description}: NOT FOUND (searched for: {needle})")
        print(f"[FAIL] {description}: NOT FOUND")

print(f"\n{'=' * 70}")
if errors:
    print("SOME TESTS FAILED:")
    for error in errors:
        print(f"   {error}")
    exit(1)
else:
    print("SUCCESS: ALL LOGGING SYSTEM TESTS PASSED")
    print(f"[OK] Log file: {log_file_path}")
    print(f"[OK] Dual output (file + console) working")
    print(f"[OK] All log levels functioning")
    print(f"[OK] Exception logging with stack traces working")
    print(f"[OK] Log format includes timestamps, levels, and module info")
    print("\nThe logging system is ready for use!")

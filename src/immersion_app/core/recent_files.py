"""Recent files management for the immersion app."""

from datetime import datetime
from pathlib import Path
import os

MAX_RECENT_FILES = 5


def add_recent_file(user_data: dict, file_path: str, file_type: str, position: dict) -> None:
    """
    Add or update a file in the recent files list.

    Args:
        user_data: User data dict
        file_path: Absolute path to the file
        file_type: "pdf" or "video"
        position: Dict with "page_index" (PDF) or "video_position_ms" (video)
    """
    # Normalize path (absolute, case-insensitive on Windows)
    normalized_path = os.path.normcase(os.path.abspath(file_path))

    # Get or initialize recent files list
    recent_files = user_data.get("recent_files", [])

    # Remove existing entry if duplicate (compare normalized paths)
    recent_files = [
        f for f in recent_files
        if os.path.normcase(os.path.abspath(f.get("path", ""))) != normalized_path
    ]

    # Create new entry
    file_name = os.path.basename(file_path)
    new_entry = {
        "path": file_path,  # Store original path
        "type": file_type,
        "name": file_name,
        "last_opened": datetime.now().isoformat(),
    }

    # Add position data
    if file_type == "pdf":
        new_entry["page_index"] = position.get("page_index", 0)
    else:  # video
        new_entry["video_position_ms"] = position.get("video_position_ms", 0)

    # Add new entry at the top
    recent_files.insert(0, new_entry)

    # Limit to MAX_RECENT_FILES
    recent_files = recent_files[:MAX_RECENT_FILES]

    # Update user data
    user_data["recent_files"] = recent_files


def get_recent_files(user_data: dict, validate_exists: bool = True) -> list:
    """
    Get recent files, optionally filtering out deleted files.

    Args:
        user_data: User data dict
        validate_exists: If True, filter out files that don't exist

    Returns:
        List of recent file dicts, sorted by last_opened (newest first)
    """
    recent_files = user_data.get("recent_files", [])

    if validate_exists:
        # Filter out files that don't exist
        recent_files = [
            f for f in recent_files
            if os.path.exists(f.get("path", ""))
        ]

    return recent_files


def remove_recent_file(user_data: dict, file_path: str) -> None:
    """Remove a file from the recent files list."""
    # Normalize path for comparison
    normalized_path = os.path.normcase(os.path.abspath(file_path))

    recent_files = user_data.get("recent_files", [])

    # Remove matching entry
    recent_files = [
        f for f in recent_files
        if os.path.normcase(os.path.abspath(f.get("path", ""))) != normalized_path
    ]

    user_data["recent_files"] = recent_files


def format_time_ago(timestamp_iso: str) -> str:
    """Format timestamp as human-readable relative time (e.g., '2 days ago')."""
    try:
        timestamp = datetime.fromisoformat(timestamp_iso)
        now = datetime.now()
        delta = now - timestamp

        seconds = delta.total_seconds()

        if seconds < 60:
            return "Just now"
        elif seconds < 3600:
            minutes = int(seconds / 60)
            return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
        elif seconds < 86400:
            hours = int(seconds / 3600)
            return f"{hours} hour{'s' if hours != 1 else ''} ago"
        elif seconds < 604800:
            days = int(seconds / 86400)
            return f"{days} day{'s' if days != 1 else ''} ago"
        elif seconds < 2592000:
            weeks = int(seconds / 604800)
            return f"{weeks} week{'s' if weeks != 1 else ''} ago"
        else:
            months = int(seconds / 2592000)
            return f"{months} month{'s' if months != 1 else ''} ago"
    except Exception:
        return "Unknown"


def format_position_metadata(file_type: str, page_index: int = 0, video_position_ms: int = 0) -> str:
    """
    Format position metadata for display.

    Returns:
        - PDF: "Page 42"
        - Video: "1:23:45" (formatted timestamp)
    """
    if file_type == "pdf":
        return f"Page {page_index + 1}"  # Convert 0-indexed to 1-indexed
    else:  # video
        # Convert milliseconds to HH:MM:SS or MM:SS
        total_seconds = video_position_ms // 1000
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60

        if hours > 0:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        else:
            return f"{minutes}:{seconds:02d}"

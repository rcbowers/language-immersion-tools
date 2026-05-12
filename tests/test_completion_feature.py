"""Quick test script for completion tracking feature."""

import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from immersion_app.core.completion_tracker import CompletionTracker
from immersion_app.core.user_data import default_user_data

def test_completion_tracker():
    """Test the CompletionTracker core functionality."""
    print("Testing CompletionTracker...")

    # Create test user data
    user_data = default_user_data()
    print(f"[OK] User data initialized with progress section: {user_data.get('progress')}")

    # Create tracker
    tracker = CompletionTracker(user_data)
    print("[OK] CompletionTracker created")

    # Test marking page complete
    test_path = "C:\\test\\book.pdf"
    tracker.mark_page_complete(test_path, 0)
    print(f"[OK] Marked page 0 complete")

    # Test querying completion
    is_complete = tracker.is_page_complete(test_path, 0)
    print(f"[OK] Page 0 is complete: {is_complete}")
    assert is_complete, "Page should be marked complete"

    # Test getting completed pages
    completed = tracker.get_completed_pages(test_path)
    print(f"[OK] Completed pages: {completed}")
    assert 0 in completed, "Page 0 should be in completed list"

    # Test completion percentage
    percentage = tracker.get_completion_percentage(test_path, 10)
    print(f"[OK] Completion percentage (1/10): {percentage}%")
    assert percentage == 10.0, "Should be 10%"

    # Test unmarking
    tracker.unmark_page_complete(test_path, 0)
    is_complete = tracker.is_page_complete(test_path, 0)
    print(f"[OK] Page 0 after unmark: {is_complete}")
    assert not is_complete, "Page should not be complete"

    # Test video completion
    video_path = "C:\\test\\video.mp4"
    tracker.mark_video_complete(video_path)
    is_video_complete = tracker.is_video_complete(video_path)
    print(f"[OK] Video is complete: {is_video_complete}")
    assert is_video_complete, "Video should be marked complete"

    print("\n[SUCCESS] All CompletionTracker tests passed!")
    return True

if __name__ == "__main__":
    try:
        test_completion_tracker()
        sys.exit(0)
    except Exception as e:
        print(f"\n[ERROR] Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

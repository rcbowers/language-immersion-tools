# Usage Time Tracking Indicator - Implementation Summary

**Enhancement Date**: 2026-05-12
**Status**: ✅ Complete and Ready for Testing

## Overview

Added a visual indicator to the bottom status bars (both PDF and Video modes) to show when usage time tracking is actively recording time.

## What Was Added

### Visual Indicator

**Appearance:**
- **Idle**: `○` (hollow circle) - Gray/muted color
- **Active**: `●` (filled circle) - Green color (#4CAF50)

**Tooltip:**
- Idle: "Usage tracking: Idle"
- Active: "Usage tracking: Active (recording time)"

**Location:**
- **PDF Mode**: Right side of PDF status bar, before "Translation" badge
- **Video Mode**: Transport bar, after speed selector, before CC button

### Active Status Logic

The indicator shows **Active** (●) when ALL of these conditions are met:
1. ✅ A session is running (PDF/video is loaded)
2. ✅ Window has focus
3. ✅ User activity within the last 2 minutes

Otherwise, it shows **Idle** (○).

## Files Modified

### 1. Core: UsageTimeTracker
**File**: `src/immersion_app/core/usage_time_tracker.py`

**Changes:**
- Added `active_status_changed = Signal(bool)` - Emits when active status changes
- Added `_is_active: bool` - Tracks current active state
- Added `is_currently_active() -> bool` - Query method to check if tracking is active
- Added `_update_active_status()` - Internal method to check and emit status changes
- Updated all relevant methods to call `_update_active_status()`:
  - `set_window_focused()`
  - `on_document_loaded()`
  - `on_video_loaded()`
  - `record_activity()`
  - `_reset_session_state()`
  - `_check_inactivity()`

### 2. GUI: PDFStatusBar
**File**: `src/immersion_app/gui/widgets/pdf_status_bar.py`

**Changes:**
- Added `usage_tracking_label` widget in right region
- Added `_get_usage_tracking_style(active: bool)` - Returns CSS for indicator
- Added `set_usage_tracking_active(active: bool)` - Updates indicator appearance
- Updated `refresh_theme()` to apply tracking indicator style

### 3. GUI: TransportBar
**File**: `src/immersion_app/gui/widgets/transport_bar.py`

**Changes:**
- Added `usage_tracking_label` widget after speed control
- Added `_get_usage_tracking_style(active: bool)` - Returns CSS for indicator
- Added `set_usage_tracking_active(active: bool)` - Updates indicator appearance
- Updated `refresh_theme()` to apply tracking indicator style

### 4. GUI: MainWindow
**File**: `src/immersion_app/gui/main_window.py`

**Changes:**
- Connected `usage_tracker.active_status_changed` signal to `_on_usage_tracking_status_changed`
- Added `_on_usage_tracking_status_changed(is_active: bool)` method:
  - Updates PDF status bar indicator
  - Updates transport bar indicator
  - Uses `hasattr()` checks for safety (status bars may not exist yet)

## How It Works

```
┌─────────────────────────────────────────────────────────────┐
│                  User Activity Detected                      │
│  (word selection, translation, mouse/keyboard)              │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ↓
┌─────────────────────────────────────────────────────────────┐
│          UsageTimeTracker.record_activity()                  │
│  - Adds timestamp to buffer                                  │
│  - Calls _update_active_status()                            │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ↓
┌─────────────────────────────────────────────────────────────┐
│          UsageTimeTracker._update_active_status()            │
│  - Calls is_currently_active()                              │
│  - Compares to previous state                                │
│  - If changed: emits active_status_changed(bool)            │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ↓
┌─────────────────────────────────────────────────────────────┐
│      MainWindow._on_usage_tracking_status_changed()          │
│  - Updates pdf_status_bar indicator                         │
│  - Updates transport_bar indicator                          │
└─────────────────────────────────────────────────────────────┘
                        │
                        ↓
┌─────────────────────────────────────────────────────────────┐
│              Visual Indicator Updated                        │
│  Active (●) = Green | Idle (○) = Gray                       │
└─────────────────────────────────────────────────────────────┘
```

## Status Update Triggers

The indicator updates in real-time when:

1. **Session starts/ends**
   - PDF loaded/closed
   - Video loaded/closed
   - Changes from Idle → Active or Active → Idle

2. **Window focus changes**
   - User switches to/from LinguaLoop
   - Changes from Active → Idle (lost focus) or Idle → Active (gained focus)

3. **User activity**
   - Word selection
   - Translation request
   - Mouse/keyboard interaction
   - Changes from Idle → Active (if session running & focused)

4. **Inactivity timer** (every 30 seconds)
   - Checks if >2 minutes since last activity
   - Changes from Active → Idle if inactive too long

## Example Scenarios

### Scenario 1: Normal Usage
```
1. User opens PDF → Indicator: ○ (idle, no activity yet)
2. User clicks window to focus → Indicator: ○ (focused, but no activity)
3. User selects first word → Indicator: ● (active! recording time)
4. User continues reading/selecting → Indicator: ● (stays active)
5. User switches to browser for 3 minutes → Indicator: ○ (lost focus)
6. User returns and selects word → Indicator: ● (active again)
```

### Scenario 2: Idle Timeout
```
1. User actively using app → Indicator: ● (active)
2. User gets coffee, leaves for 3 minutes → Indicator: ● → ○ (goes idle after 2 min)
3. Timer check at 30s intervals detects inactivity → Status changes
4. User returns and clicks → Indicator: ● (active again)
```

### Scenario 3: Background Window
```
1. User actively using app → Indicator: ● (active)
2. User Alt+Tabs to different app → Indicator: ○ (loses focus immediately)
3. User returns to LinguaLoop → Indicator: ○ (focused, but need activity)
4. User selects word → Indicator: ● (active again)
```

## Color Scheme

### PDF Mode (Light Background)
- **Active**: `#4CAF50` (Material Green 500)
- **Idle**: `Theme.TEXT_MUTED` (gray, follows theme)

### Video Mode (Dark Background)
- **Active**: `#4CAF50` (Material Green 500)
- **Idle**: `rgba(255, 255, 255, 0.4)` (translucent white)

## Testing Checklist

- [ ] Open PDF, verify indicator shows ○ (idle)
- [ ] Select a word, verify indicator changes to ● (active, green)
- [ ] Minimize window, verify indicator changes to ○ (idle)
- [ ] Restore window and select word, verify ● (active)
- [ ] Wait 2+ minutes without activity, verify → ○ (idle)
- [ ] Do any activity, verify → ● (active)
- [ ] Switch to video mode, verify indicator appears in transport bar
- [ ] Play video and select subtitle word, verify ● (active)
- [ ] Pause and wait 2+ minutes, verify → ○ (idle)
- [ ] Close file, verify indicator still present (shows idle)
- [ ] Check tooltips on hover for both states

## Design Rationale

### Why a Simple Dot Indicator?

1. **Non-intrusive**: Small, doesn't take up much space
2. **Clear**: Green = active is universally understood (traffic light metaphor)
3. **Real-time feedback**: Users can see immediately if their time is being tracked
4. **Discoverable**: Tooltip explains what it means
5. **Consistent**: Same indicator in both PDF and Video modes

### Why Not Show Time/Duration?

- Keeps the indicator simple and focused
- Actual time tracking is internal (can be viewed later via stats methods)
- Just needs to answer: "Is it tracking right now?" → Yes (●) or No (○)

### Why Green for Active?

- **Positive association**: Green = good, working, active
- **High contrast**: Visible against both light and dark backgrounds
- **Standard convention**: Activity indicators often use green (e.g., recording lights)

## Future Enhancements

Potential additions (not implemented):
- Click indicator to see today's accumulated time
- Show session duration in tooltip
- Animate pulse when recording
- Color changes based on session length (e.g., orange after 30 min, red after 60 min)
- Option to hide indicator in settings

## Verification

**Syntax Check**: ✅ All files compile successfully
```bash
python -m py_compile src/immersion_app/core/usage_time_tracker.py
python -m py_compile src/immersion_app/gui/widgets/pdf_status_bar.py
python -m py_compile src/immersion_app/gui/widgets/transport_bar.py
python -m py_compile src/immersion_app/gui/main_window.py
```

**Manual Testing**: Ready for user testing with real PDF/video workflows

---

**Implementation Complete**: The usage tracking indicator is now visible in both PDF and Video modes, providing real-time feedback about whether active time is being recorded.

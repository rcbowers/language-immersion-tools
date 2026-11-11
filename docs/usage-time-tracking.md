# Study-time tracking

How Language Immersion Tools decides what counts as study time. The user-facing summary is in the README. This page is for contributors.

## Pieces

| Piece | File | Role |
| --- | --- | --- |
| `UsageTimeTracker` | `src/immersion_app/core/usage_time_tracker.py` | State manager: file context, activity segments, session records, `active_status_changed` |
| `UserActivityMonitor` | `src/immersion_app/gui/activity_monitor.py` | App-wide event filter. Turns mouse presses/moves, wheel, key presses and touch into a throttled `activity` signal (at most every 5 s) |
| Main window wiring | `src/immersion_app/gui/main_window.py` | Connects the monitor, *visible* translations and app focus to the tracker |
| Controllers | `gui/controllers/pdf_controller.py`, `video_controller.py` | Report page/position changes, and playback as activity (once per 60 s while playing) |
| Indicator | `PDFStatusBar` / `TransportBar` | ● recording / ○ paused |

## Model

- **File context**: starts when a PDF or video is loaded (`on_document_loaded` / `on_video_loaded`) and ends when it's closed, another file is opened, or the app exits (`finalize_current_session`).
- **Segment**: a run of activity inside a file context. Each activity timestamp contributes a ±60 s window, and overlapping windows are merged. A segment closes after **120 s without activity** (`IDLE_TIMEOUT_SECONDS`) or when the file context ends. The next activity on the same file starts a new segment, so tracking always resumes after a break.
- **Session record**: each closed segment is appended to `user_data["usage_time"]["sessions"]` with `duration_seconds` (merged active time), start/end location, and pages or minutes advanced. A segment that crosses local midnight is split into one record per day, so "today" totals are correct.
- **Focus**: activity only counts while Language Immersion Tools is the active application (`QGuiApplication.applicationStateChanged`). Any Language Immersion Tools window counts, including dialogs and the translation popover. Losing focus marks the indicator idle immediately.
- **Indicator refresh**: on every activity and focus change, plus a 5 s timer for the idle transition.

## What counts as activity

Counts:
- mouse clicks, mouse movement, scrolling and key presses in any Language Immersion Tools window
- translations the user asked for (`translation_ready` with `visible=True`)
- page turns and jumps (PDF)
- video playback (once per minute while playing)

Does **not** count:
- background pre-translation of the page's words (`visible=False`)
- selection resets, page renders, loading a file
- anything while another application is focused

## Progress metadata

The start page/position of a segment is the first position reported after the file opens. So reopening a book at a saved page doesn't count the earlier pages as read. Navigation while a segment is closed (idle) is credited to the next segment.

## Tests

`tests/core/test_usage_time_tracker.py` (including idle/resume, restored-page and midnight-split regressions), `tests/test_usage_time_integration.py`, `tests/gui/test_activity_monitor.py`.

# Video Mode Implementation Plan for Sentence Miner GUI

## Context

The sentence miner GUI currently supports vocabulary mining from PDFs by allowing users to click on words, view translations, and create Anki flashcards. This plan adds a **video mode** that extends the same vocabulary mining workflow to videos with subtitles, enabling users to learn from authentic video content (movies, TV shows, YouTube videos, etc.).

**Why this change:**
- Videos with subtitles are one of the most effective immersion materials for language learning
- Users can mine vocabulary from content they're already watching for entertainment
- Automatic subtitle generation (via Whisper AI) makes it accessible even without pre-existing subtitles
- Maintains the same proven workflow (click word → translate → create flashcard) users already know from PDF mode

**Intended outcome:**
- Users can select between PDF mode and Video mode at startup
- Video mode provides identical vocabulary mining features (click words, translate, add to Anki/queue)
- Seamless subtitle generation when .srt files aren't available
- All existing PDF functionality remains unchanged and working

## Architecture Overview

### Mode Selection Pattern

Add a startup dialog (`ModeSelectorDialog`) that appears before the main window:
- Two buttons: "PDF Mode" and "Video Mode"
- Optional "Remember my choice" checkbox (saves to user_data.json)
- Optional button: "Load Last Session" (loads mode + file from last session)
- Return selected mode: "pdf" or "video"

### Component Structure

Refactor codebase into shared base class + mode-specific windows:

```
AbstractSentenceMinerWindow (base class)
├── Shared components:
│   ├── Right panel (word/context/translation display + action buttons)
│   ├── Translation system (async googletrans, caching, TranslateTask)
│   ├── Anki integration (add_anki_card, queue management)
│   ├── User data persistence
│   └── UI scaling system
│
├── PdfSentenceMinerWindow (refactored existing)
│   ├── PDF viewer (PyMuPDF + ClickablePdfLabel)
│   └── PDF-specific toolbar
│
└── VideoSentenceMinerWindow (new)
    ├── Video player (QMediaPlayer + QVideoWidget)
    ├── Subtitle overlay (clickable, synchronized)
    ├── SRT parser and word detection
    └── Video-specific toolbar
```

### User Preferences (from clarification)

1. **Subtitle display**: Overlay on video (traditional subtitle style with semi-transparent background)
2. **Word selection**: Single words only in V1 (no multi-word Shift+Click for now)
3. **Missing subtitles**: Automatically prompt to generate subtitles when .srt file not found

## Implementation Plan

### Phase 1: Refactoring & Foundation

**Goal**: Extract shared functionality into reusable base class

**Tasks**:
1. Create `apps/sentence_miner/base_miner_window.py` with `AbstractSentenceMinerWindow` class
2. Extract shared methods from current `PdfSentenceMinerWindow`:
   - `_build_right_panel()` - Selection display + action buttons (lines 256-304)
   - `_request_translation()` - Async translation system (lines 587-619)
   - `_add_now()` - Immediate Anki card creation (lines 685-700)
   - `_add_to_queue()` - Queue entry writing (lines 702-712)
   - `_process_queue()` - Batch queue processing (lines 732-784)
   - User data loading/saving (lines 786-866)
   - Translation cache and `TranslateTask` (lines 65-104)
3. Define abstract methods that subclasses must implement:
   - `_build_viewer_panel()` - Left panel (PDF viewer or video player)
   - `_open_file_dialog()` - File selection dialog
   - `_clear_viewer_state()` - Reset mode-specific state
4. Create `apps/sentence_miner/pdf_miner_window.py` - move `PdfSentenceMinerWindow` to this file and inherit from base class
5. Update imports in `sentence_miner_gui.py`
6. **Verify**: Run PDF mode and confirm all functionality still works

**Files to create**:
- `apps/sentence_miner/base_miner_window.py` (new, ~400 lines)
- `apps/sentence_miner/pdf_miner_window.py` (refactored from existing code, ~500 lines)

**Files to modify**:
- `apps/sentence_miner/sentence_miner_gui.py` (update imports, remove moved code)

### Phase 2: SRT Subtitle Infrastructure

**Goal**: Build subtitle parsing and synchronization system

**Tasks**:
1. Create `apps/sentence_miner/subtitle_parser.py` with:
   - `SRTSubtitle` class: Represents single subtitle with index, start_ms, end_ms, text, and word list
   - `SRTParser` class: Parses .srt files into list of `SRTSubtitle` objects
   - Timestamp parsing: Convert "HH:MM:SS,mmm" format to milliseconds
   - `get_subtitle_at_time(time_ms)` method using binary search for efficiency
   - Word extraction: Split subtitle text into clickable words with character offsets
2. Handle SRT format edge cases:
   - Missing indexes
   - Malformed timestamps
   - Multi-line subtitle text
   - UTF-8 encoding
3. Write unit tests with sample .srt files from `immersion materials/` folder

**Files to create**:
- `apps/sentence_miner/subtitle_parser.py` (new, ~150 lines)

**Existing utilities to reference**:
- Word cleaning logic from `PdfSentenceMinerWindow._clean_word()` (lines 541-551) - reuse for subtitle words

### Phase 3: Video Player Core

**Goal**: Implement basic video playback without subtitles

**Tasks**:
1. Create `apps/sentence_miner/video_miner_window.py` with `VideoSentenceMinerWindow` class
2. Implement video player components:
   - `QMediaPlayer` for playback engine
   - `QVideoWidget` for video display
   - `QAudioOutput` for audio (PySide6.QtMultimedia)
3. Build video-specific toolbar:
   - "Open Video" (Ctrl+O) - supports .mp4, .mkv, .avi, .mov, .webm
   - "Load Subtitles" (Ctrl+L) - load .srt file
   - "Generate Subtitles" - trigger Whisper generation
   - Play/Pause (Space key)
   - Skip backward/forward 5s (Left/Right arrows)
   - Playback speed selector (0.5x, 0.75x, 1.0x, 1.25x, 1.5x)
   - UI scaling (A-, A+) - inherited from base
   - Anki controls (Start Anki, Check Anki) - inherited from base
4. Implement playback controls:
   - Timeline slider (QSlider) with current position
   - Timestamp display (current / total duration)
   - Play/pause toggle button
5. Handle video file loading:
   - Set media source: `QMediaPlayer.setSource(QUrl.fromLocalFile(path))`
   - Auto-detect matching .srt file (same name as video)
   - If no .srt found, show subtitle generation dialog (per user preference)

**Files to create**:
- `apps/sentence_miner/video_miner_window.py` (new, ~600 lines initially)

**Qt imports needed**:
```python
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtCore import QUrl
```

### Phase 4: Clickable Subtitle Overlay

**Goal**: Display synchronized subtitles with click detection

**Tasks**:
1. Create `apps/sentence_miner/subtitle_widget.py` with `ClickableSubtitleLabel` class
2. Implement subtitle overlay widget:
   - Inherits from `QLabel`
   - Semi-transparent black background (`rgba(0, 0, 0, 150)`)
   - White text, large font (24px), bold, with padding
   - Positioned at bottom-center of video
   - `mousePressEvent()` to detect clicks on words
3. Implement word click detection:
   - Use `QFontMetrics` to calculate text layout
   - Calculate cumulative width of words to determine which word was clicked
   - Emit signal with clicked word: `clicked = Signal(str, object)` (word, modifiers)
4. Integrate with video player:
   - Overlay subtitle label on top of `QVideoWidget` using layout stacking
   - Connect to `QMediaPlayer.positionChanged` signal (triggers every ~100ms)
   - Update displayed subtitle by calling `SRTParser.get_subtitle_at_time(position_ms)`
   - Show/hide subtitle based on current timestamp
5. Implement visual word highlighting:
   - Use HTML formatting in QLabel: `<span style='background-color: yellow;'>word</span>`
   - Highlight selected word after click

**Files to create**:
- `apps/sentence_miner/subtitle_widget.py` (new, ~120 lines)

**Pattern to follow**:
- Similar to `ClickablePdfLabel` (lines 56-62), but for subtitle text instead of PDF coordinates

### Phase 5: Word Selection & Translation

**Goal**: Connect subtitle clicks to translation and card creation

**Tasks**:
1. In `VideoSentenceMinerWindow`, implement `_on_subtitle_click(word, modifiers)` handler:
   - Clean the word using inherited `_clean_word()` method (remove punctuation)
   - Set `self.selected_word = clean_word`
   - Set `self.selected_sentence = current_subtitle.text` (full subtitle is the context)
   - Call `_update_selection_panel()` (inherited from base class)
   - Call `_request_translation(word)` (inherited from base class)
   - Highlight word in subtitle overlay
2. Reuse existing translation infrastructure:
   - `TranslateTask` (lines 70-104) - async translation with googletrans
   - Translation cache - avoid re-translating same words
   - Success/failure signal handlers (lines 603-619)
3. Reuse existing action buttons (already built in base class right panel):
   - "Add Now" button → `_add_now()` creates Anki card immediately
   - "Add to Queue" → `_add_to_queue()` writes to words_to_process.txt
   - "Process Queue" → `_process_queue()` batch processes queue
4. **Note**: Single-word selection only (no Shift+Click multi-word in V1 per user preference)

**Files to modify**:
- `apps/sentence_miner/video_miner_window.py` (add click handler, ~50 lines)

**Existing code to reuse**:
- `spanish_sentence_miner.py::add_anki_card()` (lines 109-126) - creates flashcard
- `spanish_sentence_miner.py::test_anki_connection()` (lines 29-39) - checks Anki status
- Translation system from base class (all async handling already implemented)

### Phase 6: Automatic Subtitle Generation

**Goal**: Integrate Whisper AI for automatic subtitle generation

**Tasks**:
1. Create `apps/sentence_miner/subtitle_generator.py` with reusable Whisper wrapper:
   - Extract core logic from `apps/subtitle generation/youtube_subtitle_generator.py`
   - Function: `generate_srt_from_video(video_path, output_path, model_size, language)`
   - Support both CPU and GPU (detect with `torch.cuda.is_available()`)
   - Return generated .srt file path
2. Create `SubtitleGeneratorDialog` (in video_miner_window.py):
   - Model selection dropdown: tiny, base, small, medium (default: base for CPU, medium for GPU)
   - Language input (default: "es" for Spanish)
   - Progress bar (indeterminate - Whisper doesn't expose precise progress)
   - Status label showing current step: "Extracting audio...", "Transcribing...", "Saving subtitles..."
   - Cancel button
3. Implement `SubtitleGeneratorWorker` (QRunnable):
   - Runs in background thread (use `QThreadPool.globalInstance()`)
   - Emits signals: `progress(message)`, `finished(srt_path)`, `error(error_message)`
   - Executes Whisper transcription
   - Saves .srt file with same name as video file
4. Wire up to video loading workflow:
   - When user opens video, check for matching .srt file (e.g., "video.mp4" → look for "video.srt")
   - If not found, show `SubtitleGeneratorDialog` immediately (per user preference)
   - If user confirms, run generation
   - On completion, load generated .srt automatically
   - On error, show error dialog and allow video to load without subtitles

**Files to create**:
- `apps/sentence_miner/subtitle_generator.py` (new, ~100 lines)

**Files to modify**:
- `apps/sentence_miner/video_miner_window.py` (add dialog classes, ~150 lines)

**Existing code to adapt**:
- `apps/subtitle generation/youtube_subtitle_generator.py::generate_subtitles()` (lines 71-90)
- `apps/subtitle generation/youtube_subtitle_generator_gpu.py` (GPU detection logic)

**Dependencies** (already in requirements.txt):
- `openai-whisper` - Whisper AI model
- `ffmpeg-python` - Audio extraction
- `torch` - GPU acceleration

### Phase 7: Mode Selection Dialog

**Goal**: Add startup mode selector

**Tasks**:
1. Create `ModeSelectorDialog` class in `sentence_miner_gui.py`:
   - Simple QDialog with two large buttons: "PDF Mode" and "Video Mode"
   - Optional checkbox: "Remember my choice" (saves to user_data.json)
   - Optional button: "Load Last Session" (loads mode + file from last session)
   - Return selected mode: "pdf" or "video"
2. Update `main()` function:
   - Check user_data.json for saved preference (`preferences.preferred_mode`)
   - If preference exists, skip dialog and launch directly
   - Otherwise, show `ModeSelectorDialog`
   - Based on selection, instantiate appropriate window class
3. Update user_data.json schema:
   - Add `mode` field to track last used mode
   - Add `preferences.preferred_mode` for "Remember choice"
   - Add video-specific session data: `last_session.video_path`, `video_position_ms`, `srt_path`

**Files to modify**:
- `apps/sentence_miner/sentence_miner_gui.py` (add dialog, update main(), ~100 lines)
- `sentence_miner_user_data.json` (schema expansion)

**Example updated main()**:
```python
def main():
    app = QApplication(sys.argv)

    # Check for saved mode preference
    user_data = load_user_data()  # helper function
    preferred_mode = user_data.get("preferences", {}).get("preferred_mode")

    if not preferred_mode:
        selector = ModeSelectorDialog()
        if selector.exec() != QDialog.Accepted:
            sys.exit(0)
        mode = selector.get_selected_mode()
        if selector.remember_choice():
            save_mode_preference(mode)
    else:
        mode = preferred_mode

    # Launch appropriate window
    if mode == "pdf":
        from pdf_miner_window import PdfSentenceMinerWindow
        window = PdfSentenceMinerWindow()
    else:
        from video_miner_window import VideoSentenceMinerWindow
        window = VideoSentenceMinerWindow()

    window.show()
    sys.exit(app.exec())
```

### Phase 8: User Data Persistence

**Goal**: Save and restore video mode sessions

**Tasks**:
1. Extend user_data.json structure:
```json
{
  "version": 1,
  "mode": "video",
  "preferences": {
    "preferred_mode": null,
    "video_playback_speed": 1.0
  },
  "last_session": {
    "pdf_path": "...",
    "page_index": 0,
    "video_path": "...",
    "video_position_ms": 0,
    "srt_path": "..."
  },
  "analytics": { ... }
}
```
2. In `VideoSentenceMinerWindow`, override session restoration:
   - Load last video path and .srt path
   - Restore playback position
   - Resume from where user left off
3. Save state on video position changes and window close:
   - Save every 5 seconds during playback (use QTimer)
   - Save on `closeEvent()`
   - Save current video path, position, and subtitle path

**Files to modify**:
- `apps/sentence_miner/base_miner_window.py` (update user_data structure)
- `apps/sentence_miner/video_miner_window.py` (implement restoration, ~30 lines)

### Phase 9: Testing & Polish

**Goal**: Verify all functionality and polish UX

**Tasks**:
1. **Functional testing**:
   - Load video with existing .srt → verify subtitle display and synchronization
   - Load video without .srt → verify automatic generation prompt
   - Click words in subtitles → verify translation appears
   - Add cards to Anki (both "Add Now" and "Add to Queue")
   - Process queue → verify batch processing works
   - Test with various video formats: .mp4, .mkv, .avi, .mov
   - Test with long videos (>1 hour) - verify performance
2. **Session persistence**:
   - Open video, watch partway, close app → reopen and verify it resumes
   - Switch between PDF and Video modes → verify mode selection works
   - Test "Remember choice" preference
3. **Subtitle generation**:
   - Generate subtitles with different Whisper models (tiny, base, medium)
   - Test GPU detection (if GPU available)
   - Verify progress dialog shows status
   - Test cancel during generation
4. **Edge cases**:
   - Malformed .srt files
   - Very long subtitles (multi-line)
   - Special characters in video filenames
   - Missing Anki connection
5. **Polish**:
   - Update window title for video mode: "Spanish Video Sentence Miner"
   - Ensure keyboard shortcuts work (Space, Left/Right, Ctrl+O, Ctrl+Return, etc.)
   - Verify UI scaling works in video mode
   - Test on different screen resolutions

## Critical Files

### Files to Create (New)
1. **apps/sentence_miner/base_miner_window.py** - Abstract base class with shared functionality
2. **apps/sentence_miner/pdf_miner_window.py** - Refactored PDF mode (moved from main file)
3. **apps/sentence_miner/video_miner_window.py** - New video mode implementation
4. **apps/sentence_miner/subtitle_parser.py** - SRT parsing and synchronization
5. **apps/sentence_miner/subtitle_widget.py** - Clickable subtitle overlay widget
6. **apps/sentence_miner/subtitle_generator.py** - Whisper integration wrapper

### Files to Modify (Existing)
1. **apps/sentence_miner/sentence_miner_gui.py** - Add mode selector, update main() entry point
2. **apps/sentence_miner/spanish_sentence_miner.py** - No changes needed (reused as-is)
3. **sentence_miner_user_data.json** - Expand schema for video mode persistence
4. **requirements.txt** - Verify all dependencies present (should be fine - PySide6 >= 6.7.0 includes QtMultimedia)

### Key Existing Code to Reuse
1. **Translation system** (lines 65-104, 587-619):
   - `TranslateTask` class - async googletrans
   - Translation cache
   - Request ID tracking
2. **Right panel** (lines 256-304):
   - Selection display (word, context, translation)
   - Action buttons (Add Now, Add to Queue, Process Queue)
3. **Anki integration** (spanish_sentence_miner.py):
   - `add_anki_card()` - creates flashcard with highlighted word
   - `test_anki_connection()` - checks if Anki is running
   - Queue file management (`words_to_process.txt`)
4. **Word cleaning** (lines 541-551):
   - `_clean_word()` - removes punctuation from selected words
5. **Subtitle generation** (apps/subtitle generation/):
   - Whisper model loading and transcription
   - Audio extraction with ffmpeg
   - SRT format generation

## Verification Plan

### End-to-End Test Scenarios

**Scenario 1: New video with subtitle generation**
1. Launch app → select "Video Mode"
2. Open video file (e.g., from `immersion materials/`) → no .srt file exists
3. Subtitle generation dialog appears → select "base" model → confirm
4. Wait for generation (progress dialog shows status)
5. Video loads with generated subtitles displayed
6. Click on a word in subtitle → translation appears in right panel
7. Click "Add Now" → verify Anki card created (check Anki deck)
8. Close app → reopen → verify video resumes at last position

**Scenario 2: Existing video with .srt file**
1. Launch app (should remember "Video Mode" if checkbox was checked)
2. Open video that already has .srt file → subtitles load automatically
3. Play video → verify subtitles sync correctly
4. Click word → add to queue (Ctrl+Shift+Return)
5. Click different word → add to queue
6. Click "Process Queue" → verify both cards created in Anki

**Scenario 3: Switch between modes**
1. Launch app → select "PDF Mode"
2. Open PDF → mine a word → create card
3. Close app → launch again → select "Video Mode"
4. Open video → mine word → create card
5. Verify both modes work independently
6. Check user_data.json → verify mode tracking

**Scenario 4: Queue processing from video mode**
1. Open video with subtitles
2. Add 5 words to queue (don't use "Add Now")
3. Close video, close app
4. Reopen in PDF mode → open PDF
5. Click "Process Queue" → verify all 5 cards created
6. Confirms queue is shared between modes

### Success Criteria

✅ Mode selector appears at startup and routes to correct window
✅ Video plays with synchronized subtitles overlaid
✅ Clicking subtitle words triggers translation and displays in right panel
✅ "Add Now" creates Anki card immediately (with sentence + word + translation)
✅ "Add to Queue" writes to queue file
✅ "Process Queue" batch-creates cards from queue
✅ Subtitle generation works (Whisper creates .srt from video)
✅ Session restoration works (video + position + subtitles)
✅ PDF mode still works identically to before
✅ Queue is shared between PDF and Video modes
✅ User data persists correctly for both modes
✅ All keyboard shortcuts work (Space, arrows, Ctrl+Return, etc.)

## Future Enhancements (Post-V1)

- Multi-word phrase selection with Shift+Click
- Subtitle editing (fix Whisper errors inline)
- Auto-pause when clicking word
- Loop current subtitle segment for listening practice
- Dual subtitles (target language + native language)
- YouTube URL support (download + generate subtitles in one step)
- Vocabulary frequency analysis for loaded video
- Export session statistics (words learned per video)

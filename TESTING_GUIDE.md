# Quick Testing Guide

## Pre-Flight Check

Before running, make sure you have:
- [ ] PySide6 installed: `pip install PySide6`
- [ ] fitz (PyMuPDF) installed: `pip install PyMuPDF`
- [ ] A PDF file for testing
- [ ] A video file with .srt subtitles (optional)
- [ ] Anki running with AnkiConnect plugin (optional)

## Start the App

```bash
cd <repo>
python -m immersion_app.app
```

## Visual Verification Checklist

### Welcome Page
- [ ] Background is light gray (#fafafa)
- [ ] Title: "Open a PDF or video to start" (26px, semibold)
- [ ] Subtitle: "Click any word..." (15px, soft gray)
- [ ] Two buttons: "Open Source" (blue accent) and "View Queue" (outlined)
- [ ] Keyboard hint at bottom: "Ctrl+O to open · Ctrl+1/2 to switch modes"
- [ ] Command bar at top showing "No document loaded"

### Command Bar (Top, 42px)
- [ ] Mode pills: PDF (active) and Video
- [ ] Title shows "No document loaded" initially
- [ ] Stats chip: "✨ 0 today · X total" (X = your vocabulary count)
- [ ] Search field with "Search ⌘K" placeholder
- [ ] Settings gear icon (⚙)

## PDF Mode Testing

### 1. Open a PDF
**Action:** Click "Open Source" or press `Ctrl+O`, select a PDF

**Verify:**
- [ ] PDF displays in centered 600px column
- [ ] Background is light gray, reading area is white
- [ ] Command bar updates with PDF filename and page count
- [ ] Chapter rail appears on right (48px width) if PDF has outline
- [ ] Status bar at bottom shows: "□ New  □ Learning  □ Selected  Click any word..."
- [ ] All words have subtle background colors (darker = new, lighter = seen)

### 2. Click a Word
**Action:** Click any word in the PDF

**Verify:**
- [ ] Translation popover appears below (or above) the word
- [ ] Popover width is 320px
- [ ] Popover has drop shadow
- [ ] Headword appears at top (19px, semibold)
- [ ] Translation text below headword
- [ ] "IN CONTEXT" section with gray background
- [ ] Source sentence in context section
- [ ] Two buttons: "+ Add to Anki ⏎" (blue) and "✎ Edit" (outlined)
- [ ] Close button (✕) in top right
- [ ] Selected word has bright blue highlight (#5b6cff)

### 3. Add to Anki
**Action:** Press `Enter` or click "Add to Anki" button

**Verify:**
- [ ] Word is added to Anki (if Anki is running)
- [ ] Word highlight changes from dark blue to light blue (seen state)
- [ ] Stats chip updates: total count increases
- [ ] Popover closes

### 4. Navigation
**Action:** Use keyboard and chapter rail

**Verify:**
- [ ] `→` goes to next page
- [ ] `←` goes to previous page
- [ ] `Ctrl++` zooms in
- [ ] `Ctrl+-` zooms out
- [ ] Click chapter dot in rail jumps to that chapter
- [ ] Current chapter dot is blue, others are gray
- [ ] Page counter at bottom of rail updates (e.g., "12/458")

### 5. Popover Edge Cases
**Action:** Test popover positioning

**Verify:**
- [ ] Click word near top of screen → popover appears below
- [ ] Click word near bottom → popover appears above
- [ ] Press `Escape` → popover closes
- [ ] Click another word → old popover closes, new one opens
- [ ] Click outside popover → popover closes

## Video Mode Testing

### 1. Switch to Video Mode
**Action:** Press `Ctrl+2` or click "Video" pill in command bar

**Verify:**
- [ ] Mode pill switches (Video is now blue, PDF is gray)
- [ ] Welcome page or last video shown
- [ ] Command bar updates

### 2. Open a Video
**Action:** Press `Ctrl+O`, select video file

**Verify:**
- [ ] Video fills entire screen (full-bleed)
- [ ] Transport bar at bottom (38px, dark background)
- [ ] Subtitle area above transport bar (80px)
- [ ] Command bar shows video filename
- [ ] If .srt file exists with same name, subtitles load automatically

### 3. Transport Bar Controls
**Action:** Test each control

**Verify:**
- [ ] Play button (▶) is 32px circle with blue background
- [ ] Click play → button changes to pause (⏸)
- [ ] Replay button (↻) appears next to play
- [ ] Time display shows "00:00 / MM:SS"
- [ ] Scrubber moves as video plays
- [ ] Dragging scrubber seeks video
- [ ] Speed dropdown shows: 0.5x, 0.75x, 1x, 1.25x, 1.5x, 2x
- [ ] Changing speed affects playback
- [ ] CC button toggles (currently just visual)
- [ ] Volume slider adjusts audio

### 4. Subtitle Word Highlighting
**Action:** Watch video with subtitles

**Verify:**
- [ ] All words in subtitle have background colors
- [ ] New words are darker blue
- [ ] Previously added words are lighter blue
- [ ] Click word → popover appears
- [ ] Selected word has bright blue background + white text
- [ ] Video pauses when word is clicked (if auto-pause enabled)

### 5. Replay Function
**Action:** Click replay button (↻) while subtitle is showing

**Verify:**
- [ ] Video jumps to start of current subtitle
- [ ] Subtitle stays visible

## Command Bar Testing

### 1. Mode Switching
**Action:** Switch between modes multiple times

**Verify:**
- [ ] `Ctrl+1` switches to PDF mode
- [ ] `Ctrl+2` switches to Video mode
- [ ] Mode pills update correctly
- [ ] Active mode has blue background
- [ ] Previously loaded document reappears when switching back

### 2. Stats Chip
**Action:** Add multiple words to Anki

**Verify:**
- [ ] Total count increases after each add
- [ ] Stats update in real-time
- [ ] Count persists between sessions

### 3. Settings Menu
**Action:** Click settings gear icon (⚙)

**Verify:**
- [ ] Menu appears below settings button
- [ ] Options include:
  - Toggle translation mode
  - Learning language submenu
  - Native language submenu
  - Start Anki
  - Check Anki
  - Generate subtitles
- [ ] Clicking option executes action
- [ ] Menu closes after selection

## Theme Consistency Check

### Colors
- [ ] Backgrounds: Light gray (#fafafa) for pages, white (#ffffff) for surfaces
- [ ] Text: Dark (#18181b) for primary, gray (#52525b) for secondary
- [ ] Accent: Electric blue (#5b6cff) for buttons, highlights, active states
- [ ] Borders: Very subtle (rgba(0,0,0,0.07))

### Typography
- [ ] All text uses Inter font (or Segoe UI fallback)
- [ ] Button text: 13px, medium weight
- [ ] Body text: 14.5px
- [ ] Headings: 19px, semibold
- [ ] Time codes: Monospace font

### Spacing
- [ ] Command bar: 42px height
- [ ] Transport bar: 38px height
- [ ] Status bar: 32px height
- [ ] Chapter rail: 48px width
- [ ] Reading column: 600px width
- [ ] Popover: 320px width

## Keyboard Shortcuts Verification

- [ ] `Ctrl+O` - Open source
- [ ] `Ctrl+L` - Load subtitles
- [ ] `Ctrl+1` - PDF mode
- [ ] `Ctrl+2` - Video mode
- [ ] `Ctrl+Enter` - Add to Anki
- [ ] `Ctrl+Shift+Enter` - Add to queue
- [ ] `Space` - Play/pause video
- [ ] `←` - Previous PDF page
- [ ] `→` - Next PDF page
- [ ] `Ctrl++` - Zoom in PDF
- [ ] `Ctrl+-` - Zoom out PDF
- [ ] `Escape` - Close popover

## Dialog Testing

### Queue Dialog
**Action:** Press `Ctrl+Shift+Enter` to add word to queue, then open queue

**Verify:**
- [ ] Dialog has modern styling
- [ ] Background is light gray
- [ ] List has rounded corners and subtle border
- [ ] Buttons use theme colors (primary/secondary)
- [ ] Dialog shows queue count

### Subtitle Generator Dialog
**Action:** Open video, go to settings → Generate subtitles

**Verify:**
- [ ] Dialog has modern styling
- [ ] Input fields use theme styling
- [ ] Buttons use theme colors
- [ ] Progress bar appears when generating

## Performance Check

- [ ] Opening 100+ page PDF is smooth
- [ ] Scrolling PDF is responsive
- [ ] Word highlighting doesn't lag
- [ ] Video playback is smooth
- [ ] Switching modes is instant
- [ ] Popover appears immediately on click

## Issues to Report

If you find any issues, note:
1. **What you did** (steps to reproduce)
2. **What happened** (actual behavior)
3. **What you expected** (expected behavior)
4. **Screenshot** (if visual issue)
5. **Console output** (if crash or error)

## Success Criteria

✅ All visual elements match the mockups
✅ All functionality works as described
✅ No crashes or errors
✅ Performance is acceptable
✅ Keyboard shortcuts all work
✅ Theme is consistent throughout

---

**Total test time:** ~15-20 minutes for comprehensive check
**Required:** ~5 minutes for basic verification

- These terminal prints "[INFO] Batch translation completed: 50 words on page 90: ". Currently it prints it broken up like you see below. we need to combine so it's one print that lists all the words.
[INFO] Batch translation completed: 50 words on page 90: echar, puerta, fugaz, mirada, comprobar
[INFO] Batch translation completed: 1 words on page 90: dé
[INFO] Batch translation completed: 50 words on page 90: 90, vez, te, voy, a
[INFO] Batch translation completed: 50 words on page 90: echar, puerta, fugaz, mirada, comprobar
[INFO] Batch translation completed: 50 words on page 90: pudo, evitar, sentirse, agradecido, Era
[INFO] Batch translation completed: 50 words on page 90: Aquí, tiene, solución, Embrujorrápid, es
[INFO] Batch translation completed: 50 words on page 90: pudo, evitar, sentirse, agradecido, Era
[INFO] Batch translation completed: 50 words on page 90: 90, vez, te, voy, a
[INFO] Batch translation completed: 50 words on page 90: Aquí, tiene, solución, Embrujorrápid, es
[INFO] Batch translation completed: 50 words on page 90: echar, puerta, fugaz, mirada, comprobar
[INFO] Batch translation completed: 50 words on page 90: 90, vez, te, voy, a
[INFO] Batch translation completed: 50 words on page 90: 90, vez, te, voy, a
[INFO] Batch translation completed: 50 words on page 90: Aquí, tiene, solución, Embrujorrápid, es
[INFO] Batch translation completed: 50 words on page 90: pudo, evitar, sentirse, agradecido, Era
[INFO] Batch translation completed: 50 words on page 90: echar, puerta, fugaz, mirada, comprobar
[INFO] Batch translation completed: 50 words on page 90: pudo, evitar, sentirse, agradecido, Era
[INFO] Batch translation completed: 50 words on page 90: Aquí, tiene, solución, Embrujorrápid, es

- if a word is in the seen list (already in anki), opening the translation bubble should also show the front content and creation date of the anki card it is associated with

- when we add a card, the toast that appears doesnt have enough vertical height (needs ~25% more)

## Usage Time Tracking (IMPLEMENTED - 2026-05-12)

The app now tracks active usage time to help users monitor their immersion study habits.

### How it works:
1. **Automatic tracking**: Tracks time when you have a file open and the app window is focused
2. **Activity-based**: Only counts time when you're actively engaging (selecting words, translating, clicking, typing)
3. **2-minute window**: Each activity creates a 2-minute window of "active time" (±1 minute around the activity)
4. **Smart merging**: Overlapping activity windows are merged for accurate duration calculation
5. **Persistent storage**: Sessions are saved to `user_data.json` with metadata (file path, timestamps, duration)

### Data structure (in user_data.json):
```json
{
  "usage_time": {
    "sessions": [
      {
        "file_path": "c:\\documents\\book.pdf",
        "file_type": "pdf",
        "start_time": "2026-05-12T14:30:00.000000",
        "end_time": "2026-05-12T14:45:30.000000",
        "duration_seconds": 930,
        "metadata": {
          "source_name": "book.pdf",
          "start_location": "Page 5",
          "end_location": "Page 8"
        }
      }
    ],
    "total_seconds": 125430,
    "last_activity_timestamp": "2026-05-12T14:45:30.000000"
  }
}
```

### Query methods available:
- `get_total_usage_seconds()`: Total usage time across all sessions
- `get_today_usage_seconds()`: Usage time for today
- `get_file_usage_seconds(file_path)`: Usage time for a specific file

### Future enhancements (not yet implemented):
- Display usage stats in UI (command bar or settings panel)
- Daily/weekly usage charts
- Per-file usage breakdown
- Export usage data to CSV
- Usage goals and streaks
- Periodic auto-save for crash recovery
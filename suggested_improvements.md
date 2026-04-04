# Immersion-Learner Feature Roadmap (Full Product Vision)

## Summary
Evolve your current toolkit (subtitle generation + PDF click-mining + Anki pipeline) into an end-to-end immersion study system that supports: context-rich mining, listening-first workflows, smarter card quality, and progress loops.
This roadmap is sequenced by impact and dependency, with explicit scope so implementation is decision-complete.

## Current Baseline (from repo)
- Working unified PDF/video click-miner in `src/immersion_app/gui/main_window.py`.
- AnkiConnect card creation pipeline in `src/immersion_app/core/anki.py`.
- Subtitle generation CLI and integration support in `src/immersion_app/cli/subtitles.py` and `src/immersion_app/integrations/subtitle_generation.py`.
- Corpus-level analysis in `src/immersion_app/cli/analyze.py`.
- Structured queue and processed logs in `data/`.

## Product Direction
Build around one core loop:
1. Consume native content.
2. Capture unknown language quickly.
3. Auto-enrich into high-quality study items.
4. Review and track weak points.
5. Return to immersion with better comprehension.

## Feature Set (What to Add)

### 1. Context-Aware Card Enrichment (highest immediate learning value)
Purpose: make each mined item more memorable and less ambiguous.

Additions:
- Card fields expanded beyond current `Front`/`Back`:
  - `FrontSentence` (target sentence with highlight)
  - `TargetExpression` (word/phrase)
  - `BaseTranslation`
  - `SourceTitle`
  - `SourceType` (`pdf`, `srt`, `youtube`)
  - `PageOrTimestamp`
  - `ContextBefore`, `ContextAfter` (neighbor sentence/line)
- Auto tags:
  - `source:<name>`, `type:pdf|srt`, `difficulty:<level>`, `pos:<tag>` (if POS enabled later).

Why useful:
- Reduces "orphan vocab" cards.
- Improves retention through source memory and context anchors.

Implementation notes:
- Keep backward compatibility with existing `Basic` model.
- Add optional "advanced model mapping" config so users can choose:
  - fallback to `Basic`, or
  - write into richer custom note type.

### 2. Audio-Linked Mining Workflow (critical for immersion)
Purpose: connect reading clicks to listening, not just translation.

Additions:
- SRT ingestion panel in GUI:
  - open `.srt`, browse lines, click token/phrase similarly to PDF.
- For subtitle-derived cards:
  - store start/end timestamp.
  - optional export of short audio clip per mined item (e.g., +/-1.5s context).
- Card field support for `[sound:...]` attachment (Anki media).

Why useful:
- Listening recall is core for immersion.
- High-value for colloquial expressions and pronunciation memory.

Implementation notes:
- Reuse existing subtitle generator outputs.
- Add media export worker pipeline with ffmpeg bindings already in project deps.

### 3. Smart Selection & Linguistic Helpers
Purpose: reduce noise and improve expression-level mining.

Additions:
- Expression expansion suggestions after click:
  - clicked word only
  - full collocation
  - full clause
- Lemma normalization and POS hints (optional spaCy pass).
- "Known word suppression":
  - hide/de-emphasize already-known or already-mined terms.
- Duplicate detector before queue/add:
  - check against local history + Anki duplicate probe.

Why useful:
- Helps learners mine useful chunks, not isolated function words.
- Avoids deck bloat and repetitive cards.

Implementation notes:
- Start with lightweight regex/chunk heuristics.
- Add spaCy optional mode for better linguistic precision.

### 4. Translation Quality Controls
Purpose: avoid blind trust in single MT output.

Additions:
- Show alternatives:
  - primary translation
  - literal gloss
  - editable final answer before save.
- Confidence cues:
  - flag low-confidence or very short ambiguous translations.
- Retry/caching layer:
  - persistent translation cache (sqlite/jsonl) with TTL.

Why useful:
- Better card quality with less manual correction later.
- Faster repeated mining sessions.

Implementation notes:
- Keep current engine as default.
- Add translation backend interface so engine swap is easy later.

### 5. Learning Pipeline Dashboard
Purpose: make immersion measurable and adaptive.

Additions:
- Progress panel:
  - mined today/week
  - queue depth
  - processed success/failure rates
  - source coverage (what content mined from).
- Frequency + knownness merge:
  - combine corpus frequency with mined status.
- "Next best targets" list:
  - high-frequency unknowns from your current content set.

Why useful:
- Keeps immersion strategic instead of random.
- Helps prioritize high ROI vocabulary.

Implementation notes:
- Build from current `processed_words.txt` + analyzer outputs.
- Move to structured storage (sqlite) for robust stats.

### 6. Review Feedback Loop from Anki
Purpose: tie card outcomes back into mining choices.

Additions:
- Pull review stats via AnkiConnect:
  - lapses, ease, mature/young, failed cards.
- Auto-prioritize weak items:
  - suggest remine of difficult words in fresh contexts.
- "Suspended/leech aware" tagging in miner.

Why useful:
- Closes the loop between immersion input and review output.
- Targets weaknesses with context-rich re-exposure.

### 7. Source Library & Session Management
Purpose: scale from ad-hoc file usage to repeatable study sessions.

Additions:
- Library index:
  - PDFs, SRTs, videos, metadata.
- Session files:
  - remember last page, zoom, filters, active source.
- Source-specific goals:
  - "mine 10 unknowns from chapter 3."

Why useful:
- Practical for long books/series.
- Reduces setup friction per study session.

### 8. Safety/Robustness Features
Purpose: make tool reliable as usage volume grows.

Additions:
- Explicit save location display and "Open queue file" button.
- Atomic queue writes + backups.
- Structured error panel (not just status bar).
- Health checks:
  - Anki connection
  - translation service status
  - media export readiness.

Why useful:
- Prevents silent failures and data-loss confusion.
- Improves trust for daily use.

## Important API / Interface Changes

### Internal Data Model
Introduce a structured mined-item object (replace implicit 3-line format at runtime):
- `id`
- `source_type`
- `source_name`
- `location` (`page`, `start_ms`, `end_ms`, etc.)
- `sentence`
- `target_expression`
- `translation`
- `context_before`, `context_after`
- `created_at`
- `status` (`queued`, `added`, `failed`)
- `anki_note_id` (optional)

Compatibility:
- Keep import/export support for existing `words_to_process.txt` format.
- Use structured storage (sqlite preferred) as primary internal state.

### Anki Integration
- Add model mapping config:
  - `deck_name`
  - `model_name`
  - `field_map` dict for richer note types.
- Fallback to current Basic model if mapping missing.

### Translation Interface
- Add service abstraction:
  - `translate(text, src, dest) -> TranslationResult`
  - includes `text`, `alternatives`, `confidence_hint`, `engine`.

## Delivery Sequencing (Full Vision)

### Phase 1 (Foundation)
- Structured mined-item storage + queue reliability.
- Expanded metadata capture (source/location/context).
- Better error/reporting UX.

### Phase 2 (Core Learning Upgrades)
- Card enrichment fields + mapping.
- Smart selection (expression suggestions + duplicate detection).
- Translation edit/alternatives UI.

### Phase 3 (Immersion Audio Loop)
- SRT mining UI path.
- Timestamp-aware cards.
- Optional audio clip export + Anki sound attachment.

### Phase 4 (Adaptive Intelligence)
- Dashboard metrics.
- Frequency-knownness prioritization.
- Anki review feedback loop and weak-item remine suggestions.

### Phase 5 (Scale & Polish)
- Source library/session management.
- Performance optimization for large docs/corpora.
- Packaging and release hardening.

## Test Cases and Scenarios

### Functional
1. Mine phrase from PDF, add now, confirm rich metadata fields populate correctly.
2. Mine subtitle phrase, verify timestamp + audio clip attachment in Anki.
3. Queue 100+ items, restart app, ensure no queue loss and consistent status recovery.
4. Attempt duplicate add; confirm warning and configurable behavior.
5. Translation service outage; verify graceful fallback and retry UX.

### Compatibility
1. Import legacy `words_to_process.txt` and process without loss.
2. Use default `Basic` note type and ensure old workflow still works.
3. Existing queue-processing CLI remains available via the supported `immersion_app.cli.queue` command.

### Performance
1. Large PDF (500+ pages) click latency stays acceptable.
2. Batch process large queue with controlled memory and clear progress reporting.
3. Subtitle mining on long SRTs remains responsive.

### Reliability
1. Crash/restart mid-queue should not corrupt queue.
2. Anki unavailable path should preserve items and surface actionable errors.
3. File-path resolution remains stable regardless of launch directory.

## Assumptions and Defaults
- Target user: self-directed immersion learner (Spanish-first, extensible later).
- Keep AnkiConnect as card sink; no replacement planned.
- Keep current translation engine as default initially; abstraction allows later engine swap.
- Internal persistence should migrate to sqlite while preserving legacy txt interoperability.
- Audio clipping is optional and can be disabled if ffmpeg pipeline fails.
- UI remains desktop-first (PySide6) rather than web/mobile in this roadmap.

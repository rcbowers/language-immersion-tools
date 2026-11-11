# Plan: MCP / LLM Integration

Status: brainstorm / not started

## Guiding principle

The LLM handles **logistics**: finding material, cleaning up, card admin and scheduling. The user still does the **immersion**: reading, listening and recall. Tools can prepare and tidy up around a session, but they never translate or summarise library content while the user is consuming it.

## Read actions (LLM looks at immersion state)

| Tool | Backed by | Why it's useful |
|---|---|---|
| `get_known_vocabulary(limit, since)` | `core/anki_snapshot.py`, `AnkiAnalyticsManager.vocabulary_seen` | Lets the LLM judge how hard a new text is, or pick material near the user's level. |
| `get_mining_queue()` | `core/queue_store.load_queue_entries`, `core/automine_queue.parse_queue_sections` | Shows pending cards and auto-mine requests so it can clean them up in batches. |
| `get_library(status=in_progress\|unstarted\|done)` | `ContentBrowserManager.get_all_content`, `CompletionTracker` | Answers "what am I partway through, and where did I stop?" |
| `get_activity_stats(days)` | `ActivityAnalyticsManager.get_dashboard_data`, `UsageTimeTracker` | Streaks, minutes per day and top sources, for weekly reviews and nudges. |
| `get_source_coverage(path_or_url)` | `media/source_context.load_source_contexts` + known vocab | Returns the % of known words and a list of the unknown lemmas. This is the "is this book too hard yet?" check. It returns numbers and words, never a translation. |
| `get_mined_contexts(word)` | processed log (`data/logs/processed_cards.log`) + queue | Every sentence where the user mined a word, for spotting leeches or duplicates. |

## Write actions (LLM changes something for the user)

| Tool | Behaviour | Guardrail |
|---|---|---|
| `add_to_library(path_or_url, tags)` | Registers a PDF, SRT or URL it found for the user, such as an article or a transcript. | Only adds it. The user opens it themselves. |
| `queue_automine(source, words[])` | Appends a section to `automine_inputs.md` in the format the auto-miner already parses. | Works on the user's word list ("mine these 10 words I flagged"), not words the LLM picked. |
| `enrich_queue_entry(id, fields)` | Fills in the card back: definition, part of speech, gender, IPA, a target-language-only gloss. | Stays in the queue as a draft until the user approves it in the app. |
| `dedupe_or_merge_queue()` | Merges inflected forms (e.g. `hablaba` → `hablar`) and drops words already in the snapshot. | Dry-run diff first. |
| `generate_subtitles(video)` | Wraps `integrations/subtitle_generation.py` so a video arrives with target-language subtitles ready. | Target language only, no translated track. |
| `set_reading_plan(path, pages_per_day)` | Writes goals that the completion tracker can check against. | It's just data, and the app shows it. |
| `log_external_immersion(minutes, kind, note)` | Records podcasts or conversations done outside the app into usage stats. | Streaks stay honest. |

## Workflows these enable

1. **Content scout:** "Find a Spanish article on climbing at ~95% known coverage." The LLM searches, runs `get_source_coverage` on each candidate, then calls `add_to_library` on the best one. The user reads it cold.
2. **Post-session tidy-up:** after the user mines 30 words, one command dedupes them, lemmatises them, fills target-language definitions and leaves them for one-click approval.
3. **Pre-reading primer, opt-in:** for the next chapter, it lists the 5 highest-frequency unknown words (words only), so the user can decide whether to pre-learn them.
4. **Weekly review:** `get_activity_stats` + `get_library` produce a "you're 60% through HP2, 3 days behind plan" summary that ties into the weekly-review flow.
5. **Leech triage:** it finds cards the user keeps failing and pulls 2–3 fresh example sentences from the user's own library, rather than generated ones.

## Implementation notes

- Put an `McpService` in `core/` (no Qt) or a separate `integrations/mcp_server.py` that imports only core functions. Most of the reads above already exist as pure functions, so the server is mostly a thin adapter.
- Writes go through the same core state managers that the GUI uses, so signals still fire and nothing gets out of sync (see `architecture_design_readme.md`).
- The server must tolerate running while the GUI is closed, which means writing to files (queue JSON, user data, `automine_inputs.md`) rather than to in-memory state. It needs a plan for concurrent writes when the GUI is open.
- **Immersion-safe mode** flag: blocks any tool from returning translations of library content.
- All new code needs tests, per AGENTS.md.

## Suggested first slice

1. `get_source_coverage`
2. `get_library`
3. `enrich_queue_entry`

Together these cover the content-scout and post-session tidy-up workflows.

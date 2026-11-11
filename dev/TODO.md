# Developer TODO

Small open items. Release-level work is tracked in [`plans/plan-public-release.md`](plans/plan-public-release.md).

## Features

- If a word is already in Anki (highlighted as "seen"), the translation popover should also show the existing card's front and its creation date.
- Daily/weekly study-time charts and per-file breakdown in the Activity view. Export usage data to CSV.
- Study goals.

## Bugs / polish

- The "Added to Anki" toast is too short vertically (needs ~25% more height).

## Done

- ~~Batch-translation log lines were printed in fragments~~: the legacy per-window prefetch logging was removed in the 0.9.0 cleanup. Prefetch failures now log one concise warning each.
- ~~Usage time tracking~~: implemented, then fixed for the public release. See [`docs/usage-time-tracking.md`](../docs/usage-time-tracking.md).

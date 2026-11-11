"""Compare two benchmark files written by ``perf_baseline.py``.

    python scripts/perf_compare.py dev/perf/baseline.json dev/perf/after.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def _load(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _pick(stat: dict, key: str):
    return stat.get(key) if stat.get("n") else None


def _fmt(value) -> str:
    return "-" if value is None else f"{value:,.1f}"


def _delta(before, after) -> str:
    if before in (None, 0) or after is None:
        return "-"
    ratio = before / after if after else float("inf")
    pct = (after - before) / before * 100.0
    return f"{pct:+.0f}% ({ratio:.1f}x {'faster' if ratio >= 1 else 'slower'})"


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__)
        return 2
    before, after = _load(argv[1]), _load(argv[2])
    print(f"before: {before['meta']['label']} @ {before['meta'].get('git_head', '?')}")
    print(f"after:  {after['meta']['label']} @ {after['meta'].get('git_head', '?')}\n")
    header = f"{'scenario':38s} {'metric':7s} {'before':>10s} {'after':>10s}  change"
    print(header)
    print("-" * len(header))
    for name in before["results"]:
        b, a = before["results"][name], after["results"].get(name, {"n": 0})
        for key in ("median", "p95", "max"):
            bv, av = _pick(b, key), _pick(a, key)
            if bv is None and av is None:
                continue
            if name == "ui_stall_max_ms" and key != "max":
                continue
            print(f"{name:38s} {key:7s} {_fmt(bv):>10s} {_fmt(av):>10s}  {_delta(bv, av)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

"""Headless UI latency benchmark for Language Immersion Tools.

Usage::

    python scripts/perf_baseline.py --label baseline
    python scripts/perf_baseline.py --label after
    python scripts/perf_compare.py dev/perf/baseline.json dev/perf/after.json

Runs against a throwaway data folder (never touches real user data) using the
offscreen Qt platform. Scenarios (times in milliseconds, "action -> settled"):

* cold_start_*   - fresh-process startup phases, with a PDF as the last session
* pdf_click      - ``click_at`` on distinct words
* pdf_hover      - Ctrl+hover on distinct words
* page_turn      - ``next_page`` after ~350 ms of "reading" (time for background prefetch)
* page_turn_rapid- ``next_page`` back-to-back with no pause (worst case, nothing prefetched)
* zoom_step      - ``zoom_in``
* theme_toggle   - light/dark switch
* ui_stall_max   - longest gap between 5 ms heartbeat ticks during the scenarios

"Settled" means the call returned *and* any pending asynchronous render has been
applied, so the same script measures both the synchronous and async designs.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
PERF_DIR = ROOT / "dev" / "perf"

_WORDS = (
    "el la de que y a en un ser se no haber por con su para como estar tener le lo todo pero mas hacer o poder decir "
    "esta ir otro ese si me ya ver porque dar cuando muy sin vez mucho saber que sobre tambien me hasta hay donde "
    "quien desde casi todos durante tanto ellos libro ciudad camino pregunta respuesta pequeno grande verdad manana"
).split()


def make_pdf(path: Path, pages: int = 50, words_per_page: int = 380) -> None:
    import fitz

    doc = fitz.open()
    for page_no in range(pages):
        page = doc.new_page()
        text = " ".join(_WORDS[(page_no * 7 + i * 3) % len(_WORDS)] for i in range(words_per_page))
        page.insert_textbox(fitz.Rect(50, 50, 545, 790), text, fontsize=11)
    doc.save(str(path))
    doc.close()


def stats(values: list[float]) -> dict:
    values = sorted(values)
    if not values:
        return {"n": 0}
    p95 = values[min(len(values) - 1, int(round(0.95 * (len(values) - 1))))]
    return {
        "n": len(values),
        "median": round(statistics.median(values), 3),
        "mean": round(statistics.fmean(values), 3),
        "p95": round(p95, 3),
        "max": round(values[-1], 3),
    }


def _prepare_data_dir(data_dir: Path, pdf_path: Path) -> None:
    """Write a user state whose last session is the benchmark PDF."""
    os.environ["IMMERSION_DATA_DIR"] = str(data_dir)
    sys.path.insert(0, str(SRC))
    from immersion_app.core.paths import USER_STATE_PATH, ensure_runtime_dirs
    from immersion_app.core.user_data import default_user_data

    ensure_runtime_dirs()
    payload = default_user_data()
    payload["preferences"]["translation_mode"] = "offline"
    payload["preferences"]["prefetch_enabled"] = False  # keep network/model work out of the numbers
    payload["last_session"].update({"content_type": "pdf", "pdf_path": str(pdf_path), "page_index": 0})
    USER_STATE_PATH.write_text(json.dumps(payload), encoding="utf-8")


def _pump(app, ms: float = 0.0) -> None:
    end = time.perf_counter() + ms / 1000.0
    app.processEvents()
    while time.perf_counter() < end:
        app.processEvents()


def _wait_settled(app, window, timeout_s: float = 15.0) -> None:
    """Pump events until no async render is pending (no-op for the sync design)."""
    deadline = time.perf_counter() + timeout_s
    controller = window.pdf_controller
    while time.perf_counter() < deadline:
        app.processEvents()
        if not getattr(controller, "render_pending", False):
            return
        time.sleep(0.0005)
    raise TimeoutError("render did not settle")


def _wait_page_visible(app, window, timeout_s: float = 30.0) -> None:
    deadline = time.perf_counter() + timeout_s
    while time.perf_counter() < deadline:
        app.processEvents()
        if window.pdf_controller.page_words:
            return
        time.sleep(0.001)
    raise TimeoutError("first page never became visible")


def cold_child() -> None:
    """Runs in a fresh process; prints phase timings (ms since process start) as JSON."""
    import psutil

    t_proc_start = psutil.Process().create_time()
    t_script = time.time()
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    sys.path.insert(0, str(SRC))
    marks = {"interpreter_boot": (t_script - t_proc_start) * 1000.0}
    t0 = time.perf_counter()

    from PySide6.QtWidgets import QApplication

    from immersion_app.gui.main_window import UnifiedSentenceMinerWindow

    marks["imports"] = (time.perf_counter() - t0) * 1000.0
    app = QApplication([])
    t1 = time.perf_counter()
    window = UnifiedSentenceMinerWindow()
    marks["window_init"] = (time.perf_counter() - t1) * 1000.0
    window.resize(1680, 980)
    t2 = time.perf_counter()
    window.show()
    app.processEvents()
    marks["window_shown"] = (time.perf_counter() - t2) * 1000.0
    # Overlay is removed at the end of ``_deferred_startup``; also wait for the first page.
    deadline = time.perf_counter() + 30
    startup_done = None
    while time.perf_counter() < deadline:
        app.processEvents()
        if startup_done is None and getattr(window, "_startup_overlay", 1) is None:
            startup_done = (time.perf_counter() - t1) * 1000.0
        if window.pdf_controller.page_words:
            break
        time.sleep(0.001)
    marks["startup_overlay_dismissed"] = startup_done if startup_done is not None else float("nan")
    marks["first_page_visible"] = (time.perf_counter() - t1) * 1000.0
    marks["total_to_first_page"] = marks["imports"] + marks["first_page_visible"]
    print("COLDJSON " + json.dumps(marks))
    sys.stdout.flush()
    window._block_detector.stop()
    os._exit(0)  # skip slow Qt/QtMultimedia teardown


def run_cold(data_dir: Path, runs: int) -> dict:
    env = dict(os.environ, IMMERSION_DATA_DIR=str(data_dir), QT_QPA_PLATFORM="offscreen")
    collected: dict[str, list[float]] = {}
    for i in range(runs):
        proc = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "--cold-child"],
            env=env, capture_output=True, text=True, timeout=180,
        )
        line = next((ln for ln in proc.stdout.splitlines() if ln.startswith("COLDJSON ")), None)
        if line is None:
            raise RuntimeError(f"cold child failed:\n{proc.stdout}\n{proc.stderr}")
        for key, value in json.loads(line[len("COLDJSON "):]).items():
            collected.setdefault(f"cold_start_{key}", []).append(value)
        print(f"  cold run {i + 1}/{runs} first_page_visible="
              f"{collected['cold_start_first_page_visible'][-1]:.0f} ms", flush=True)
    return {name: stats(vals) for name, vals in collected.items()}


def run_interaction(pdf_path: Path, iterations: int) -> dict:
    from PySide6.QtCore import QPoint, QTimer, Qt
    from PySide6.QtWidgets import QApplication

    app = QApplication([])
    from immersion_app.gui.main_window import UnifiedSentenceMinerWindow

    window = UnifiedSentenceMinerWindow()
    window.resize(1680, 980)
    window.show()
    _pump(app, 50)
    _wait_page_visible(app, window)  # session restore opens the PDF
    _wait_settled(app, window)
    controller = window.pdf_controller
    window._block_detector.stop()  # the app's own heartbeat would add timer noise

    stall = {"last": time.perf_counter(), "max": 0.0, "armed": False}

    def beat():
        now = time.perf_counter()
        if stall["armed"]:
            stall["max"] = max(stall["max"], (now - stall["last"]) * 1000.0 - 5.0)
        stall["last"] = now

    heartbeat = QTimer()
    heartbeat.setInterval(5)
    heartbeat.timeout.connect(beat)
    heartbeat.start()

    def word_points(count: int, offset: int = 0) -> list[QPoint]:
        order = controller.page_word_order
        step = max(1, len(order) // (count + offset + 1))
        pts = []
        for k in range(count):
            w = order[min(len(order) - 1, (k + offset + 1) * step)]
            pts.append(QPoint(int((w[0] + w[2]) / 2 * controller.zoom_factor),
                              int((w[1] + w[3]) / 2 * controller.zoom_factor)))
        return pts

    results: dict[str, list[float]] = {"pdf_click": [], "pdf_hover": [], "page_turn": [], "page_turn_rapid": [],
                                       "zoom_step": [], "theme_toggle": []}

    def timed(bucket: str, fn, think_ms: float = 0.0) -> None:
        stall["last"] = time.perf_counter()
        stall["armed"] = True
        t = time.perf_counter()
        fn()
        _wait_settled(app, window)
        results[bucket].append((time.perf_counter() - t) * 1000.0)
        stall["armed"] = False
        _pump(app, think_ms)

    no_mod = Qt.KeyboardModifier.NoModifier
    ctrl = Qt.KeyboardModifier.ControlModifier

    for i, pt in enumerate(word_points(iterations + 1)):
        if i == 0:
            controller.click_at(pt, no_mod)  # warm-up
            _wait_settled(app, window)
            continue
        timed("pdf_click", lambda pt=pt: controller.click_at(pt, no_mod))

    for i, pt in enumerate(word_points(iterations + 1, offset=iterations)):
        if i == 0:
            controller.hover_at(pt, ctrl)
            _wait_settled(app, window)
            continue
        timed("pdf_hover", lambda pt=pt: controller.hover_at(pt, ctrl))

    # Page turns. Always forward over fresh pages (never re-visiting a cached page), so every turn is a
    # genuine first view. "page_turn" leaves reading time between turns; "page_turn_rapid" does not.
    page_count = controller.pdf_service.page_count()
    for bucket, think_ms in (("page_turn", 350.0), ("page_turn_rapid", 0.0)):
        controller.jump_to_page(1)
        _wait_settled(app, window)
        _pump(app, 400)
        for _ in range(min(iterations, page_count - 2)):
            timed(bucket, controller.next_page, think_ms)

    # Zoom: alternate in/out so the zoom stays in range and each step renders at a new size.
    for i in range(iterations):
        timed("zoom_step", controller.zoom_in if i % 2 == 0 else controller.zoom_out)

    # Theme toggle (light <-> dark). Records the UI-thread cost of the switch itself.
    mode = "dark"
    for _ in range(max(6, iterations // 3)):
        timed("theme_toggle", lambda m=mode: window._on_appearance_changed(m))
        mode = "light" if mode == "dark" else "dark"

    heartbeat.stop()
    out = {name: stats(vals) for name, vals in results.items()}
    out["ui_stall_max_ms"] = {"n": 1, "max": round(stall["max"], 3)}
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--label", default="baseline", help="output name: dev/perf/<label>.json")
    parser.add_argument("--pdf", help="PDF to benchmark (default: generated 50-page text-heavy PDF)")
    parser.add_argument("--iterations", type=int, default=30)
    parser.add_argument("--cold-runs", type=int, default=5)
    parser.add_argument("--cold-child", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--interaction-child", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args.cold_child:
        cold_child()
        return 0

    if args.interaction_child:
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        sys.path.insert(0, str(SRC))
        result = run_interaction(Path(args.pdf), args.iterations)
        print("INTJSON " + json.dumps(result))
        sys.stdout.flush()
        os._exit(0)

    workdir = Path(tempfile.mkdtemp(prefix="immersion-perf-"))
    pdf_path = Path(args.pdf).resolve() if args.pdf else workdir / "bench.pdf"
    if not args.pdf:
        print("Generating benchmark PDF ...", flush=True)
        make_pdf(pdf_path)
    data_dir = workdir / "data"
    _prepare_data_dir(data_dir, pdf_path)

    print(f"Cold start x{args.cold_runs} ...", flush=True)
    results = run_cold(data_dir, args.cold_runs)

    print("Interaction scenarios ...", flush=True)
    env = dict(os.environ, IMMERSION_DATA_DIR=str(data_dir), QT_QPA_PLATFORM="offscreen")
    proc = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), "--interaction-child", "--pdf", str(pdf_path),
         "--iterations", str(args.iterations)],
        env=env, capture_output=True, text=True, timeout=900,
    )
    line = next((ln for ln in proc.stdout.splitlines() if ln.startswith("INTJSON ")), None)
    if line is None:
        raise RuntimeError(f"interaction child failed:\n{proc.stdout}\n{proc.stderr}")
    results.update(json.loads(line[len("INTJSON "):]))

    meta = {
        "label": args.label,
        "python": sys.version.split()[0],
        "pdf": "generated 50-page" if not args.pdf else str(pdf_path),
        "iterations": args.iterations,
        "cold_runs": args.cold_runs,
        "git_head": subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True,
                                   text=True).stdout.strip(),
    }
    PERF_DIR.mkdir(parents=True, exist_ok=True)
    out_path = PERF_DIR / f"{args.label}.json"
    out_path.write_text(json.dumps({"meta": meta, "results": results}, indent=2), encoding="utf-8")
    print(f"\nWrote {out_path}")
    for name, st in results.items():
        if st.get("n"):
            print(f"  {name:38s} median={st.get('median', st.get('max')):>10} "
                  f"p95={st.get('p95', '-'):>10} max={st['max']:>10}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Live visual monitor for a questionnaire-bot submission run.

Reads a JSONL results file (one SubmissionResult per line) plus the dataset
to know the target total, then renders an informative progress dashboard.

Usage:
    python scripts/monitor.py --results data/sambel_pecel_150.jsonl --total 150
    python scripts/monitor.py --results data/sambel_pecel_150.jsonl --total 150 --watch

--watch refreshes every few seconds until total submissions are reached.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path


GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"


def _enable_ansi() -> None:
    if os.name == "nt":
        os.system("")  # enable VT100 on Windows terminal


def load_results(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def bar(done: int, total: int, width: int = 40) -> str:
    if total <= 0:
        total = 1
    filled = int(width * done / total)
    filled = min(filled, width)
    return "█" * filled + "░" * (width - filled)


def fmt_status(status: str) -> str:
    color = {
        "success": GREEN,
        "timeout": YELLOW,
        "fill_failed": RED,
        "submit_failed": RED,
        "form_load_failed": RED,
        "exception": RED,
        "pending": DIM,
    }.get(status, "")
    return f"{color}{status}{RESET}"


def render(results_path: Path, total: int) -> bool:
    """Render one dashboard frame. Returns True if run is complete."""
    rows = load_results(results_path)
    n = len(rows)
    by_status = Counter(r.get("status", "?") for r in rows)
    success = by_status.get("success", 0)
    fails = n - success

    # unique successful persona ids (dedup across retries)
    success_ids = {r["persona_id"] for r in rows if r.get("status") == "success"}
    uniq_success = len(success_ids)

    durations = [r.get("duration_seconds", 0) for r in rows if r.get("status") == "success"]
    avg_dur = sum(durations) / len(durations) if durations else 0
    remaining = max(0, total - uniq_success)
    eta_sec = remaining * avg_dur if avg_dur else 0

    lines: list[str] = []
    lines.append(f"{BOLD}{CYAN}╔══════════════════════════════════════════════════════════════╗{RESET}")
    lines.append(f"{BOLD}{CYAN}║   QUESTIONNAIRE BOT — MONITOR  (Sambel Pecel Ponorogo)        ║{RESET}")
    lines.append(f"{BOLD}{CYAN}╚══════════════════════════════════════════════════════════════╝{RESET}")
    lines.append("")
    pct = 100 * uniq_success / total if total else 0
    lines.append(f"  {BOLD}Progress{RESET}  [{GREEN}{bar(uniq_success, total)}{RESET}] {uniq_success}/{total}  ({pct:.1f}%)")
    lines.append("")
    lines.append(f"  {GREEN}✓ success (unik){RESET} : {BOLD}{uniq_success}{RESET}")
    lines.append(f"  {RED}✗ gagal (attempt){RESET}: {BOLD}{fails}{RESET}")
    lines.append(f"  {DIM}Σ total attempt{RESET} : {n}")
    lines.append(f"  {DIM}avg durasi/sub{RESET}  : {avg_dur:.1f}s")
    if remaining and avg_dur:
        mins = eta_sec / 60
        lines.append(f"  {DIM}sisa{RESET}           : {remaining}  (~{mins:.0f} menit lagi)")
    lines.append("")

    # Status breakdown
    lines.append(f"  {BOLD}Status breakdown:{RESET}")
    for st, c in by_status.most_common():
        lines.append(f"     {fmt_status(st):24s} {c}")
    lines.append("")

    # Failures detail
    fail_rows = [r for r in rows if r.get("status") != "success"]
    if fail_rows:
        lines.append(f"  {BOLD}{RED}Kegagalan (perlu retry):{RESET}")
        shown = fail_rows[-8:]
        for r in shown:
            pid = r.get("persona_id", "?")
            st = r.get("status", "?")
            nama = r.get("nama", "?")[:28]
            err = (r.get("error") or "")[:32]
            lines.append(f"     #{pid:<4} {fmt_status(st):22s} {nama:30s} {DIM}{err}{RESET}")
        if len(fail_rows) > 8:
            lines.append(f"     {DIM}... +{len(fail_rows)-8} lagi{RESET}")
        lines.append("")

    # Last few activity
    lines.append(f"  {BOLD}Aktivitas terakhir:{RESET}")
    for r in rows[-6:]:
        pid = r.get("persona_id", "?")
        st = r.get("status", "?")
        nama = r.get("nama", "?")[:28]
        ts = r.get("timestamp", "")[-8:]
        dur = r.get("duration_seconds", 0)
        lines.append(f"     {DIM}{ts}{RESET} #{pid:<4} {fmt_status(st):22s} {nama:30s} {DIM}{dur}s{RESET}")

    lines.append("")
    lines.append(f"  {DIM}refresh: {datetime.now().strftime('%H:%M:%S')}  |  file: {results_path.name}{RESET}")

    sys.stdout.write("\033[2J\033[H")  # clear screen + home
    sys.stdout.write("\n".join(lines) + "\n")
    sys.stdout.flush()

    return uniq_success >= total


def main(argv: list[str] | None = None) -> int:
    _enable_ansi()
    ap = argparse.ArgumentParser(description="Monitor questionnaire-bot run")
    ap.add_argument("--results", required=True, help="Path to JSONL results file")
    ap.add_argument("--total", type=int, default=150, help="Target total submissions")
    ap.add_argument("--watch", action="store_true", help="Auto-refresh until complete")
    ap.add_argument("--interval", type=float, default=5.0, help="Refresh interval seconds")
    args = ap.parse_args(argv)

    results_path = Path(args.results)

    if not args.watch:
        render(results_path, args.total)
        return 0

    try:
        while True:
            done = render(results_path, args.total)
            if done:
                print(f"\n{GREEN}{BOLD}  ✅ SELESAI — {args.total}/{args.total} submission sukses!{RESET}\n")
                return 0
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print(f"\n{DIM}monitor dihentikan (run tetap jalan di background){RESET}\n")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())

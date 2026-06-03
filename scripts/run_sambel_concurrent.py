"""Concurrent background runner for Sambel Pecel form — N workers, fast mode.

Why this exists: faster than 1-at-a-time, but still SAFE on a memory-limited
machine. Concurrency is configurable; each worker fills the form in --fast
mode, while worker *starts* are staggered so submission timestamps don't all
land at the same instant ("samar di cek jam pengisian e").

Key properties:
  - Resume-safe: persona ids already 'success' in the JSONL are skipped, so
    re-running never double-submits a persona that already went through.
  - Retry: failures are retried across rounds until all unique personas
    succeed or MAX_ROUNDS is hit.
  - Concurrency bounded by asyncio.Semaphore (default 3).
  - 300s wall-clock guard per submission (inherited via asyncio.wait_for).

Writes:
  - data/sambel_pecel_150.jsonl  : append-only attempt log (monitor reads this)
  - data/sambel_pecel_run.log    : full text log

Usage:
  python scripts/run_sambel_concurrent.py --concurrency 3
  python scripts/run_sambel_concurrent.py --concurrency 5   # needs more RAM
"""
from __future__ import annotations

import argparse
import asyncio
import json
import random
import sys
from pathlib import Path

from loguru import logger

from qbot.runner import append_results_jsonl, run_one
from qbot.schema import load_schema

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "schemas" / "umkm-sambel-pecel-ponorogo.json"
DATASET = ROOT / "data" / "sambel_pecel_150.json"
RESULTS = ROOT / "data" / "sambel_pecel_150.jsonl"
LOGFILE = ROOT / "data" / "sambel_pecel_run.log"

MAX_ROUNDS = 5            # retry rounds over the still-missing personas
PER_SUB_TIMEOUT = 300.0   # wall-clock guard per submission
# Stagger between worker launches so starts (and thus submit times) spread out.
STAGGER_MIN = 4.0
STAGGER_MAX = 12.0


def _setup_logging() -> None:
    logger.remove()
    logger.add(sys.stderr, level="INFO",
               format="<green>{time:HH:mm:ss}</green> | <level>{level:7}</level> | {message}")
    logger.add(str(LOGFILE), level="INFO",
               format="{time:YYYY-MM-DD HH:mm:ss} | {level:7} | {message}",
               encoding="utf-8")


def load_done_ids() -> set[int]:
    done: set[int] = set()
    if RESULTS.exists():
        for line in RESULTS.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if r.get("status") == "success":
                done.add(int(r["persona_id"]))
    return done


async def run_pending(schema, pending: list[dict], concurrency: int) -> None:
    """Run all pending personas with bounded concurrency + staggered starts."""
    sem = asyncio.Semaphore(concurrency)
    write_lock = asyncio.Lock()
    launch_lock = asyncio.Lock()
    rng = random.Random()

    async def worker(persona: dict) -> None:
        pid = int(persona["id"])
        nama = persona["biodata"].get("nama", f"persona_{pid}")
        async with sem:
            # Stagger the actual start so concurrent workers don't submit in
            # a synchronized burst (organic submission timing).
            async with launch_lock:
                await asyncio.sleep(rng.uniform(STAGGER_MIN, STAGGER_MAX))
            logger.info(f"#{pid} {nama} — START")
            try:
                record = await asyncio.wait_for(
                    run_one(schema, persona, headful=False, fast=True),
                    timeout=PER_SUB_TIMEOUT,
                )
            except asyncio.TimeoutError:
                from qbot.runner import SubmissionResult
                from datetime import datetime
                record = SubmissionResult(
                    timestamp=datetime.now().isoformat(timespec="seconds"),
                    schema_id=schema.id, persona_id=pid,
                    archetype=str(persona.get("archetype", "unknown")),
                    nama=nama, status="timeout",
                    error="run_one exceeded 300s wall-clock",
                )
            async with write_lock:
                append_results_jsonl(RESULTS, record)
            if record.status == "success":
                logger.success(f"#{pid} {nama} OK in {record.duration_seconds}s")
            else:
                logger.warning(f"#{pid} {nama} -> {record.status} ({record.error})")

    tasks = [asyncio.create_task(worker(p)) for p in pending]
    await asyncio.gather(*tasks, return_exceptions=True)


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--concurrency", "-c", type=int, default=3)
    args = ap.parse_args()

    _setup_logging()
    schema = load_schema(SCHEMA)
    personas = json.loads(DATASET.read_text(encoding="utf-8"))
    total = len(personas)
    all_ids = {int(p["id"]) for p in personas}

    logger.info(f"START concurrent run | total={total} | conc={args.concurrency} | fast=True")

    for rnd in range(1, MAX_ROUNDS + 1):
        done = load_done_ids()
        pending = [p for p in personas if int(p["id"]) not in done]
        if not pending:
            break
        logger.info(f"ROUND {rnd}/{MAX_ROUNDS} | done={len(done)} | pending={len(pending)}")
        await run_pending(schema, pending, args.concurrency)

    done = load_done_ids()
    logger.info(f"FINISH | unique_success={len(done)}/{total}")
    if len(done) >= total:
        logger.success(f"ALL {total} SUBMISSIONS COMPLETE")
        return 0
    missing = sorted(all_ids - done)
    logger.error(f"INCOMPLETE | missing ids: {missing}")
    return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

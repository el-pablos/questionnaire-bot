"""Concurrent background runner for Sambel Pecel form — N workers, fast mode.

Key properties:
  - Resume-safe: persona ids already 'success' in JSONL are skipped automatically.
  - Retry: failures retried across MAX_ROUNDS until all target personas succeed.
  - Concurrency bounded by asyncio.Semaphore.
  - 300s wall-clock guard per submission via asyncio.wait_for.
  - Staggered worker starts so submission timestamps spread organically.
  - --dataset to point at a specific persona slice (zero-overlap multi-machine use).
  - --results to use a separate JSONL per machine.

Usage examples:
  # Windows (personas #1-100, concurrency 3)
  python scripts/run_sambel_concurrent.py -c 3

  # VPS (personas #101-150, concurrency 10, separate results file)
  python scripts/run_sambel_concurrent.py -c 10 \\
      --dataset data/sambel_vps_101_150.json \\
      --results data/sambel_vps_101_150.jsonl
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
SCHEMA_PATH = ROOT / "schemas" / "umkm-sambel-pecel-ponorogo.json"

MAX_ROUNDS = 5
PER_SUB_TIMEOUT = 300.0
STAGGER_MIN = 3.0
STAGGER_MAX = 10.0


def _setup_logging(logfile: Path) -> None:
    logger.remove()
    logger.add(
        sys.stderr, level="INFO",
        format="<green>{time:HH:mm:ss}</green> | <level>{level:7}</level> | {message}",
    )
    logger.add(
        str(logfile), level="INFO",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level:7} | {message}",
        encoding="utf-8",
    )


def load_done_ids(results: Path) -> set[int]:
    """Return set of persona_ids that already have a 'success' record."""
    done: set[int] = set()
    if not results.exists():
        return done
    for line in results.read_text(encoding="utf-8").splitlines():
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


async def run_pending(schema, pending: list[dict], concurrency: int, results: Path) -> None:
    """Run all pending personas with bounded concurrency + staggered starts."""
    sem = asyncio.Semaphore(concurrency)
    write_lock = asyncio.Lock()
    launch_lock = asyncio.Lock()
    rng = random.Random()

    async def worker(persona: dict) -> None:
        pid = int(persona["id"])
        nama = persona["biodata"].get("nama", f"persona_{pid}")
        async with sem:
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
                append_results_jsonl(results, record)
            if record.status == "success":
                logger.success(f"#{pid} {nama} OK in {record.duration_seconds}s")
            else:
                logger.warning(f"#{pid} {nama} -> {record.status} ({record.error})")

    tasks = [asyncio.create_task(worker(p)) for p in pending]
    await asyncio.gather(*tasks, return_exceptions=True)


async def main() -> int:
    ap = argparse.ArgumentParser(description="Concurrent Sambel Pecel form runner")
    ap.add_argument("--concurrency", "-c", type=int, default=3,
                    help="Number of parallel browser workers (default: 3)")
    ap.add_argument("--dataset", default=None,
                    help="Dataset JSON file (default: data/sambel_pecel_150.json)")
    ap.add_argument("--results", default=None,
                    help="Results JSONL file (default: data/sambel_pecel_150.jsonl)")
    args = ap.parse_args()

    dataset_path = Path(args.dataset) if args.dataset else ROOT / "data" / "sambel_pecel_150.json"
    results_path = Path(args.results) if args.results else ROOT / "data" / "sambel_pecel_150.jsonl"
    logfile_path = results_path.with_suffix(".log")

    _setup_logging(logfile_path)
    schema = load_schema(SCHEMA_PATH)
    personas = json.loads(dataset_path.read_text(encoding="utf-8"))
    total = len(personas)
    all_ids = {int(p["id"]) for p in personas}

    logger.info(
        f"START | dataset={dataset_path.name} | results={results_path.name} "
        f"| total={total} | conc={args.concurrency} | fast=True"
    )

    for rnd in range(1, MAX_ROUNDS + 1):
        done = load_done_ids(results_path)
        pending = [p for p in personas if int(p["id"]) not in done]
        if not pending:
            break
        logger.info(f"ROUND {rnd}/{MAX_ROUNDS} | done={len(done)} | pending={len(pending)}")
        await run_pending(schema, pending, args.concurrency, results_path)

    done = load_done_ids(results_path)
    logger.info(f"FINISH | unique_success={len(done)}/{total}")
    if len(done) >= total:
        logger.success(f"ALL {total} SUBMISSIONS COMPLETE ✓")
        return 0
    missing = sorted(all_ids - done)
    logger.error(f"INCOMPLETE | missing ids: {missing}")
    return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

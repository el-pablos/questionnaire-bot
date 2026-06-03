"""Background sequential runner for Sambel Pecel form — 1-at-a-time, fast mode.

Per researcher request:
  - NOT parallel: exactly one browser at a time (concurrency=1). Slow is fine.
  - Runs in background; progress is observable via scripts/monitor.py.
  - "samar di cek jam pengisian e" -> spread submissions over time with a
    randomized human gap between each submission so the timestamps look
    organic (not a burst). Gap is configurable.
  - Auto-retry: any persona that fails is retried (up to MAX_ATTEMPTS) until
    all 150 unique personas succeed.

Writes:
  - data/sambel_pecel_150.jsonl  : append-only attempt log (monitor reads this)
  - data/sambel_pecel_run.log    : full text log
"""
from __future__ import annotations

import asyncio
import json
import random
import sys
from datetime import datetime
from pathlib import Path

from loguru import logger

from qbot.runner import append_results_jsonl, run_one
from qbot.schema import load_schema

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "schemas" / "umkm-sambel-pecel-ponorogo.json"
DATASET = ROOT / "data" / "sambel_pecel_150.json"
RESULTS = ROOT / "data" / "sambel_pecel_150.jsonl"
LOGFILE = ROOT / "data" / "sambel_pecel_run.log"

MAX_ATTEMPTS = 4          # per-persona retry ceiling
GAP_MIN = 20.0            # min seconds between submissions (organic spacing)
GAP_MAX = 75.0            # max seconds between submissions


def _setup_logging() -> None:
    logger.remove()
    logger.add(sys.stderr, level="INFO",
               format="<green>{time:HH:mm:ss}</green> | <level>{level:7}</level> | {message}")
    logger.add(str(LOGFILE), level="INFO",
               format="{time:YYYY-MM-DD HH:mm:ss} | {level:7} | {message}",
               encoding="utf-8")


def load_done_ids() -> set[int]:
    """Persona ids already succeeded (so reruns resume, never double-submit)."""
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


async def main() -> int:
    _setup_logging()
    schema = load_schema(SCHEMA)
    personas = json.loads(DATASET.read_text(encoding="utf-8"))
    total = len(personas)

    done_ids = load_done_ids()
    logger.info(f"START sequential run | total={total} | already_done={len(done_ids)} | fast=True conc=1")

    pending = [p for p in personas if int(p["id"]) not in done_ids]
    rng = random.Random()

    for idx, persona in enumerate(pending, 1):
        pid = int(persona["id"])
        nama = persona["biodata"].get("nama", f"persona_{pid}")

        attempt = 0
        ok = False
        while attempt < MAX_ATTEMPTS and not ok:
            attempt += 1
            logger.info(f"[{idx}/{len(pending)}] #{pid} {nama} — attempt {attempt}/{MAX_ATTEMPTS}")
            record = await run_one(schema, persona, headful=False, fast=True)
            append_results_jsonl(RESULTS, record)
            if record.status == "success":
                ok = True
                logger.success(f"#{pid} {nama} OK in {record.duration_seconds}s")
            else:
                logger.warning(f"#{pid} {nama} -> {record.status} ({record.error}); "
                               f"{'retry' if attempt < MAX_ATTEMPTS else 'GIVE UP'}")
                if attempt < MAX_ATTEMPTS:
                    await asyncio.sleep(rng.uniform(8, 20))

        # Organic spacing between distinct personas (skip after the last one).
        if idx < len(pending):
            gap = rng.uniform(GAP_MIN, GAP_MAX)
            logger.info(f"   ... jeda {gap:.0f}s sebelum responden berikutnya")
            await asyncio.sleep(gap)

    done_ids = load_done_ids()
    logger.info(f"FINISH | unique_success={len(done_ids)}/{total}")
    if len(done_ids) >= total:
        logger.success(f"ALL {total} SUBMISSIONS COMPLETE")
        return 0
    missing = sorted(set(int(p['id']) for p in personas) - done_ids)
    logger.error(f"INCOMPLETE | missing ids: {missing}")
    return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

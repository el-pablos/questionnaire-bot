"""Submission runner: drives a Camoufox browser through a multi-page Google Form.

Strategy: build a complete value map from schema+persona, walk every page,
fill every entry id present, click Berikutnya until Submit appears, click
Submit, wait for confirmation.
"""
from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from camoufox.async_api import AsyncCamoufox
from loguru import logger
from playwright.async_api import Page, TimeoutError as PWTimeoutError

from .filler import (
    click_checkboxes,
    click_next,
    click_radio,
    click_scale,
    click_submit,
    entries_on_page,
    fill_text,
    has_submit,
    human_delay,
)
from .schema import FormField, FormSchema


# ---------------------------------------------------------------------------
# Result record
# ---------------------------------------------------------------------------

@dataclass
class SubmissionResult:
    timestamp: str
    schema_id: str
    persona_id: int
    archetype: str
    nama: str
    status: str
    error: str | None = None
    duration_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


# ---------------------------------------------------------------------------
# Value map: entry_id -> {type, label, value} for every field.
# ---------------------------------------------------------------------------

def build_value_map(schema: FormSchema, persona: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Map entry_id -> {type, label, value} using persona + schema."""
    bio = persona.get("biodata", {})
    answers = persona.get("answers", {})
    vmap: dict[str, dict[str, Any]] = {}
    for f in schema.fields:
        if f.type == "scale":
            value = answers.get(f.key)
        else:
            value = bio.get(f.key)
        if value is None:
            continue
        vmap[f.entry] = {
            "type": f.type,
            "label": f.label,
            "value": value,
        }
    return vmap


async def fill_one(page: Page, entry_id: str, spec: dict[str, Any]) -> bool:
    """Dispatch a single field fill based on its declared type."""
    t = spec["type"]
    label = spec["label"]
    v = spec["value"]
    if t == "text":
        return await fill_text(page, label, str(v))
    if t == "radio":
        return await click_radio(page, label, str(v))
    if t == "checkbox":
        return await click_checkboxes(page, label, list(v))
    if t == "scale":
        return await click_scale(page, label, int(v))
    logger.error(f"fill_one: unknown spec type {t} for {entry_id}")
    return False


# ---------------------------------------------------------------------------
# Multi-page form walker
# ---------------------------------------------------------------------------

async def fill_form(page: Page, schema: FormSchema, persona: dict[str, Any]) -> bool:
    """Walk the multi-page form, filling every entry id wherever it appears."""
    vmap = build_value_map(schema, persona)
    filled: set[str] = set()
    persona_label = str(persona.get("biodata", {}).get("nama_lengkap")
                        or persona.get("biodata", {}).get("nama")
                        or f"persona_{persona.get('id')}")

    max_pages = 20
    for page_idx in range(max_pages):
        await human_delay(0.6, 1.4)

        entries = await entries_on_page(page)
        logger.info(f"[{persona_label}] page {page_idx + 1}: {len(entries)} entries")

        for entry_id in entries:
            if entry_id not in vmap:
                logger.warning(f"[{persona_label}]   skip unknown entry {entry_id}")
                continue
            if entry_id in filled:
                continue
            ok = await fill_one(page, entry_id, vmap[entry_id])
            if not ok:
                logger.error(f"[{persona_label}] fill failed at {entry_id}")
                return False
            filled.add(entry_id)
            await human_delay(0.2, 0.6)

        if await has_submit(page):
            logger.info(
                f"[{persona_label}] submit visible after page {page_idx + 1}; "
                f"filled {len(filled)}/{len(vmap)}"
            )
            break

        entries_before = set(entries)
        if not await click_next(page):
            logger.error(f"[{persona_label}] no Next/Submit on page {page_idx + 1}")
            return False
        await human_delay(1.0, 2.0)
        entries_after = set(await entries_on_page(page))
        if entries_after == entries_before and entries_after:
            logger.error(
                f"[{persona_label}] stuck on same entries after Next on page {page_idx + 1}; "
                "likely validation failure"
            )
            return False
    else:
        logger.error(f"[{persona_label}] exceeded max_pages={max_pages} without finding submit")
        return False

    missing = set(vmap.keys()) - filled
    if missing:
        logger.warning(f"[{persona_label}] did not fill {len(missing)} entries: {sorted(missing)}")
    return True


async def submit_form(page: Page) -> bool:
    """Click Kirim/Submit and wait for confirmation page."""
    if not await click_submit(page):
        return False
    try:
        await page.wait_for_url(re.compile(r"formResponse"), timeout=30000)
        return True
    except PWTimeoutError:
        try:
            await page.wait_for_selector(
                'text=/Tanggapan Anda|Your response|telah direkam|has been recorded/i',
                timeout=15000,
            )
            return True
        except PWTimeoutError:
            logger.error("submit_form: confirmation not detected")
            return False


# ---------------------------------------------------------------------------
# Single-persona runner (one browser instance, one submission)
# ---------------------------------------------------------------------------

async def run_one(
    schema: FormSchema,
    persona: dict[str, Any],
    headful: bool = False,
    fast: bool = False,
) -> SubmissionResult:
    """Run a single persona end-to-end. Returns a SubmissionResult."""
    started = datetime.now()
    nama = str(
        persona.get("biodata", {}).get("nama_lengkap")
        or persona.get("biodata", {}).get("nama")
        or f"persona_{persona.get('id')}"
    )
    record = SubmissionResult(
        timestamp=started.isoformat(timespec="seconds"),
        schema_id=schema.id,
        persona_id=int(persona.get("id", 0)),
        archetype=str(persona.get("archetype", "unknown")),
        nama=nama,
        status="pending",
    )
    try:
        async with AsyncCamoufox(
            headless=not headful,
            humanize=not fast,
            os=["windows"],
            locale=[schema.locale, "en-US"],
            i_know_what_im_doing=True,
        ) as browser:
            page = await browser.new_page() if hasattr(browser, "new_page") else browser.pages[0]
            try:
                await page.goto(schema.form_url, wait_until="domcontentloaded", timeout=45000)
            except PWTimeoutError:
                record.status = "form_load_failed"
                record.error = "Form page load timeout"
                return record
            await human_delay(0.5, 1.0) if not fast else await asyncio.sleep(0.3)
            if not await fill_form(page, schema, persona):
                record.status = "fill_failed"
                record.error = "Form fill failed"
                return record
            if not await submit_form(page):
                record.status = "submit_failed"
                record.error = "Submit/confirmation failed"
                return record
            record.status = "success"
            logger.success(f"[#{record.persona_id}] submitted as {nama} ({schema.id})")
    except Exception as e:
        logger.exception(f"[#{record.persona_id}] unhandled error: {e}")
        record.status = "exception"
        record.error = repr(e)
    finally:
        record.duration_seconds = round((datetime.now() - started).total_seconds(), 2)
    return record


# ---------------------------------------------------------------------------
# Parallel batch runner with semaphore-based concurrency
# ---------------------------------------------------------------------------

async def run_batch(
    schema: FormSchema,
    personas: list[dict[str, Any]],
    concurrency: int = 1,
    headful: bool = False,
    fast: bool = False,
    min_jitter: float = 3.0,
    max_jitter: float = 8.0,
    on_result: "Any | None" = None,
) -> list[SubmissionResult]:
    """Run many personas in parallel, bounded by `concurrency`.

    on_result, when supplied, is invoked synchronously after every submission
    completes (success or failure) - useful for incremental result writes.
    """
    if concurrency < 1:
        raise ValueError("concurrency must be >= 1")
    sem = asyncio.Semaphore(concurrency)
    results: list[SubmissionResult] = []
    lock = asyncio.Lock()
    import random as _random

    async def worker(persona: dict[str, Any]) -> None:
        async with sem:
            if not fast:
                await asyncio.sleep(_random.uniform(min_jitter, max_jitter))
            try:
                record = await asyncio.wait_for(
                    run_one(schema, persona, headful=headful, fast=fast),
                    timeout=300.0,
                )
            except asyncio.TimeoutError:
                record = SubmissionResult(
                    timestamp=__import__('datetime').datetime.now().isoformat(timespec='seconds'),
                    schema_id=schema.id,
                    persona_id=int(persona.get('id', 0)),
                    archetype=str(persona.get('archetype', 'unknown')),
                    nama=str(persona.get('biodata', {}).get('nama_lengkap') or persona.get('biodata', {}).get('nama') or f"persona_{persona.get('id')}"),
                    status='timeout',
                    error='run_one exceeded 300s wall-clock',
                )
            async with lock:
                results.append(record)
                if on_result is not None:
                    on_result(record)

    tasks = [asyncio.create_task(worker(p)) for p in personas]
    done = await asyncio.gather(*tasks, return_exceptions=True)
    # Surface unexpected exceptions into log without crashing the batch
    for r in done:
        if isinstance(r, BaseException) and not isinstance(r, asyncio.CancelledError):
            logger.error(f'worker raised: {r!r}')
    return results


def append_results_jsonl(path: Path | str, record: SubmissionResult) -> None:
    """Append one SubmissionResult to a JSONL file (creates parents)."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    import json as _json
    with p.open("a", encoding="utf-8") as fh:
        fh.write(_json.dumps(record.to_dict(), ensure_ascii=False) + "\n")

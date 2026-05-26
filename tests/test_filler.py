"""Tests for filler module - logic that does not need a real browser."""
from __future__ import annotations

import pytest

from qbot.filler import human_delay


@pytest.mark.asyncio
async def test_human_delay_runs_within_window() -> None:
    """Sanity check: human_delay should not error and should not block forever."""
    import asyncio
    import time

    start = time.monotonic()
    await asyncio.wait_for(human_delay(0.01, 0.05), timeout=2.0)
    elapsed = time.monotonic() - start
    assert 0 <= elapsed <= 2.0


@pytest.mark.asyncio
async def test_human_delay_default_args() -> None:
    import asyncio
    await asyncio.wait_for(human_delay(), timeout=3.0)


def test_filler_module_exports_expected_symbols() -> None:
    from qbot import filler
    expected = {
        "human_delay",
        "label_container",
        "fill_text",
        "click_radio",
        "click_checkboxes",
        "click_scale",
        "entries_on_page",
        "click_next",
        "has_submit",
        "click_submit",
    }
    assert expected.issubset(set(dir(filler)))

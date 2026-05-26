"""Form interaction helpers - locate, fill, click question controls.

All locators use label text scoping (Google Forms text inputs have empty name attr,
hidden mirror inputs sit outside listitem containers, so label-based scope is the
only reliable strategy across single- and multi-page forms).
"""
from __future__ import annotations

import asyncio
import random
from typing import TYPE_CHECKING

from loguru import logger
from playwright.async_api import TimeoutError as PWTimeoutError

if TYPE_CHECKING:
    from playwright.async_api import Locator, Page


async def human_delay(min_s: float = 0.3, max_s: float = 0.8) -> None:
    """Sleep for a random short interval to avoid pasted-input fingerprint."""
    await asyncio.sleep(random.uniform(min_s, max_s))


def label_container(page: Page, label: str) -> Locator:
    """Locate the listitem div whose heading matches `label` (substring match).

    Google Forms wraps each question in `div[role="listitem"]` containing a
    `div[role="heading"]` element. We escape any embedded double quotes and
    take the first matching listitem.
    """
    safe = label.replace('"', '\\"')
    return page.locator(
        f'div[role="listitem"]:has(div[role="heading"]:has-text("{safe}"))'
    ).first


async def fill_text(page: Page, label: str, value: str) -> bool:
    """Fill a short-answer text question.

    Strategy: scope to listitem by label, click the visible textbox, clear via
    Ctrl+A + Delete (Forms ignores .fill on its custom widgets), then type with
    per-character jitter.
    """
    try:
        container = label_container(page, label)
        if await container.count() == 0:
            logger.error(f"fill_text: no listitem for label '{label}'")
            return False
        await container.scroll_into_view_if_needed()
        await human_delay(0.2, 0.5)
        textbox = container.locator('input[type="text"], textarea').first
        await textbox.click()
        await human_delay(0.1, 0.25)
        await page.keyboard.press("Control+A")
        await page.keyboard.press("Delete")
        await human_delay(0.05, 0.15)
        for ch in value:
            await page.keyboard.type(ch, delay=random.randint(25, 90))
        return True
    except Exception as e:
        logger.error(f"fill_text('{label}') failed: {e}")
        return False


async def click_radio(page: Page, label: str, option: str) -> bool:
    """Tick a radio button option inside a question container."""
    try:
        container = label_container(page, label)
        if await container.count() == 0:
            logger.error(f"click_radio: no listitem for label '{label}'")
            return False
        await container.scroll_into_view_if_needed()
        await human_delay(0.2, 0.5)
        target = container.locator(f'div[role="radio"][aria-label="{option}"]').first
        if await target.count() == 0:
            target = container.locator(f'label:has-text("{option}")').first
        await target.click()
        return True
    except Exception as e:
        logger.error(f"click_radio('{label}', '{option}') failed: {e}")
        return False


async def click_checkboxes(page: Page, label: str, options: list[str]) -> bool:
    """Tick multiple checkbox options inside a question container."""
    try:
        container = label_container(page, label)
        if await container.count() == 0:
            logger.error(f"click_checkboxes: no listitem for label '{label}'")
            return False
        await container.scroll_into_view_if_needed()
        await human_delay(0.2, 0.5)
        for opt in options:
            target = container.locator(f'div[role="checkbox"][aria-label="{opt}"]').first
            if await target.count() == 0:
                target = container.locator(f'label:has-text("{opt}")').first
            await target.click()
            await human_delay(0.15, 0.35)
        return True
    except Exception as e:
        logger.error(f"click_checkboxes('{label}') failed: {e}")
        return False


async def click_scale(page: Page, label: str, value: int) -> bool:
    """Click a Likert scale value (numeric aria-label)."""
    try:
        container = label_container(page, label)
        if await container.count() == 0:
            logger.error(f"click_scale: no listitem for label '{label}'")
            return False
        await container.scroll_into_view_if_needed()
        await human_delay(0.2, 0.5)
        target = container.locator(f'div[role="radio"][aria-label="{value}"]').first
        if await target.count() == 0:
            target = container.locator(f'div[role="radio"][data-value="{value}"]').first
        await target.click()
        return True
    except Exception as e:
        logger.error(f"click_scale('{label}', {value}) failed: {e}")
        return False


async def entries_on_page(page: Page) -> list[str]:
    """Return entry IDs (entry.NNN) of inputs present on the current page.

    Strips '_sentinel' suffix that Google appends to mirror inputs of radio /
    checkbox questions so callers see the canonical entry id.
    """
    raw: list[str] = await page.evaluate(
        """
        () => {
            const ids = new Set();
            document.querySelectorAll('input[name^="entry."]').forEach(el => {
                ids.add(el.name);
            });
            return Array.from(ids);
        }
        """
    )
    cleaned: set[str] = set()
    for name in raw:
        if name.endswith("_sentinel"):
            cleaned.add(name[: -len("_sentinel")])
        else:
            cleaned.add(name)
    return sorted(cleaned)


async def click_next(page: Page, timeout_ms: int = 15000) -> bool:
    """Click the 'Berikutnya' / 'Next' button. Returns True on success."""
    btn = page.locator(
        'div[role="button"]:has-text("Berikutnya"),'
        ' div[role="button"]:has-text("Next")'
    ).first
    try:
        await btn.wait_for(state="visible", timeout=timeout_ms)
    except PWTimeoutError:
        return False
    try:
        await human_delay(0.3, 0.6)
        await btn.click(force=True, timeout=10000)
        await human_delay(0.6, 1.4)
        return True
    except Exception as e:
        logger.error(f"click_next failed: {e}")
        return False


async def has_submit(page: Page) -> bool:
    """Return True if a Kirim/Submit button is currently in the DOM."""
    btn = page.locator(
        'div[role="button"]:has-text("Kirim"),'
        ' div[role="button"]:has-text("Submit")'
    ).first
    return await btn.count() > 0


async def click_submit(page: Page) -> bool:
    """Click the final Kirim/Submit button."""
    btn = page.locator(
        'div[role="button"]:has-text("Kirim"),'
        ' div[role="button"]:has-text("Submit")'
    ).first
    try:
        await btn.wait_for(state="visible", timeout=15000)
        await human_delay(0.4, 1.0)
        await btn.click(force=True, timeout=10000)
        return True
    except Exception as e:
        logger.error(f"click_submit failed: {e}")
        return False

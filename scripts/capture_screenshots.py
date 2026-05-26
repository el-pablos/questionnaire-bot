"""Capture screenshots of both target Google Forms for README documentation.

Saves PNG files into docs/screenshots/ with semantic names.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from camoufox.async_api import AsyncCamoufox

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "screenshots"
OUT.mkdir(parents=True, exist_ok=True)

TARGETS = [
    {
        "name": "form1-umkm-intro",
        "url": "https://docs.google.com/forms/d/e/1FAIpQLSfpcsBC3ui_45KHXvXGb5Rp8W34_98S__e1oBNx-xwcsU3jCw/viewform",
        "advance_clicks": 0,
    },
    {
        "name": "form1-umkm-biodata",
        "url": "https://docs.google.com/forms/d/e/1FAIpQLSfpcsBC3ui_45KHXvXGb5Rp8W34_98S__e1oBNx-xwcsU3jCw/viewform",
        "advance_clicks": 1,
    },
    {
        "name": "form2-jenang-ponorogo",
        "url": "https://docs.google.com/forms/d/e/1FAIpQLScvg_PHJ-54LFezxFk7HVnNMs0espeL9AenRLYf7nsTM9hblQ/viewform",
        "advance_clicks": 0,
    },
]


async def shoot(target: dict) -> Path:
    async with AsyncCamoufox(
        headless=True,
        humanize=False,
        os=["windows"],
        i_know_what_im_doing=True,
    ) as browser:
        page = await browser.new_page() if hasattr(browser, "new_page") else browser.pages[0]
        await page.set_viewport_size({"width": 1280, "height": 1600})
        await page.goto(target["url"], wait_until="domcontentloaded", timeout=45000)
        await asyncio.sleep(3)
        for _ in range(target["advance_clicks"]):
            btn = page.locator('div[role="button"]:has-text("Berikutnya")').first
            if await btn.count() > 0:
                await btn.click(force=True)
                await asyncio.sleep(2)
        out_path = OUT / f"{target['name']}.png"
        await page.screenshot(path=str(out_path), full_page=True)
        return out_path


async def main() -> int:
    for target in TARGETS:
        out = await shoot(target)
        print(f"[OK] {out}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

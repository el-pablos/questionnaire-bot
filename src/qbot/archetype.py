"""Persona archetypes and Likert distribution helpers.

Archetypes simulate realistic survey-respondent populations with mixed
distributions: enthusiasts, positive, neutral, skeptical, mixed/erratic.
Each archetype carries a Gaussian mean+std used to sample 1..7 Likert values.
"""
from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass(frozen=True)
class Archetype:
    """A respondent persona profile with a target Likert distribution."""

    name: str
    weight: int
    mean: float
    std: float


DEFAULT_ARCHETYPES: tuple[Archetype, ...] = (
    Archetype("enthusiast", weight=25, mean=6.0, std=0.6),
    Archetype("positive", weight=30, mean=5.2, std=0.8),
    Archetype("neutral", weight=20, mean=4.0, std=0.9),
    Archetype("skeptical", weight=15, mean=3.2, std=1.0),
    Archetype("mixed", weight=10, mean=4.5, std=1.5),
)


def pick_archetype(
    archetypes: tuple[Archetype, ...] = DEFAULT_ARCHETYPES,
    rng: random.Random | None = None,
) -> Archetype:
    """Pick a weighted-random archetype."""
    r = rng if rng is not None else random
    return r.choices(archetypes, weights=[a.weight for a in archetypes], k=1)[0]


def gauss_likert(
    mean: float,
    std: float,
    scale_min: int = 1,
    scale_max: int = 7,
    rng: random.Random | None = None,
) -> int:
    """Draw a Likert integer from a clipped Gaussian distribution."""
    r = rng if rng is not None else random
    raw = r.gauss(mean, std)
    val = round(raw)
    return max(scale_min, min(scale_max, val))


def likert_block(
    archetype: Archetype,
    n: int,
    scale_min: int = 1,
    scale_max: int = 7,
    drift: float = 0.0,
    rng: random.Random | None = None,
) -> list[int]:
    """Generate `n` correlated Likert values around archetype mean (with drift)."""
    return [
        gauss_likert(archetype.mean + drift, archetype.std, scale_min, scale_max, rng)
        for _ in range(n)
    ]

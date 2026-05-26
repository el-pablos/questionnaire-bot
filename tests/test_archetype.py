"""Tests for archetype distributions and Likert sampling."""
from __future__ import annotations

import random
import statistics

import pytest

from qbot.archetype import (
    DEFAULT_ARCHETYPES,
    Archetype,
    gauss_likert,
    likert_block,
    pick_archetype,
)


def test_default_archetypes_have_unique_names() -> None:
    names = [a.name for a in DEFAULT_ARCHETYPES]
    assert len(names) == len(set(names))


def test_default_archetypes_have_positive_weights() -> None:
    for a in DEFAULT_ARCHETYPES:
        assert a.weight > 0
        assert 1.0 <= a.mean <= 7.0
        assert a.std > 0


def test_pick_archetype_returns_one_of_input() -> None:
    rng = random.Random(0)
    a = pick_archetype(DEFAULT_ARCHETYPES, rng=rng)
    assert a in DEFAULT_ARCHETYPES


def test_pick_archetype_distribution_respects_weights() -> None:
    rng = random.Random(123)
    archetypes = (
        Archetype("a", weight=90, mean=5.0, std=0.5),
        Archetype("b", weight=10, mean=5.0, std=0.5),
    )
    counts = {"a": 0, "b": 0}
    for _ in range(2000):
        counts[pick_archetype(archetypes, rng=rng).name] += 1
    # Should be roughly 90/10 split, allow generous slack.
    assert counts["a"] > counts["b"] * 5


def test_gauss_likert_clipped_to_scale() -> None:
    rng = random.Random(0)
    for _ in range(500):
        v = gauss_likert(mean=10.0, std=5.0, scale_min=1, scale_max=7, rng=rng)
        assert 1 <= v <= 7


def test_gauss_likert_custom_scale() -> None:
    rng = random.Random(0)
    for _ in range(200):
        v = gauss_likert(mean=3.0, std=1.0, scale_min=1, scale_max=5, rng=rng)
        assert 1 <= v <= 5


def test_likert_block_length() -> None:
    rng = random.Random(1)
    block = likert_block(DEFAULT_ARCHETYPES[0], n=4, rng=rng)
    assert len(block) == 4


def test_likert_block_mean_correlates_with_archetype() -> None:
    rng = random.Random(7)
    enthusiast = next(a for a in DEFAULT_ARCHETYPES if a.name == "enthusiast")
    skeptical = next(a for a in DEFAULT_ARCHETYPES if a.name == "skeptical")
    enth_block = likert_block(enthusiast, n=200, rng=rng)
    skep_block = likert_block(skeptical, n=200, rng=rng)
    assert statistics.mean(enth_block) > statistics.mean(skep_block)


def test_likert_block_drift_shifts_mean() -> None:
    rng = random.Random(7)
    arch = Archetype("test", weight=1, mean=4.0, std=0.5)
    no_drift = likert_block(arch, n=300, drift=0.0, rng=rng)
    pos_drift = likert_block(arch, n=300, drift=2.0, rng=rng)
    assert statistics.mean(pos_drift) > statistics.mean(no_drift)


def test_likert_block_seed_determinism() -> None:
    rng1 = random.Random(42)
    rng2 = random.Random(42)
    a = DEFAULT_ARCHETYPES[0]
    assert likert_block(a, n=10, rng=rng1) == likert_block(a, n=10, rng=rng2)

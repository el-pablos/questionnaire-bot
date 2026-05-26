"""Tests for persona generator (deterministic with seed)."""
from __future__ import annotations

import random

import pytest
from faker import Faker

from qbot.archetype import DEFAULT_ARCHETYPES, Archetype
from qbot.persona import (
    _is_age_field,
    _is_duration_business,
    _is_duration_tech,
    _is_education_field,
    _is_gender_field,
    _is_name_field,
    _is_yes_no_field,
    _resolve_checkbox_value,
    _resolve_radio_value,
    _resolve_text_value,
    gen_age_str,
    gen_lama_teknologi,
    gen_lama_usaha,
    gen_name,
    generate_dataset,
    generate_persona,
)
from qbot.schema import FormField, FormSchema, load_schema


# ---------------------------------------------------------------------------
# Heuristic detectors
# ---------------------------------------------------------------------------

def test_is_name_field() -> None:
    assert _is_name_field("nama_lengkap", "Nama Lengkap")
    assert _is_name_field("name", "Your Name")
    assert not _is_name_field("usia", "Usia")


def test_is_gender_field() -> None:
    assert _is_gender_field("jenis_kelamin", "Jenis Kelamin")
    assert _is_gender_field("gender", "Gender")
    assert not _is_gender_field("usia", "Usia")


def test_is_age_field() -> None:
    assert _is_age_field("usia", "Usia")
    assert _is_age_field("age", "Your Age")
    assert _is_age_field("umur", "Umur")
    assert not _is_age_field("nama", "Nama")


def test_is_duration_business() -> None:
    assert _is_duration_business("lama_usaha", "Lama Usaha")
    assert _is_duration_business("usaha_berdiri", "Usaha berdiri sejak")


def test_is_duration_tech() -> None:
    assert _is_duration_tech("lama_teknologi", "Lama Menggunakan Teknologi Digital")


def test_is_education_field() -> None:
    assert _is_education_field("pendidikan", "Pendidikan")
    assert _is_education_field("education", "Education Level")


def test_is_yes_no_field() -> None:
    f = FormField(key="x", label="X", entry="entry.1", type="radio", options=("Ya", "Tidak"))
    assert _is_yes_no_field(f)
    f2 = FormField(key="x", label="X", entry="entry.1", type="radio", options=("A", "B"))
    assert not _is_yes_no_field(f2)


# ---------------------------------------------------------------------------
# Generators
# ---------------------------------------------------------------------------

def test_gen_name_returns_string() -> None:
    fake = Faker("id_ID")
    Faker.seed(0)
    n = gen_name(fake)
    assert isinstance(n, str) and len(n) > 0


def test_gen_name_gendered() -> None:
    fake = Faker("id_ID")
    Faker.seed(0)
    n_male = gen_name(fake, "Laki-laki")
    n_female = gen_name(fake, "Perempuan")
    assert isinstance(n_male, str) and isinstance(n_female, str)


def test_gen_age_str_in_range() -> None:
    rng = random.Random(0)
    for _ in range(50):
        v = int(gen_age_str(rng))
        assert 20 <= v <= 55


def test_gen_lama_usaha_format() -> None:
    rng = random.Random(0)
    for _ in range(50):
        s = gen_lama_usaha(rng)
        assert s.endswith("tahun") or s.endswith("bulan")


def test_gen_lama_teknologi_consistent_with_usaha() -> None:
    rng = random.Random(0)
    s = gen_lama_teknologi("5 tahun", rng)
    assert s.endswith("tahun")
    s2 = gen_lama_teknologi("8 bulan", rng)
    assert s2.endswith("bulan")


# ---------------------------------------------------------------------------
# Resolvers
# ---------------------------------------------------------------------------

def test_resolve_radio_value_yes_no_skewed_to_ya() -> None:
    rng = random.Random(7)
    f = FormField(key="x", label="X", entry="entry.1", type="radio", options=("Ya", "Tidak"))
    counts = {"Ya": 0, "Tidak": 0}
    for _ in range(500):
        counts[_resolve_radio_value(f, rng)] += 1
    assert counts["Ya"] > counts["Tidak"]


def test_resolve_radio_value_education_picks_smk_or_sarjana() -> None:
    rng = random.Random(7)
    f = FormField(
        key="pendidikan", label="Pendidikan", entry="entry.1", type="radio",
        options=("SD", "SMP", "SMA", "Diploma", "Sarjana (S1)", "Magister (S2)"),
    )
    picks = [_resolve_radio_value(f, rng) for _ in range(200)]
    common = max(set(picks), key=picks.count)
    assert common in {"SMA", "Sarjana (S1)", "Diploma"}


def test_resolve_checkbox_value_picks_at_least_one() -> None:
    rng = random.Random(0)
    f = FormField(
        key="m", label="M", entry="entry.1", type="checkbox",
        options=("WhatsApp", "Tiktok", "Instagram/Facebook"),
    )
    for _ in range(50):
        v = _resolve_checkbox_value(f, rng)
        assert len(v) >= 1
        for o in v:
            assert o in f.options


def test_resolve_checkbox_value_prefers_whatsapp() -> None:
    rng = random.Random(7)
    f = FormField(
        key="m", label="M", entry="entry.1", type="checkbox",
        options=("WhatsApp", "Tiktok", "Instagram/Facebook"),
    )
    wa_count = 0
    for _ in range(200):
        v = _resolve_checkbox_value(f, rng)
        if "WhatsApp" in v:
            wa_count += 1
    assert wa_count > 150  # ~95% expected


def test_resolve_text_value_uses_field_heuristic() -> None:
    rng = random.Random(0)
    fake = Faker("id_ID")
    Faker.seed(0)
    state: dict = {}
    f_age = FormField(key="usia", label="Usia", entry="entry.1", type="text")
    age_str = _resolve_text_value(f_age, fake, rng, state)
    assert int(age_str) >= 20

    f_lu = FormField(key="lama_usaha", label="Lama Usaha", entry="entry.2", type="text")
    lu = _resolve_text_value(f_lu, fake, rng, state)
    assert lu.endswith("tahun") or lu.endswith("bulan")
    assert state["_lama_usaha"] == lu


# ---------------------------------------------------------------------------
# generate_persona / generate_dataset
# ---------------------------------------------------------------------------

def _tiny_schema() -> FormSchema:
    fields = (
        FormField(key="nama", label="Nama", entry="entry.1", type="text"),
        FormField(key="jenis_kelamin", label="Jenis Kelamin", entry="entry.2",
                  type="radio", options=("Laki-laki", "Perempuan")),
        FormField(key="usia", label="Usia", entry="entry.3", type="text"),
        FormField(key="media", label="Media Digital", entry="entry.4",
                  type="checkbox", options=("WhatsApp", "Tiktok")),
        FormField(key="q1", label="Saya senang", entry="entry.5", type="scale"),
    )
    return FormSchema(id="tiny", title="t", description="", form_url="u", form_response_url="r", fields=fields)


def test_generate_persona_includes_all_fields() -> None:
    schema = _tiny_schema()
    fake = Faker("id_ID")
    Faker.seed(0)
    rng = random.Random(0)
    p = generate_persona(1, schema, fake, rng)
    assert p["id"] == 1
    assert "biodata" in p
    assert "answers" in p
    for k in ("nama", "jenis_kelamin", "usia", "media"):
        assert k in p["biodata"]
    assert "q1" in p["answers"]
    assert 1 <= p["answers"]["q1"] <= 7


def test_generate_dataset_count_and_uniqueness() -> None:
    schema = _tiny_schema()
    ds = generate_dataset(schema, count=50, seed=42)
    assert len(ds) == 50
    names = [p["biodata"]["nama"] for p in ds]
    # 50 unique names is plausible from Faker id_ID, allow tiny duplicate tolerance.
    assert len(set(names)) >= 45


def test_generate_dataset_seed_determinism() -> None:
    schema = _tiny_schema()
    a = generate_dataset(schema, count=20, seed=99)
    b = generate_dataset(schema, count=20, seed=99)
    assert a == b


def test_generate_dataset_real_umkm_schema() -> None:
    from pathlib import Path
    p = Path("schemas/umkm-transformasi-digital.json")
    if not p.exists():
        pytest.skip(f"{p} not present")
    schema = load_schema(p)
    ds = generate_dataset(schema, count=10, seed=1)
    assert len(ds) == 10
    for persona in ds:
        bio = persona["biodata"]
        assert "nama_lengkap" in bio
        assert "pendidikan" in bio
        assert bio["pendidikan"] in ("SD", "SMP", "SMA", "Sarjana (S1)")
        ans = persona["answers"]
        for k, v in ans.items():
            assert 1 <= v <= 7


def test_generate_dataset_real_jenang_schema() -> None:
    from pathlib import Path
    p = Path("schemas/umkm-jenang-ponorogo.json")
    if not p.exists():
        pytest.skip(f"{p} not present")
    schema = load_schema(p)
    ds = generate_dataset(schema, count=10, seed=2)
    assert len(ds) == 10
    for persona in ds:
        bio = persona["biodata"]
        assert bio["jenis_kelamin"] in ("Laki-laki", "Perempuan")
        assert bio["pakai_digital"] in ("Ya", "Tidak")

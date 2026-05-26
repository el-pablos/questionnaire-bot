"""Generate realistic Indonesian persona datasets for any form schema.

Output structure:
{
  "id": int,
  "archetype": str,
  "biodata": { field_key -> value, ... },     # text/radio/checkbox values
  "answers": { field_key -> value, ... },     # scale (Likert) values
}

The generator inspects a FormSchema and produces values for every field:
  - text fields use field-specific generators (name/age/duration/...) or fall back
    to short fake text, picked from heuristics on the field key.
  - radio fields pick from declared options (weighted toward sensible defaults).
  - checkbox fields pick a 1..N subset of declared options.
  - scale fields draw from a Gaussian centered on the persona archetype.
"""
from __future__ import annotations

import argparse
import json
import random
from collections.abc import Callable
from pathlib import Path
from typing import Any

from faker import Faker

from .archetype import DEFAULT_ARCHETYPES, Archetype, likert_block, pick_archetype
from .schema import FormField, FormSchema, load_schema


# ---------------------------------------------------------------------------
# Field-key heuristics for biodata text fields (Indonesian-aware).
# ---------------------------------------------------------------------------

def _is_name_field(key: str, label: str) -> bool:
    s = (key + " " + label).lower()
    return any(w in s for w in ("nama", "name"))


def _is_gender_field(key: str, label: str) -> bool:
    s = (key + " " + label).lower()
    return "kelamin" in s or "gender" in s


def _is_age_field(key: str, label: str) -> bool:
    s = (key + " " + label).lower()
    return "usia" in s or "umur" in s or "age" in s


def _is_duration_business(key: str, label: str) -> bool:
    s = (key + " " + label).lower()
    return ("lama" in s and "usaha" in s) or "lama_usaha" in key.lower() or "berdiri" in s


def _is_duration_tech(key: str, label: str) -> bool:
    s = (key + " " + label).lower()
    return "lama" in s and ("teknologi" in s or "digital" in s or "tech" in s)


def _is_education_field(key: str, label: str) -> bool:
    s = (key + " " + label).lower()
    return "pendidikan" in s or "education" in s


def _is_position_field(key: str, label: str) -> bool:
    s = (key + " " + label).lower()
    return "posisi" in s or "jabatan" in s or "role" in s


def _is_business_type_field(key: str, label: str) -> bool:
    s = (key + " " + label).lower()
    return "jenis usaha" in s or "tipe usaha" in s or "kategori usaha" in s


def _is_yes_no_field(field: FormField) -> bool:
    if field.type != "radio":
        return False
    opts_lower = [o.lower().strip() for o in field.options]
    return set(opts_lower) <= {"ya", "tidak", "yes", "no"}


# ---------------------------------------------------------------------------
# Value generators (no schema knowledge needed).
# ---------------------------------------------------------------------------

def gen_name(fake: Faker, gender: str | None = None) -> str:
    if gender and gender.lower().startswith("perempuan"):
        return fake.name_female()
    if gender and gender.lower().startswith("laki"):
        return fake.name_male()
    return fake.name()


def gen_age_str(rng: random.Random) -> str:
    age = rng.choices(
        population=[
            rng.randint(20, 24),
            rng.randint(25, 34),
            rng.randint(35, 44),
            rng.randint(45, 55),
        ],
        weights=[15, 40, 30, 15],
        k=1,
    )[0]
    return str(age)


def gen_lama_usaha(rng: random.Random) -> str:
    bucket = rng.choices(
        ["months", "1y", "2y", "3y", "5y", "10y"],
        weights=[10, 20, 25, 20, 15, 10],
        k=1,
    )[0]
    if bucket == "months":
        return f"{rng.randint(6, 11)} bulan"
    if bucket == "1y":
        return "1 tahun"
    if bucket == "2y":
        return f"{rng.randint(2, 3)} tahun"
    if bucket == "3y":
        return f"{rng.randint(3, 4)} tahun"
    if bucket == "5y":
        return f"{rng.randint(5, 7)} tahun"
    return f"{rng.randint(8, 15)} tahun"


def gen_lama_teknologi(lama_usaha: str, rng: random.Random) -> str:
    parts = lama_usaha.split()
    if "bulan" in lama_usaha:
        return f"{rng.randint(3, 6)} bulan"
    try:
        years = int(parts[0])
    except (IndexError, ValueError):
        years = 1
    tech_years = max(1, rng.randint(1, max(1, years)))
    return f"{tech_years} tahun"


# ---------------------------------------------------------------------------
# Field value resolver - decides what value to give every schema field.
# ---------------------------------------------------------------------------

def _resolve_radio_value(field: FormField, rng: random.Random) -> str:
    """Pick one option for a radio field."""
    options = list(field.options)
    if not options:
        return ""
    if _is_yes_no_field(field):
        return rng.choices(options, weights=[8 if o.lower().startswith("ya") else 2 for o in options], k=1)[0]
    if _is_education_field(field.key, field.label):
        weights: list[int] = []
        for o in options:
            ol = o.lower()
            if "sma" in ol or "smk" in ol:
                weights.append(50)
            elif "sarjana" in ol or "s1" in ol or "diploma" in ol:
                weights.append(30)
            elif "smp" in ol:
                weights.append(12)
            elif "sd" in ol:
                weights.append(6)
            elif "magister" in ol or "s2" in ol:
                weights.append(2)
            else:
                weights.append(1)
        return rng.choices(options, weights=weights, k=1)[0]
    return rng.choice(options)


def _resolve_checkbox_value(field: FormField, rng: random.Random) -> list[str]:
    """Pick a 1..N subset of checkbox options. WhatsApp prioritised when present."""
    options = list(field.options)
    if not options:
        return []
    selections: list[str] = []
    if any("whatsapp" in o.lower() for o in options) and rng.random() < 0.95:
        wa = next(o for o in options if "whatsapp" in o.lower())
        selections.append(wa)
    extras = [o for o in options if o not in selections]
    n_extra = rng.choices([0, 1, 2, 3], weights=[15, 35, 35, 15], k=1)[0]
    selections.extend(rng.sample(extras, min(n_extra, len(extras))))
    if not selections:
        selections.append(rng.choice(options))
    return selections


def _resolve_text_value(
    field: FormField,
    fake: Faker,
    rng: random.Random,
    persona_state: dict[str, Any],
) -> str:
    """Pick a value for a text field using key/label heuristics."""
    if _is_name_field(field.key, field.label):
        gender = persona_state.get("_gender")
        return gen_name(fake, gender)
    if _is_age_field(field.key, field.label):
        return gen_age_str(rng)
    if _is_duration_business(field.key, field.label):
        v = gen_lama_usaha(rng)
        persona_state["_lama_usaha"] = v
        return v
    if _is_duration_tech(field.key, field.label):
        return gen_lama_teknologi(persona_state.get("_lama_usaha", "1 tahun"), rng)
    if _is_gender_field(field.key, field.label):
        return rng.choice(["Laki-laki", "Perempuan"])
    return fake.sentence(nb_words=3).rstrip(".")


# ---------------------------------------------------------------------------
# Top-level dataset generator.
# ---------------------------------------------------------------------------

def generate_persona(
    idx: int,
    schema: FormSchema,
    fake: Faker,
    rng: random.Random,
    archetypes: tuple[Archetype, ...] = DEFAULT_ARCHETYPES,
) -> dict[str, Any]:
    """Generate a single persona for `schema`."""
    archetype = pick_archetype(archetypes, rng)
    biodata: dict[str, Any] = {}
    answers: dict[str, Any] = {}
    state: dict[str, Any] = {}

    # 1) Decide gender first if a gender field exists - other text fields use it.
    for f in schema.fields:
        if _is_gender_field(f.key, f.label):
            if f.type == "radio" and f.options:
                state["_gender"] = _resolve_radio_value(f, rng)
            else:
                state["_gender"] = rng.choice(["Laki-laki", "Perempuan"])
            break

    # 2) Walk every field and produce a value.
    for f in schema.fields:
        if f.type == "text":
            biodata[f.key] = _resolve_text_value(f, fake, rng, state)
        elif f.type == "radio":
            if "_gender" in state and _is_gender_field(f.key, f.label):
                biodata[f.key] = state["_gender"]
            else:
                biodata[f.key] = _resolve_radio_value(f, rng)
        elif f.type == "checkbox":
            biodata[f.key] = _resolve_checkbox_value(f, rng)
        elif f.type == "scale":
            drift = rng.uniform(-0.4, 0.3)
            answers[f.key] = likert_block(
                archetype, n=1, scale_min=f.scale_min, scale_max=f.scale_max,
                drift=drift, rng=rng,
            )[0]

    return {
        "id": idx,
        "archetype": archetype.name,
        "schema_id": schema.id,
        "biodata": biodata,
        "answers": answers,
    }


def generate_dataset(
    schema: FormSchema,
    count: int,
    seed: int | None = None,
    fake_locale: str = "id_ID",
    archetypes: tuple[Archetype, ...] = DEFAULT_ARCHETYPES,
) -> list[dict[str, Any]]:
    """Generate `count` personas. Deterministic when `seed` is set."""
    rng = random.Random(seed)
    fake = Faker(fake_locale)
    if seed is not None:
        Faker.seed(seed)
    return [generate_persona(i + 1, schema, fake, rng, archetypes) for i in range(count)]


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Generate persona dataset for a form schema.")
    p.add_argument("--schema", required=True, help="Path to form schema JSON/YAML")
    p.add_argument("--count", type=int, default=10, help="Number of personas")
    p.add_argument("--out", required=True, help="Output JSON path")
    p.add_argument("--seed", type=int, default=None, help="Optional RNG seed")
    p.add_argument("--locale", default="id_ID", help="Faker locale (default id_ID)")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    schema = load_schema(args.schema)
    dataset = generate_dataset(schema, args.count, args.seed, args.locale)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(dataset, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[OK] Generated {len(dataset)} personas for schema '{schema.id}' -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

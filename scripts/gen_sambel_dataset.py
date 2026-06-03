"""Generate 150-persona dataset for the Sambel Pecel Ponorogo form.

Customizations over the default generator (per researcher request):
  - "jeneng e seng rodok tuwek ae" -> names + age skew toward MATURE/OLDER
    respondents (UMKM owners tend to be 31-50+). Age brackets weighted to
    older buckets; names use Faker id_ID which already yields honorifics
    (H., Hj., Ir., Drs., etc.) that read as established business owners.
  - Realistic Likert archetype mix (UMKM owners lean positive about their
    own business but with honest neutral/skeptical tails).
  - Cross-field consistency: if pakai_digital == "Tidak", the Kematangan
    Digital answers (kd_*) are pulled DOWN so the data is internally coherent.
"""
from __future__ import annotations

import json
import random
from pathlib import Path

from faker import Faker

from qbot.archetype import DEFAULT_ARCHETYPES, likert_block, pick_archetype
from qbot.schema import load_schema

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "schemas" / "umkm-sambel-pecel-ponorogo.json"
OUT = ROOT / "data" / "sambel_pecel_150.json"
COUNT = 150
SEED = 20260206

# Age brackets weighted toward OLDER respondents (mature business owners).
AGE_WEIGHTED = [
    ("< 20 tahun", 1),
    ("20–30 tahun", 12),
    ("31–40 tahun", 34),
    ("41–50 tahun", 35),
    (">50 tahun", 18),
]

# Education: realistic for UMKM owners in a regency (kabupaten).
EDU_WEIGHTED = [
    ("SD/Sederajat", 14),
    ("SMP/Sederajat", 22),
    ("SMA/Sederajat", 40),
    ("Diploma", 9),
    ("Sarjana", 15),
]

LAMA_WEIGHTED = [
    ("< 1 tahun", 6),
    ("1–3 tahun", 20),
    ("4–6 tahun", 30),
    ("7-10 tahun", 26),
    (">10 tahun", 18),
]

JENIS_USAHA_WEIGHTED = [
    ("Produksi Sambal Pecel", 35),
    ("Penjual Sambal Pecel", 30),
    ("Produksi Dan Penjual Sambal Pecel", 35),
]


def weighted_pick(rng: random.Random, pairs: list[tuple[str, int]]) -> str:
    opts = [p[0] for p in pairs]
    wts = [p[1] for p in pairs]
    return rng.choices(opts, weights=wts, k=1)[0]


def mature_name(fake: Faker, gender: str, rng: random.Random) -> str:
    """Return a name that reads as an established/older business owner.

    Faker id_ID already emits honorifics. We additionally bias toward
    producing a prefixed/honorific name so the cohort skews 'tuwek' (older).
    """
    for _ in range(6):
        name = fake.name_male() if gender == "Laki-Laki" else fake.name_female()
        # Prefer names that carry an honorific/degree (reads more mature),
        # but don't force it every time to stay natural.
        if any(tok in name for tok in ("H.", "Hj.", "Ir.", "Drs.", "Dr.", "S.E", "S.Pd", "M.", "Hi.")):
            return name
    # Fallback: plain name is fine too.
    return fake.name_male() if gender == "Laki-Laki" else fake.name_female()


def main() -> int:
    schema = load_schema(SCHEMA)
    rng = random.Random(SEED)
    fake = Faker("id_ID")
    Faker.seed(SEED)

    personas: list[dict] = []
    for i in range(1, COUNT + 1):
        archetype = pick_archetype(DEFAULT_ARCHETYPES, rng)
        gender = rng.choice(["Laki-Laki", "Perempuan"])
        pakai_digital = rng.choices(["Iya", "Tidak"], weights=[72, 28], k=1)[0]

        biodata = {
            "nama": mature_name(fake, gender, rng),
            "jenis_usaha": weighted_pick(rng, JENIS_USAHA_WEIGHTED),
            "jenis_kelamin": gender,
            "usia": weighted_pick(rng, AGE_WEIGHTED),
            "pendidikan": weighted_pick(rng, EDU_WEIGHTED),
            "lama_usaha": weighted_pick(rng, LAMA_WEIGHTED),
            "pakai_digital": pakai_digital,
        }

        answers: dict[str, int] = {}
        # Per-section drift so answers within a section correlate, but
        # sections differ a little (more natural than a flat line).
        section_drift: dict[str, float] = {}
        for f in schema.scale_fields:
            sec = f.section or "_"
            if sec not in section_drift:
                section_drift[sec] = rng.uniform(-0.35, 0.35)
            drift = section_drift[sec]
            # Coherence: non-digital businesses score digital maturity lower.
            if sec == "kematangan_digital" and pakai_digital == "Tidak":
                drift -= 2.3
            val = likert_block(
                archetype, n=1,
                scale_min=f.scale_min, scale_max=f.scale_max,
                drift=drift, rng=rng,
            )[0]
            answers[f.key] = val

        personas.append({
            "id": i,
            "archetype": archetype.name,
            "schema_id": schema.id,
            "biodata": biodata,
            "answers": answers,
        })

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(personas, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[OK] Generated {len(personas)} personas -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

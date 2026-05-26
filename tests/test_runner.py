"""Tests for runner.build_value_map and SubmissionResult."""
from __future__ import annotations

from qbot.runner import SubmissionResult, build_value_map
from qbot.schema import FormField, FormSchema


def _schema() -> FormSchema:
    fields = (
        FormField(key="nama", label="Nama", entry="entry.10", type="text"),
        FormField(key="kelamin", label="Jenis Kelamin", entry="entry.20",
                  type="radio", options=("Laki-laki", "Perempuan")),
        FormField(key="media", label="Media", entry="entry.30",
                  type="checkbox", options=("WA", "IG")),
        FormField(key="q1", label="Saya senang", entry="entry.40", type="scale"),
    )
    return FormSchema(
        id="t", title="t", description="", form_url="u", form_response_url="r", fields=fields,
    )


def test_build_value_map_full_persona() -> None:
    schema = _schema()
    persona = {
        "id": 1,
        "archetype": "neutral",
        "biodata": {"nama": "Andi", "kelamin": "Laki-laki", "media": ["WA"]},
        "answers": {"q1": 5},
    }
    vmap = build_value_map(schema, persona)
    assert set(vmap.keys()) == {"entry.10", "entry.20", "entry.30", "entry.40"}
    assert vmap["entry.10"] == {"type": "text", "label": "Nama", "value": "Andi"}
    assert vmap["entry.20"]["type"] == "radio"
    assert vmap["entry.30"]["value"] == ["WA"]
    assert vmap["entry.40"] == {"type": "scale", "label": "Saya senang", "value": 5}


def test_build_value_map_skips_missing_values() -> None:
    schema = _schema()
    persona = {"id": 1, "archetype": "x", "biodata": {"nama": "A"}, "answers": {}}
    vmap = build_value_map(schema, persona)
    assert "entry.10" in vmap
    assert "entry.20" not in vmap
    assert "entry.40" not in vmap


def test_submission_result_to_dict_roundtrip() -> None:
    r = SubmissionResult(
        timestamp="2026-01-01T00:00:00",
        schema_id="x",
        persona_id=1,
        archetype="neutral",
        nama="A",
        status="success",
    )
    d = r.to_dict()
    assert d["status"] == "success"
    assert d["schema_id"] == "x"
    assert d["error"] is None
    assert d["duration_seconds"] == 0.0


def test_submission_result_status_values() -> None:
    r = SubmissionResult(
        timestamp="t", schema_id="s", persona_id=1, archetype="a",
        nama="n", status="fill_failed", error="oops", duration_seconds=12.5,
    )
    assert r.status == "fill_failed"
    assert r.error == "oops"
    assert r.duration_seconds == 12.5

"""Tests for schema loading and validation."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from qbot.schema import FormField, FormSchema, list_schemas, load_schema


def test_form_field_validates_entry_prefix() -> None:
    with pytest.raises(ValueError, match="entry"):
        FormField(key="x", label="X", entry="bad", type="text")


def test_form_field_radio_requires_options() -> None:
    with pytest.raises(ValueError, match="options"):
        FormField(key="x", label="X", entry="entry.1", type="radio")


def test_form_field_scale_validates_range() -> None:
    with pytest.raises(ValueError, match="scale_min"):
        FormField(key="x", label="X", entry="entry.1", type="scale", scale_min=7, scale_max=1)


def test_form_field_text_ok() -> None:
    f = FormField(key="x", label="X", entry="entry.1", type="text")
    assert f.entry == "entry.1"
    assert f.required is True
    assert f.options == ()


def test_form_schema_rejects_duplicate_keys() -> None:
    fields = (
        FormField(key="dup", label="A", entry="entry.1", type="text"),
        FormField(key="dup", label="B", entry="entry.2", type="text"),
    )
    with pytest.raises(ValueError, match="Duplicate field keys"):
        FormSchema(id="x", title="t", description="", form_url="u", form_response_url="r", fields=fields)


def test_form_schema_rejects_duplicate_entries() -> None:
    fields = (
        FormField(key="a", label="A", entry="entry.1", type="text"),
        FormField(key="b", label="B", entry="entry.1", type="text"),
    )
    with pytest.raises(ValueError, match="Duplicate entry"):
        FormSchema(id="x", title="t", description="", form_url="u", form_response_url="r", fields=fields)


def test_schema_filter_helpers() -> None:
    fields = (
        FormField(key="t", label="T", entry="entry.1", type="text"),
        FormField(key="r", label="R", entry="entry.2", type="radio", options=("A", "B")),
        FormField(key="c", label="C", entry="entry.3", type="checkbox", options=("X", "Y")),
        FormField(key="s", label="S", entry="entry.4", type="scale"),
    )
    schema = FormSchema(id="x", title="t", description="", form_url="u", form_response_url="r", fields=fields)
    assert len(schema.text_fields) == 1
    assert len(schema.radio_fields) == 1
    assert len(schema.checkbox_fields) == 1
    assert len(schema.scale_fields) == 1


def test_schema_by_key_lookup() -> None:
    f = FormField(key="t", label="T", entry="entry.1", type="text")
    schema = FormSchema(id="x", title="t", description="", form_url="u", form_response_url="r", fields=(f,))
    assert schema.by_key("t").entry == "entry.1"
    with pytest.raises(KeyError):
        schema.by_key("missing")


def test_schema_by_entry_lookup() -> None:
    f = FormField(key="t", label="T", entry="entry.42", type="text")
    schema = FormSchema(id="x", title="t", description="", form_url="u", form_response_url="r", fields=(f,))
    assert schema.by_entry("entry.42") is f
    assert schema.by_entry("entry.unknown") is None


def test_load_schema_json(tmp_path: Path) -> None:
    raw = {
        "id": "demo",
        "title": "Demo",
        "description": "demo schema",
        "form_url": "https://example/viewform",
        "form_response_url": "https://example/formResponse",
        "fields": [
            {"key": "name", "label": "Name", "entry": "entry.1", "type": "text"},
            {"key": "agree", "label": "Agree", "entry": "entry.2", "type": "scale"},
        ],
    }
    p = tmp_path / "demo.json"
    p.write_text(json.dumps(raw), encoding="utf-8")
    schema = load_schema(p)
    assert schema.id == "demo"
    assert len(schema.fields) == 2
    assert schema.fields[0].key == "name"


def test_list_schemas_directory(tmp_path: Path) -> None:
    (tmp_path / "a.json").write_text("{}", encoding="utf-8")
    (tmp_path / "b.yaml").write_text("{}", encoding="utf-8")
    (tmp_path / "ignore.txt").write_text("nope", encoding="utf-8")
    paths = list_schemas(tmp_path)
    names = [p.name for p in paths]
    assert "a.json" in names
    assert "b.yaml" in names
    assert "ignore.txt" not in names


def test_list_schemas_missing_dir_returns_empty() -> None:
    assert list_schemas("definitely-not-a-real-path-9999") == []


def test_real_umkm_schema_loads() -> None:
    p = Path("schemas/umkm-transformasi-digital.json")
    if not p.exists():
        pytest.skip(f"{p} not present")
    schema = load_schema(p)
    assert schema.id == "umkm-transformasi-digital"
    assert len(schema.fields) == 23
    assert any(f.type == "scale" for f in schema.fields)
    assert any(f.type == "checkbox" for f in schema.fields)


def test_real_jenang_schema_loads() -> None:
    p = Path("schemas/umkm-jenang-ponorogo.json")
    if not p.exists():
        pytest.skip(f"{p} not present")
    schema = load_schema(p)
    assert schema.id == "umkm-jenang-ponorogo"
    assert len(schema.fields) == 28
    radio_count = sum(1 for f in schema.fields if f.type == "radio")
    scale_count = sum(1 for f in schema.fields if f.type == "scale")
    assert radio_count == 7
    assert scale_count == 20

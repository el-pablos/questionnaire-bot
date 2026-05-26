"""Schema model for Google Forms — describes the structure of any target form."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import json
import yaml


FieldType = Literal["text", "radio", "checkbox", "scale"]


@dataclass(frozen=True)
class FormField:
    """A single question on a form."""

    key: str
    label: str
    entry: str
    type: FieldType
    required: bool = True
    options: tuple[str, ...] = ()
    section: str | None = None
    scale_min: int = 1
    scale_max: int = 7

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        if not self.entry.startswith("entry."):
            raise ValueError(f"Field '{self.key}': entry must start with 'entry.'")
        if self.type in ("radio", "checkbox") and not self.options:
            raise ValueError(f"Field '{self.key}': {self.type} requires options")
        if self.type == "scale" and self.scale_min >= self.scale_max:
            raise ValueError(f"Field '{self.key}': scale_min must be < scale_max")


@dataclass(frozen=True)
class FormSchema:
    """Complete description of a Google Form."""

    id: str
    title: str
    description: str
    form_url: str
    form_response_url: str
    locale: str = "id-ID"
    fields: tuple[FormField, ...] = field(default_factory=tuple)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for f in self.fields:
            f.validate()
        keys = [f.key for f in self.fields]
        if len(keys) != len(set(keys)):
            raise ValueError(f"Duplicate field keys in schema '{self.id}'")
        entries = [f.entry for f in self.fields]
        if len(entries) != len(set(entries)):
            raise ValueError(f"Duplicate entry IDs in schema '{self.id}'")

    @property
    def text_fields(self) -> tuple[FormField, ...]:
        return tuple(f for f in self.fields if f.type == "text")

    @property
    def radio_fields(self) -> tuple[FormField, ...]:
        return tuple(f for f in self.fields if f.type == "radio")

    @property
    def checkbox_fields(self) -> tuple[FormField, ...]:
        return tuple(f for f in self.fields if f.type == "checkbox")

    @property
    def scale_fields(self) -> tuple[FormField, ...]:
        return tuple(f for f in self.fields if f.type == "scale")

    def by_key(self, key: str) -> FormField:
        for f in self.fields:
            if f.key == key:
                return f
        raise KeyError(f"Field key '{key}' not found in schema '{self.id}'")

    def by_entry(self, entry: str) -> FormField | None:
        for f in self.fields:
            if f.entry == entry:
                return f
        return None


def _coerce_field(raw: dict[str, Any]) -> FormField:
    options_raw = raw.get("options") or ()
    options: tuple[str, ...] = tuple(str(o) for o in options_raw)
    return FormField(
        key=str(raw["key"]),
        label=str(raw["label"]),
        entry=str(raw["entry"]),
        type=raw["type"],
        required=bool(raw.get("required", True)),
        options=options,
        section=raw.get("section"),
        scale_min=int(raw.get("scale_min", 1)),
        scale_max=int(raw.get("scale_max", 7)),
    )


def load_schema(path: str | Path) -> FormSchema:
    """Load a schema from a JSON or YAML file."""
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if p.suffix.lower() in {".yaml", ".yml"}:
        raw = yaml.safe_load(text)
    else:
        raw = json.loads(text)
    if not isinstance(raw, dict):
        raise TypeError(f"Schema root must be a mapping, got {type(raw).__name__}")
    fields = tuple(_coerce_field(f) for f in raw.get("fields", []))
    return FormSchema(
        id=str(raw["id"]),
        title=str(raw["title"]),
        description=str(raw.get("description", "")),
        form_url=str(raw["form_url"]),
        form_response_url=str(raw["form_response_url"]),
        locale=str(raw.get("locale", "id-ID")),
        fields=fields,
        metadata=dict(raw.get("metadata", {})),
    )


def list_schemas(directory: str | Path) -> list[Path]:
    """Return every JSON/YAML schema under `directory`, sorted."""
    d = Path(directory)
    if not d.is_dir():
        return []
    out: list[Path] = []
    for ext in ("*.json", "*.yaml", "*.yml"):
        out.extend(sorted(d.glob(ext)))
    return out

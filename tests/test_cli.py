"""Tests for CLI argument parsing."""
from __future__ import annotations

from qbot.cli import build_parser


def test_parser_generate_subcommand() -> None:
    p = build_parser()
    args = p.parse_args([
        "generate", "--schema", "s.json", "--count", "20", "--out", "o.json", "--seed", "7",
    ])
    assert args.cmd == "generate"
    assert args.schema == "s.json"
    assert args.count == 20
    assert args.out == "o.json"
    assert args.seed == 7
    assert args.locale == "id_ID"


def test_parser_run_subcommand() -> None:
    p = build_parser()
    args = p.parse_args([
        "run", "--schema", "s.json", "--dataset", "d.json",
        "-c", "5", "--fast", "--start", "0", "--end", "10",
        "--results", "r.jsonl",
    ])
    assert args.cmd == "run"
    assert args.concurrency == 5
    assert args.fast is True
    assert args.start == 0
    assert args.end == 10
    assert args.results == "r.jsonl"


def test_parser_run_defaults() -> None:
    p = build_parser()
    args = p.parse_args(["run", "--schema", "s.json", "--dataset", "d.json"])
    assert args.concurrency == 1
    assert args.fast is False
    assert args.headful is False
    assert args.min_delay == 3.0
    assert args.max_delay == 8.0


def test_parser_list_schemas_subcommand() -> None:
    p = build_parser()
    args = p.parse_args(["list-schemas", "--dir", "schemas"])
    assert args.cmd == "list-schemas"
    assert args.dir == "schemas"


def test_parser_log_level() -> None:
    p = build_parser()
    args = p.parse_args(["--log-level", "DEBUG", "list-schemas"])
    assert args.log_level == "DEBUG"

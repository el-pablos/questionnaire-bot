"""CLI entry point for the questionnaire bot.

Usage:
    qbot generate --schema schemas/foo.json --count 100 --out data/foo.json
    qbot run      --schema schemas/foo.json --dataset data/foo.json -c 5 --fast
    qbot list-schemas --dir schemas/
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from loguru import logger

from .runner import append_results_jsonl, run_batch
from .schema import list_schemas, load_schema


def _setup_logging(level: str = "INFO") -> None:
    logger.remove()
    logger.add(
        sys.stderr,
        level=level,
        format="<green>{time:HH:mm:ss}</green> | <level>{level:7}</level> | {message}",
    )


def cmd_generate(args: argparse.Namespace) -> int:
    from .persona import generate_dataset
    schema = load_schema(args.schema)
    dataset = generate_dataset(schema, args.count, seed=args.seed, fake_locale=args.locale)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(dataset, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.success(f"Generated {len(dataset)} personas for schema '{schema.id}' -> {out}")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    schema = load_schema(args.schema)
    dataset_path = Path(args.dataset)
    if not dataset_path.exists():
        logger.error(f"Dataset not found: {dataset_path}")
        return 2
    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    if not isinstance(dataset, list):
        logger.error("Dataset must be a JSON array of personas")
        return 2

    start = max(0, args.start)
    end = args.end if args.end is not None else len(dataset)
    end = min(end, len(dataset))
    if start >= end:
        logger.error(f"Empty range: start={start} end={end}")
        return 1

    personas = dataset[start:end]
    logger.info(
        f"Running schema='{schema.id}' personas[{start}:{end}] "
        f"({len(personas)} subs, concurrency={args.concurrency}, fast={args.fast})"
    )

    results_path = Path(args.results) if args.results else None

    def _on_result(rec: object) -> None:
        if results_path is not None:
            append_results_jsonl(results_path, rec)  # type: ignore[arg-type]

    results = asyncio.run(
        run_batch(
            schema=schema,
            personas=personas,
            concurrency=args.concurrency,
            headful=args.headful,
            fast=args.fast,
            min_jitter=args.min_delay,
            max_jitter=args.max_delay,
            on_result=_on_result,
        )
    )
    success = sum(1 for r in results if r.status == "success")
    fail = len(results) - success
    logger.info(f"DONE  success={success}  fail={fail}  total={len(results)}")
    return 0 if fail == 0 else 2


def cmd_list_schemas(args: argparse.Namespace) -> int:
    paths = list_schemas(args.dir)
    if not paths:
        logger.warning(f"No schemas found in {args.dir}")
        return 1
    print(f"Found {len(paths)} schema(s) in {args.dir}:")
    for p in paths:
        try:
            s = load_schema(p)
            print(f"  - {p.name}  id={s.id}  fields={len(s.fields)}  title={s.title[:60]}")
        except Exception as e:  # noqa: BLE001
            print(f"  - {p.name}  [INVALID: {e}]")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="qbot", description="Generic Google Forms automation bot")
    p.add_argument("--log-level", default="INFO", help="Logging level (DEBUG/INFO/WARNING/ERROR)")
    sub = p.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("generate", help="Generate persona dataset for a schema")
    g.add_argument("--schema", required=True, help="Path to form schema JSON/YAML")
    g.add_argument("--count", type=int, default=10, help="Number of personas")
    g.add_argument("--out", required=True, help="Output JSON path")
    g.add_argument("--seed", type=int, default=None, help="Optional RNG seed")
    g.add_argument("--locale", default="id_ID", help="Faker locale (default id_ID)")
    g.set_defaults(func=cmd_generate)

    r = sub.add_parser("run", help="Run submissions against a form")
    r.add_argument("--schema", required=True, help="Path to form schema JSON/YAML")
    r.add_argument("--dataset", required=True, help="Path to persona dataset JSON")
    r.add_argument("--start", type=int, default=0, help="Start index in dataset")
    r.add_argument("--end", type=int, default=None, help="Exclusive end index")
    r.add_argument("--concurrency", "-c", type=int, default=1, help="Parallel browsers")
    r.add_argument("--fast", action="store_true", help="Reduce delays for max speed")
    r.add_argument("--headful", action="store_true", help="Show browser window")
    r.add_argument("--min-delay", type=float, default=3.0, help="Min jitter seconds between workers")
    r.add_argument("--max-delay", type=float, default=8.0, help="Max jitter seconds between workers")
    r.add_argument("--results", default=None, help="Path to JSONL results file")
    r.set_defaults(func=cmd_run)

    l = sub.add_parser("list-schemas", help="List available schemas in a directory")
    l.add_argument("--dir", default="schemas", help="Directory to scan")
    l.set_defaults(func=cmd_list_schemas)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    _setup_logging(args.log_level)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())

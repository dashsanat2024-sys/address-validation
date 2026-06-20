#!/usr/bin/env python3
"""Generate fine-tuning JSONL from Postcodes.io + synthetic UK addresses."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from address_validation.review_store import corrections_to_instruction_jsonl  # noqa: E402
from address_validation.training.export import DEFAULT_INSTRUCTION  # noqa: E402
from address_validation.training.synthetic import SyntheticGenerator  # noqa: E402

DEFAULT_OUT = ROOT / "data" / "training" / "synthetic.jsonl"
DEFAULT_MERGED = ROOT / "data" / "training" / "train.jsonl"
CORRECTIONS = ROOT / "data" / "review" / "corrections.csv"


def write_jsonl(records: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in records:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate address fine-tuning dataset")
    parser.add_argument("--count", type=int, default=2000, help="Target synthetic rows")
    parser.add_argument("--postcodes", type=int, default=400, help="Unique postcodes to fetch")
    parser.add_argument("--invalid-ratio", type=float, default=0.15, help="Share of invalid PC examples")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--merge-corrections", action="store_true", help="Append human corrections")
    parser.add_argument("--merged-output", type=Path, default=DEFAULT_MERGED)
    parser.add_argument("--offline", action="store_true", help="Skip network; requires postcodes cache")
    args = parser.parse_args()

    gen = SyntheticGenerator(
        seed=args.seed,
        invalid_ratio=args.invalid_ratio,
    )

    if args.offline:
        cache = ROOT / "data" / "training" / "postcodes_cache.json"
        if not cache.exists():
            print(f"No cache at {cache}. Run once without --offline.", file=sys.stderr)
            return 1
        postcodes = json.loads(cache.read_text(encoding="utf-8"))[: args.postcodes]
        records = gen.generate(args.count, args.postcodes, postcodes=postcodes)
    else:
        print(f"Fetching up to {args.postcodes} postcodes and generating ~{args.count} rows…")
        records = gen.generate(args.count, args.postcodes)

    write_jsonl(records, args.output)
    print(f"Wrote {len(records)} synthetic rows → {args.output}")

    if args.merge_corrections and CORRECTIONS.exists():
        corrections_out = args.output.with_name("from_corrections.jsonl")
        n = corrections_to_instruction_jsonl(
            CORRECTIONS,
            corrections_out,
            instruction=DEFAULT_INSTRUCTION,
            include_llm_validation=True,
            overwrite=True,
        )
        merged = records + list(_read_jsonl(corrections_out))
        write_jsonl(merged, args.merged_output)
        print(f"Merged {n} correction rows → {args.merged_output} ({len(merged)} total)")
    elif args.merge_corrections:
        print("No corrections.csv found — skipped merge.")
    else:
        write_jsonl(records, args.merged_output)
        print(f"Fine-tune dataset → {args.merged_output} ({len(records)} rows)")

    return 0


def _read_jsonl(path: Path):
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                yield json.loads(line)


if __name__ == "__main__":
    raise SystemExit(main())

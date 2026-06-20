#!/usr/bin/env python3
"""Score mapper accuracy against gold JSONL labels."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from address_validation.training.evaluate import evaluate_jsonl  # noqa: E402

DEFAULT_DATA = ROOT / "data" / "training" / "synthetic.jsonl"


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate address mapper vs gold labels")
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--max-rows", type=int, default=None)
    parser.add_argument("--use-llm", action="store_true", help="Use Ollama (slow)")
    parser.add_argument("--skip-validation", action="store_true")
    parser.add_argument("--model", default=None, help="Ollama model name")
    parser.add_argument("--json", action="store_true", help="Print full JSON report")
    args = parser.parse_args()

    if not args.data.exists():
        print(f"Dataset not found: {args.data}", file=sys.stderr)
        print("Run: python tools/generate_training_dataset.py", file=sys.stderr)
        return 1

    report = evaluate_jsonl(
        args.data,
        skip_llm=not args.use_llm,
        skip_validation=args.skip_validation,
        model=args.model,
        max_rows=args.max_rows,
    )

    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        d = report.to_dict()
        print(f"Rows evaluated:     {d['total']}")
        print(f"Exact match rate:   {d['exact_match_rate']:.1%} ({report.exact_match}/{report.total})")
        print("Field accuracy:")
        for fld, acc in d["field_accuracy"].items():
            print(f"  {fld:22} {acc:.1%}")
        if report.failures:
            print(f"\nFirst failure:")
            f = report.failures[0]
            print(f"  Input: {f['input'][:80]}…")
            print(f"  Gold:  {f['gold']}")
            print(f"  Pred:  {f['pred']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""CLI for testing the address pipeline."""

from __future__ import annotations

import argparse
import json
import os
import sys

from dotenv import load_dotenv

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from address_validation.export import write_client_csv  # noqa: E402
from address_validation.pipeline import AddressPipeline  # noqa: E402
from address_validation.vendor_import import load_mapping_config, parse_csv_rows  # noqa: E402

load_dotenv()


def main() -> int:
    parser = argparse.ArgumentParser(description="UK address validation pipeline")
    parser.add_argument("address", nargs="?", help="Vendor address string")
    parser.add_argument("--customer-id", default="", help="Optional customer ID")
    parser.add_argument("--model", default=None, help="Ollama model (default: qwen3:8b)")
    parser.add_argument("--skip-llm", action="store_true", help="Postcode validate only")
    parser.add_argument("--file", help="Vendor CSV (auto-detects columns)")
    parser.add_argument(
        "--export-csv",
        help="Write client-format CSV to this path (use with --file)",
    )
    args = parser.parse_args()

    pipeline = AddressPipeline(model=args.model, skip_llm=args.skip_llm)

    if args.file:
        config = load_mapping_config()
        override = config.get("override") or {}
        with open(args.file, newline="", encoding="utf-8-sig") as fh:
            preview = parse_csv_rows(fh, override)

        results = []
        for row in preview.sample_rows:
            result = pipeline.run(row.vendor_address, customer_id=row.customer_id)
            results.append(result.to_dict())
            if not args.export_csv:
                print(json.dumps(results[-1], indent=2))

        if args.export_csv:
            with open(args.export_csv, "w", newline="", encoding="utf-8") as out:
                count = write_client_csv(results, out)
            print(f"Exported {count} rows to {args.export_csv}")
        return 0

    if not args.address:
        parser.error("Provide an address or --file")

    result = pipeline.run(args.address, customer_id=args.customer_id)
    print(json.dumps(result.to_dict(), indent=2))
    return 0 if result.success else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Run Azure OpenAI UK address normalization POC.

Examples:
    cd poc/azure_uk_address
    cp .env.example .env   # add Azure credentials
    pip install -r requirements.txt
    python run_poc.py
    python run_poc.py --address "Apartment 7 Elliot's Yard 8 Gulson Road Coventry CV1 2NF"
    python run_poc.py --dry-run   # print prompts + token estimate only (no API call)
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

load_dotenv(ROOT / ".env")

from src.cost_analysis import analyze_cost, estimate_prompt_tokens, TokenUsage  # noqa: E402
from src.postcode_validate import extract_postcode, validate_postcode  # noqa: E402
from src.prompts import build_user_prompt, load_system_prompt  # noqa: E402
from src.azure_client import _rule_hint_for_reversed, normalize_address  # noqa: E402

DEFAULT_ADDRESS = "Apartment 7 Elliot's Yard 8 Gulson Road Coventry CV1 2NF"


def _print_cost_report(result_dict: dict) -> None:
    cost = result_dict.get("cost_analysis", {})
    tokens = cost.get("tokens", {})
    cost_usd = cost.get("cost_usd", {})
    projections = cost.get("projections_usd", {})

    print("\n── Token usage ──")
    print(f"  Prompt tokens:     {tokens.get('prompt', 0):,}")
    print(f"  Completion tokens: {tokens.get('completion', 0):,}")
    print(f"  Total tokens:      {tokens.get('total', 0):,}")
    if tokens.get("estimated_prompt"):
        print(f"  Est. prompt (offline): {tokens['estimated_prompt']:,}")

    print("\n── Cost analysis (USD) ──")
    print(f"  Model / deployment: {cost.get('model', 'n/a')}")
    pricing = cost.get("pricing_usd_per_1m", {})
    print(f"  Pricing: ${pricing.get('input', 0):.2f}/1M input · ${pricing.get('output', 0):.2f}/1M output")
    print(f"  This request:  ${cost_usd.get('total_per_request', 0):.6f}")
    print(f"    Input:  ${cost_usd.get('input', 0):.6f}")
    print(f"    Output: ${cost_usd.get('output', 0):.6f}")
    print("\n── Volume projections ──")
    for label, value in projections.items():
        print(f"  {label.replace('_', ' ')}: ${value:,.2f}")


def dry_run(address: str, skip_postcode: bool) -> None:
    system = load_system_prompt()
    ctx: dict = {}
    if not skip_postcode:
        pc = extract_postcode(address)
        if pc:
            ctx = validate_postcode(pc)
    hint = _rule_hint_for_reversed(address)
    user = build_user_prompt(address, validation_context=ctx or None, rule_parser_hint=hint)
    est = estimate_prompt_tokens(system, user)
    est_completion = 180  # typical JSON response size

    print("── DRY RUN (no Azure API call) ──\n")
    print("SYSTEM PROMPT:\n")
    print(system)
    print("\nUSER PROMPT:\n")
    print(user)
    print(f"\nEstimated prompt tokens: ~{est:,}")
    print(f"Estimated completion tokens: ~{est_completion:,} (assumed)")
    usage = TokenUsage(prompt_tokens=est, completion_tokens=est_completion, total_tokens=est + est_completion)
    cost = analyze_cost("gpt-4o-mini", usage)
    _print_cost_report({"cost_analysis": cost.to_dict()})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--address", default=DEFAULT_ADDRESS, help="Vendor address to normalize")
    parser.add_argument("--skip-postcode", action="store_true", help="Skip Postcodes.io lookup")
    parser.add_argument("--dry-run", action="store_true", help="Print prompts and cost estimate only")
    parser.add_argument("--out", type=Path, help="Save full JSON result to file")
    args = parser.parse_args()

    if args.dry_run:
        dry_run(args.address, args.skip_postcode)
        return 0

    print(f"Normalizing: {args.address}\n")
    result = normalize_address(args.address, skip_postcode_lookup=args.skip_postcode)
    payload = result.to_dict()

    print("── Normalized output ──")
    print(json.dumps(payload["normalized"], indent=2))
    if payload.get("llm_validation"):
        print("\n── LLM validation ──")
        print(json.dumps(payload["llm_validation"], indent=2))
    if payload.get("errors"):
        print("\n── Errors ──")
        for err in payload["errors"]:
            print(f"  ! {err}")

    _print_cost_report(payload)
    print(f"\nLatency: {payload['latency_ms']:.0f} ms")

    out_path = args.out or ROOT / "results" / f"poc_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\nSaved: {out_path}")
    return 0 if not payload.get("errors") else 1


if __name__ == "__main__":
    raise SystemExit(main())

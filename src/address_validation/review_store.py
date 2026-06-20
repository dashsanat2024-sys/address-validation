"""Export human corrections as fine-tuning JSONL."""

from __future__ import annotations

import csv
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .schema import is_valid_uk_postcode_format
from .training.export import DEFAULT_INSTRUCTION, build_training_output

DEFAULT_PATH = Path(__file__).resolve().parents[2] / "data" / "review" / "corrections.csv"


def record_correction(
    vendor_address: str,
    llm_output: dict[str, Any],
    human_corrected: dict[str, Any],
    customer_id: str = "",
    path: Path = DEFAULT_PATH,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not path.exists() or path.stat().st_size == 0
    with path.open("a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "timestamp",
                "customer_id",
                "vendor_address",
                "llm_output",
                "human_corrected",
            ],
        )
        if write_header:
            writer.writeheader()
        writer.writerow(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "customer_id": customer_id,
                "vendor_address": vendor_address,
                "llm_output": json.dumps(llm_output, ensure_ascii=False),
                "human_corrected": json.dumps(human_corrected, ensure_ascii=False),
            }
        )


def _parse_json_field(raw: str) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def export_correction_output(
    human_corrected: dict[str, Any],
    *,
    include_llm_validation: bool = True,
    postcode_exists: bool | None = True,
) -> dict[str, Any]:
    """Build training output JSON from a human-corrected row."""
    if not include_llm_validation:
        return human_corrected

    if "llm_validation" in human_corrected:
        return human_corrected

    pc = human_corrected.get("postal_code", "")
    fmt_ok = is_valid_uk_postcode_format(pc) if pc else False
    return build_training_output(
        human_corrected,
        postcode_format_valid=fmt_ok,
        postcode_exists=postcode_exists if postcode_exists is not None else fmt_ok,
        postcode_plausible=True,
        validation_notes="human_corrected",
    )


def corrections_to_instruction_jsonl(
    corrections_csv: Path,
    output_jsonl: Path,
    instruction: str = DEFAULT_INSTRUCTION,
    *,
    include_llm_validation: bool = True,
    overwrite: bool = False,
) -> int:
    """Export human corrections as fine-tuning JSONL with optional llm_validation block."""
    if not corrections_csv.exists():
        return 0

    count = 0
    output_jsonl.parent.mkdir(parents=True, exist_ok=True)
    mode = "w" if overwrite else "a"
    with corrections_csv.open(newline="", encoding="utf-8") as src, output_jsonl.open(
        mode, encoding="utf-8"
    ) as dst:
        for row in csv.DictReader(src):
            corrected = _parse_json_field(row.get("human_corrected", ""))
            if not corrected:
                continue
            output = export_correction_output(
                corrected,
                include_llm_validation=include_llm_validation,
            )
            record = {
                "instruction": instruction,
                "input": row["vendor_address"],
                "output": json.dumps(output, ensure_ascii=False),
            }
            dst.write(json.dumps(record, ensure_ascii=False) + os.linesep)
            count += 1
    return count

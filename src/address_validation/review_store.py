"""Store corrections for future fine-tuning (Phase 2)."""

from __future__ import annotations

import csv
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

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


def corrections_to_instruction_jsonl(
    corrections_csv: Path,
    output_jsonl: Path,
    instruction: str = "Convert UK address into company standard format",
) -> int:
    """Export human corrections as fine-tuning JSONL."""
    if not corrections_csv.exists():
        return 0

    count = 0
    output_jsonl.parent.mkdir(parents=True, exist_ok=True)
    with corrections_csv.open(newline="", encoding="utf-8") as src, output_jsonl.open(
        "a", encoding="utf-8"
    ) as dst:
        for row in csv.DictReader(src):
            record = {
                "instruction": instruction,
                "input": row["vendor_address"],
                "output": row["human_corrected"],
            }
            dst.write(json.dumps(record, ensure_ascii=False) + os.linesep)
            count += 1
    return count

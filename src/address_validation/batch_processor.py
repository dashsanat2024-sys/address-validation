"""Shared batch processing for vendor CSV files."""

from __future__ import annotations

import io
from typing import Any, Callable, Iterator

from .pipeline import AddressPipeline
from .vendor_import import load_mapping_config, parse_csv_rows


ProgressCallback = Callable[[dict[str, Any]], None]


def iter_batch_results(
    file_stream: io.TextIOBase,
    skip_llm: bool = False,
    validator: str | None = None,
    on_progress: ProgressCallback | None = None,
) -> Iterator[dict[str, Any]]:
    config = load_mapping_config()
    override = config.get("override") or {}
    preview = parse_csv_rows(file_stream, override)
    runner = AddressPipeline(skip_llm=skip_llm, validator=validator)
    total = len(preview.sample_rows)

    for index, row in enumerate(preview.sample_rows, start=1):
        result = runner.run(row.vendor_address, customer_id=row.customer_id)
        payload = result.to_dict()
        payload["vendor_address"] = row.vendor_address
        payload["batch_index"] = index
        payload["batch_total"] = total

        if on_progress:
            on_progress(
                {
                    "type": "progress",
                    "current": index,
                    "total": total,
                    "customer_id": row.customer_id,
                    "vendor_address": row.vendor_address,
                    "success": result.success,
                    "errors": result.errors,
                }
            )
        yield payload

"""Shared batch processing for vendor CSV files."""

from __future__ import annotations

import io
from typing import Any, Callable, Iterator

from .pipeline import AddressPipeline
from .vendor_import import load_mapping_config, parse_csv_rows


ProgressCallback = Callable[[dict[str, Any]], None]


def iter_batch_events(
    file_stream: io.TextIOBase,
    skip_llm: bool = False,
    skip_validation: bool = False,
    validator: str | None = None,
) -> Iterator[dict[str, Any]]:
    config = load_mapping_config()
    override = config.get("override") or {}
    preview = parse_csv_rows(file_stream, override)
    runner = AddressPipeline(
        skip_llm=skip_llm,
        skip_validation=skip_validation,
        validator=validator,
    )
    total = len(preview.sample_rows)

    yield {
        "type": "started",
        "total": total,
        "skip_llm": skip_llm,
        "skip_validation": skip_validation,
        "message": (
            "Fast mode — no Ollama."
            if skip_llm
            else f"Processing {total} row(s). Loading Ollama model if needed (~45s first time)…"
        ),
    }

    if not skip_llm:
        from .ollama_client import warm_model

        yield {
            "type": "warming",
            "message": "Loading Ollama model into memory…",
        }
        warm_model()

    for index, row in enumerate(preview.sample_rows, start=1):
        yield {
            "type": "row_start",
            "current": index,
            "total": total,
            "customer_id": row.customer_id,
            "vendor_address": row.vendor_address,
        }

        result = runner.run(row.vendor_address, customer_id=row.customer_id)
        payload = result.to_dict()
        payload["vendor_address"] = row.vendor_address
        payload["batch_index"] = index
        payload["batch_total"] = total
        payload["type"] = "progress"
        payload["current"] = index
        yield payload


def iter_batch_results(
    file_stream: io.TextIOBase,
    skip_llm: bool = False,
    skip_validation: bool = False,
    validator: str | None = None,
    on_progress: ProgressCallback | None = None,
) -> Iterator[dict[str, Any]]:
    """Legacy iterator — yields result payloads only (row_done events)."""
    for event in iter_batch_events(
        file_stream,
        skip_llm=skip_llm,
        skip_validation=skip_validation,
        validator=validator,
    ):
        if event.get("type") == "progress":
            if on_progress:
                on_progress(event)
            yield event

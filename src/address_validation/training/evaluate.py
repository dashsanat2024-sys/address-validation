"""Evaluate address mapper accuracy against gold training labels."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

from ..pipeline import AddressPipeline
from .export import TRAINING_OUTPUT_FIELDS, normalize_field_for_compare, parse_training_output

COMPARE_FIELDS = (
    "street_2",
    "street_3",
    "street_house_number",
    "street_4",
    "other_city",
    "district",
    "postal_code",
)


@dataclass
class FieldScore:
    correct: int = 0
    total: int = 0

    @property
    def accuracy(self) -> float:
        return self.correct / self.total if self.total else 0.0


@dataclass
class EvaluationReport:
    total: int = 0
    exact_match: int = 0
    field_scores: dict[str, FieldScore] = field(default_factory=dict)
    failures: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "exact_match": self.exact_match,
            "exact_match_rate": self.exact_match / self.total if self.total else 0.0,
            "field_accuracy": {k: v.accuracy for k, v in self.field_scores.items()},
            "failures_sample": self.failures[:20],
        }


def load_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield json.loads(line)


def evaluate_records(
    records: list[dict[str, Any]],
    *,
    skip_llm: bool = True,
    skip_validation: bool = False,
    model: str | None = None,
    max_rows: int | None = None,
) -> EvaluationReport:
    runner = AddressPipeline(skip_llm=skip_llm, skip_validation=skip_validation, model=model)
    report = EvaluationReport()
    report.field_scores = {f: FieldScore() for f in COMPARE_FIELDS}

    for idx, row in enumerate(records):
        if max_rows is not None and idx >= max_rows:
            break

        vendor = row.get("input") or row.get("vendor_address") or ""
        gold = parse_training_output(row.get("output") or row.get("gold") or "{}")

        result = runner.run(vendor)
        pred = result.normalized_address or {}

        report.total += 1
        row_exact = True
        for fld in COMPARE_FIELDS:
            g = normalize_field_for_compare(gold.get(fld, ""), fld)
            p = normalize_field_for_compare(pred.get(fld, ""), fld)
            report.field_scores[fld].total += 1
            if g == p:
                report.field_scores[fld].correct += 1
            else:
                row_exact = False

        if row_exact:
            report.exact_match += 1
        elif len(report.failures) < 50:
            report.failures.append(
                {
                    "input": vendor,
                    "gold": {f: gold.get(f) for f in COMPARE_FIELDS},
                    "pred": {f: pred.get(f) for f in COMPARE_FIELDS},
                    "errors": result.errors,
                }
            )

    return report


def evaluate_jsonl(
    path: Path,
    *,
    skip_llm: bool = True,
    skip_validation: bool = False,
    model: str | None = None,
    max_rows: int | None = None,
) -> EvaluationReport:
    records = list(load_jsonl(path))
    return evaluate_records(
        records,
        skip_llm=skip_llm,
        skip_validation=skip_validation,
        model=model,
        max_rows=max_rows,
    )

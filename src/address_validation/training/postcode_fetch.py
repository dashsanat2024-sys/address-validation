"""Fetch and cache postcodes from Postcodes.io for training data."""

from __future__ import annotations

import json
import random
import time
from pathlib import Path
from typing import Any

import requests

from ..postcodes_io import PostcodesIOClient
from ..schema import format_uk_postcode

DEFAULT_CACHE = Path(__file__).resolve().parents[3] / "data" / "training" / "postcodes_cache.json"


def fetch_random_postcodes(
    count: int,
    *,
    client: PostcodesIOClient | None = None,
    cache_path: Path = DEFAULT_CACHE,
    use_cache: bool = True,
    delay_seconds: float = 0.2,
) -> list[dict[str, Any]]:
    """Fetch `count` random valid UK postcodes with metadata."""
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    if use_cache and cache_path.exists():
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
        if len(cached) >= count:
            return cached[:count]

    client = client or PostcodesIOClient()
    session = client.session
    base = client.base_url
    collected: dict[str, dict[str, Any]] = {}

    if cache_path.exists():
        for row in json.loads(cache_path.read_text(encoding="utf-8")):
            pc = row.get("postcode")
            if pc:
                collected[format_uk_postcode(pc)] = row

    while len(collected) < count:
        batch = min(100, count - len(collected))
        try:
            resp = session.get(
                f"{base}/random/postcodes",
                params={"limit": batch},
                timeout=client.timeout,
            )
            resp.raise_for_status()
            payload = resp.json().get("result")
            if payload is None:
                rows = []
            elif isinstance(payload, list):
                rows = payload
            else:
                rows = [payload]
        except requests.RequestException:
            time.sleep(1.0)
            continue

        for row in rows:
            if isinstance(row, str):
                pc = format_uk_postcode(row)
                meta = client.lookup_postcode(pc)
                if not meta.valid:
                    continue
                collected[pc] = {
                    "postcode": pc,
                    "admin_district": meta.admin_district or "",
                    "region": meta.region or "",
                    "country": meta.country or "England",
                    "parliamentary_constituency": meta.parliamentary_constituency or "",
                }
                continue
            pc = format_uk_postcode(row.get("postcode", ""))
            if not pc:
                continue
            collected[pc] = {
                "postcode": pc,
                "admin_district": row.get("admin_district") or "",
                "region": row.get("region") or "",
                "country": row.get("country") or "England",
                "parliamentary_constituency": row.get("parliamentary_constituency") or "",
            }
            if len(collected) >= count:
                break
        time.sleep(delay_seconds)

    result = list(collected.values())[:count]
    cache_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return result


def mutate_invalid_postcode(valid_pc: str) -> str:
    """Produce a plausible-format postcode that is unlikely to exist."""
    pc = format_uk_postcode(valid_pc)
    compact = pc.replace(" ", "")
    # Flip last character of incode
    chars = "ABCEGHJKLMNOPQRSTUVWXYZ"
    last = compact[-1]
    for replacement in chars:
        if replacement != last:
            candidate = compact[:-1] + replacement
            return format_uk_postcode(candidate)
    return "XX99 9XX"

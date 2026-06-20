"""Similarity search over address mapping examples."""

from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from typing import Any

from ..local_address_store import lookup as local_lookup
from .store import RagExample, load_examples

POSTCODE_RE = re.compile(r"\b([A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2})\b", re.IGNORECASE)
TOKEN_RE = re.compile(r"[a-z0-9]+")


def is_rag_enabled(explicit: bool | None = None) -> bool:
    if explicit is not None:
        return bool(explicit)
    return os.getenv("RAG_ENABLED", "1").strip().lower() in {"1", "true", "yes"}


def _tokens(text: str) -> set[str]:
    return set(TOKEN_RE.findall((text or "").lower()))


def _extract_postcode(text: str) -> str:
    m = POSTCODE_RE.search(text or "")
    return m.group(1).upper().replace("  ", " ") if m else ""


def _similarity(query: str, example: RagExample) -> float:
    tq = _tokens(query)
    te = _tokens(example.vendor_address)
    if not tq or not te:
        return 0.0
    overlap = len(tq & te) / len(tq | te)
    score = overlap * example.weight
    pq, pe = _extract_postcode(query), _extract_postcode(example.vendor_address)
    if pq and pe and pq.replace(" ", "") == pe.replace(" ", ""):
        score += 0.35
    if query.strip().lower() == example.vendor_address.strip().lower():
        score += 1.0
    return score


@lru_cache(maxsize=1)
def _cached_examples() -> tuple[RagExample, ...]:
    return tuple(load_examples())


def retrieve_similar_examples(vendor_address: str, top_k: int | None = None) -> list[dict[str, Any]]:
    k = top_k or int(os.getenv("RAG_TOP_K", "3"))
    examples = _cached_examples()
    if not examples:
        return []

    scored = [
        (ex, _similarity(vendor_address, ex))
        for ex in examples
        if vendor_address.strip().lower() != ex.vendor_address.strip().lower()
    ]
    scored.sort(key=lambda x: x[1], reverse=True)
    hits = []
    for ex, score in scored[:k]:
        if score <= 0.05:
            continue
        hits.append(
            {
                "vendor_address": ex.vendor_address,
                "mapped": ex.mapped,
                "source": ex.source,
                "score": round(score, 3),
            }
        )
    return hits


def format_rag_block(hits: list[dict[str, Any]]) -> str:
    if not hits:
        return ""
    lines = [
        "Similar corrected examples from your knowledge base (use as mapping guidance, not as copy-paste):",
    ]
    for i, hit in enumerate(hits, 1):
        lines.append(f"\nExample {i} (source={hit['source']}, relevance={hit['score']}):")
        lines.append(f"Input: {hit['vendor_address']}")
        lines.append(f"Mapped output: {json.dumps(hit['mapped'], ensure_ascii=False)}")
    return "\n".join(lines)


def format_local_block(local: dict[str, Any]) -> str:
    if not local:
        return ""
    matched = local.get("matched_address") or {}
    lines = [
        "Local address index match (validated before LLM — prefer for postcode/city/street when confident):",
        json.dumps(local, ensure_ascii=False),
    ]
    if matched.get("street"):
        lines.append(f"Canonical street: {matched.get('number', '')} {matched['street']}".strip())
    return "\n".join(lines)


def attach_local_lookup(
    validation_context: dict[str, Any],
    vendor_address: str,
    postcode_hint: str | None = None,
) -> dict[str, Any]:
    """Merge local index lookup into validation context for RAG + LLM."""
    ctx = dict(validation_context)
    match = local_lookup(vendor_address, postcode_hint)
    if match:
        ctx["local_lookup"] = match.to_context_dict()
    return ctx


def enrich_user_prompt(
    user_prompt: str,
    vendor_address: str,
    *,
    enabled: bool | None = None,
    validation_context: dict[str, Any] | None = None,
    postcode_hint: str | None = None,
) -> tuple[str, dict[str, Any]]:
    """Append local lookup + RAG examples to user prompt; return metadata for API/UI."""
    meta: dict[str, Any] = {
        "enabled": is_rag_enabled(enabled),
        "hits": [],
        "examples_count": len(_cached_examples()),
        "local_lookup": None,
    }
    blocks: list[str] = []

    if validation_context and validation_context.get("local_lookup"):
        meta["local_lookup"] = validation_context["local_lookup"]
        local_block = format_local_block(validation_context["local_lookup"])
        if local_block:
            blocks.append(local_block)
    else:
        match = local_lookup(vendor_address, postcode_hint)
        if match:
            meta["local_lookup"] = match.to_context_dict()
            local_block = format_local_block(meta["local_lookup"])
            if local_block:
                blocks.append(local_block)

    if not meta["enabled"]:
        if blocks:
            return f"{user_prompt}\n\n" + "\n\n".join(blocks), meta
        return user_prompt, meta

    hits = retrieve_similar_examples(vendor_address)
    meta["hits"] = hits
    rag_block = format_rag_block(hits)
    if rag_block:
        blocks.append(rag_block)
    elif not blocks:
        meta["note"] = "No sufficiently similar examples found in knowledge base."
        return user_prompt, meta

    return f"{user_prompt}\n\n" + "\n\n".join(blocks), meta

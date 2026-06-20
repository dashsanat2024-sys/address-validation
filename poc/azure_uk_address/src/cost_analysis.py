"""Token usage and cost analysis for Azure OpenAI calls."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

# Azure OpenAI list pricing (USD per 1M tokens) — update from Azure portal / pricing page.
# https://azure.microsoft.com/en-us/pricing/details/cognitive-services/openai-service/
DEFAULT_PRICING: dict[str, dict[str, float]] = {
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4.1-mini": {"input": 0.40, "output": 1.60},
    "gpt-4.1": {"input": 2.00, "output": 8.00},
    "gpt-35-turbo": {"input": 0.50, "output": 1.50},
}


@dataclass
class TokenUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    estimated_prompt_tokens: int | None = None

    @classmethod
    def from_api(cls, usage: Any) -> "TokenUsage":
        if usage is None:
            return cls()
        return cls(
            prompt_tokens=int(getattr(usage, "prompt_tokens", 0) or 0),
            completion_tokens=int(getattr(usage, "completion_tokens", 0) or 0),
            total_tokens=int(getattr(usage, "total_tokens", 0) or 0),
        )


@dataclass
class CostBreakdown:
    model: str
    usage: TokenUsage
    input_price_per_1m: float
    output_price_per_1m: float
    input_cost_usd: float = 0.0
    output_cost_usd: float = 0.0
    total_cost_usd: float = 0.0
    projections: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "tokens": {
                "prompt": self.usage.prompt_tokens,
                "completion": self.usage.completion_tokens,
                "total": self.usage.total_tokens,
                "estimated_prompt": self.usage.estimated_prompt_tokens,
            },
            "pricing_usd_per_1m": {
                "input": self.input_price_per_1m,
                "output": self.output_price_per_1m,
            },
            "cost_usd": {
                "input": round(self.input_cost_usd, 6),
                "output": round(self.output_cost_usd, 6),
                "total_per_request": round(self.total_cost_usd, 6),
            },
            "projections_usd": {k: round(v, 4) for k, v in self.projections.items()},
        }


def resolve_pricing(model: str) -> tuple[float, float]:
    custom_in = os.getenv("AZURE_INPUT_PRICE_PER_1M")
    custom_out = os.getenv("AZURE_OUTPUT_PRICE_PER_1M")
    if custom_in and custom_out:
        return float(custom_in), float(custom_out)

    key = model.lower()
    for name, prices in DEFAULT_PRICING.items():
        if name in key:
            return prices["input"], prices["output"]
    return DEFAULT_PRICING["gpt-4o-mini"]["input"], DEFAULT_PRICING["gpt-4o-mini"]["output"]


def analyze_cost(model: str, usage: TokenUsage) -> CostBreakdown:
    in_price, out_price = resolve_pricing(model)
    input_cost = (usage.prompt_tokens / 1_000_000) * in_price
    output_cost = (usage.completion_tokens / 1_000_000) * out_price
    total = input_cost + output_cost

    projections = {
        "per_1_000_addresses": total * 1_000,
        "per_10_000_addresses": total * 10_000,
        "per_100_000_addresses": total * 100_000,
        "per_1_000_000_addresses": total * 1_000_000,
    }
    return CostBreakdown(
        model=model,
        usage=usage,
        input_price_per_1m=in_price,
        output_price_per_1m=out_price,
        input_cost_usd=input_cost,
        output_cost_usd=output_cost,
        total_cost_usd=total,
        projections=projections,
    )


def estimate_prompt_tokens(system_prompt: str, user_prompt: str, model: str = "gpt-4o-mini") -> int:
    """Offline token estimate when API usage is unavailable."""
    try:
        import tiktoken

        try:
            enc = tiktoken.encoding_for_model(model)
        except KeyError:
            enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(system_prompt)) + len(enc.encode(user_prompt)) + 4
    except Exception:
        return (len(system_prompt) + len(user_prompt)) // 4

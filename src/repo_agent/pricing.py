"""Per-1M-token USD pricing used to estimate inference cost.

Local Ollama aliases are free (cost is compute you already own). Hosted
aliases are priced per the provider's public rate card. Update these
constants when provider pricing changes; they are intentionally static
rather than fetched at runtime so cost estimates stay reproducible across
a workflow's replay history.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelPrice:
    prompt_per_million: float
    completion_per_million: float


# Keyed by the LiteLLM alias, not the raw provider model name, since that's
# what run_inference actually receives and what the workflow requests.
PRICING: dict[str, ModelPrice] = {
    "agent-default": ModelPrice(0.0, 0.0),  # local Ollama
    "agent-qwen3-8b": ModelPrice(0.0, 0.0),  # local Ollama
    "agent-anthropic": ModelPrice(3.00, 15.00),  # Claude Sonnet-class pricing
    "agent-openai": ModelPrice(2.50, 10.00),  # GPT-4o-class pricing
}

DEFAULT_PRICE = ModelPrice(0.0, 0.0)


def estimate_cost_usd(alias: str, prompt_tokens: int, completion_tokens: int) -> float:
    price = PRICING.get(alias, DEFAULT_PRICE)
    return (
        prompt_tokens * price.prompt_per_million
        + completion_tokens * price.completion_per_million
    ) / 1_000_000

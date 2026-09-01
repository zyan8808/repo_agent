"""Inference token estimation and model-aware cost calculation."""

from dataclasses import dataclass
from typing import Any

import litellm


@dataclass(frozen=True)
class ModelPrice:
    prompt_per_million: float
    completion_per_million: float


LOCAL_ALIASES = {"agent-default", "agent-qwen3-8b"}
ALIAS_FALLBACK_PRICING: dict[str, ModelPrice] = {
    "agent-anthropic": ModelPrice(3.00, 15.00),
    "agent-openai": ModelPrice(2.50, 10.00),
}


def estimate_tokens(
    model: str,
    messages: list[dict[str, Any]],
    completion: str | None,
) -> tuple[int, int]:
    prompt_tokens = litellm.token_counter(  # type: ignore[reportUnknownMemberType]
        model=model,
        messages=messages,
    )
    completion_tokens = litellm.token_counter(  # type: ignore[reportUnknownMemberType]
        model=model,
        text=completion or "",
    )
    return prompt_tokens, completion_tokens


def estimate_cost_usd(
    alias: str,
    resolved_model: str,
    prompt_tokens: int,
    completion_tokens: int,
) -> float:
    if alias in LOCAL_ALIASES or resolved_model.startswith("ollama"):
        return 0.0
    try:
        prompt_cost, completion_cost = litellm.cost_per_token(
            model=resolved_model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )
        return prompt_cost + completion_cost
    except litellm.exceptions.BadRequestError:
        price = ALIAS_FALLBACK_PRICING.get(alias)
    if price is None:
        raise ValueError(f"No pricing configured for model alias {alias!r}")
    return (
        prompt_tokens * price.prompt_per_million
        + completion_tokens * price.completion_per_million
    ) / 1_000_000

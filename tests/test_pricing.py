from math import isclose
from unittest.mock import Mock

import pytest

from repo_agent import pricing


def test_local_alias_is_explicitly_free() -> None:
    assert pricing.estimate_cost_usd("agent-default", "qwen3.8:27b", 1_000, 500) == 0


def test_resolved_model_uses_litellm_price(monkeypatch: pytest.MonkeyPatch) -> None:
    cost_per_token = Mock(return_value=(0.001, 0.002))
    monkeypatch.setattr(pricing.litellm, "cost_per_token", cost_per_token)

    cost = pricing.estimate_cost_usd("agent-openai", "openai/custom-model", 1_000, 500)

    assert isclose(cost, 0.003)
    cost_per_token.assert_called_once_with(
        model="openai/custom-model",
        prompt_tokens=1_000,
        completion_tokens=500,
    )


def test_unknown_resolved_model_uses_explicit_alias_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    error = pricing.litellm.exceptions.BadRequestError(
        message="unknown model",
        model="unknown/model",
        llm_provider="unknown",
    )
    monkeypatch.setattr(pricing.litellm, "cost_per_token", Mock(side_effect=error))

    cost = pricing.estimate_cost_usd("agent-openai", "unknown/model", 1_000, 500)

    assert isclose(cost, 0.0075)


def test_unknown_alias_never_silently_becomes_free(monkeypatch: pytest.MonkeyPatch) -> None:
    error = pricing.litellm.exceptions.BadRequestError(
        message="unknown model",
        model="unknown/model",
        llm_provider="unknown",
    )
    monkeypatch.setattr(pricing.litellm, "cost_per_token", Mock(side_effect=error))

    with pytest.raises(ValueError, match="No pricing configured"):
        pricing.estimate_cost_usd("unknown-alias", "unknown/model", 1_000, 500)
from math import isclose
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from repo_agent import activities
from repo_agent.contracts import InferenceRequest


@pytest.mark.asyncio
async def test_missing_provider_usage_is_estimated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = SimpleNamespace(
        model="openai/resolved-model",
        usage=None,
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content="Done", tool_calls=None),
            )
        ],
    )
    create = AsyncMock(return_value=response)
    client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create)),
    )

    def fake_openai(**_kwargs: object) -> SimpleNamespace:
        return client

    def fake_estimate_tokens(
        _model: str,
        _messages: list[dict[str, Any]],
        _completion: str | None,
    ) -> tuple[int, int]:
        return 120, 30

    def fake_estimate_cost(
        _alias: str,
        _resolved_model: str,
        _prompt_tokens: int,
        _completion_tokens: int,
    ) -> float:
        return 0.004

    monkeypatch.setattr(activities, "AsyncOpenAI", fake_openai)
    monkeypatch.setattr(activities, "estimate_tokens", fake_estimate_tokens)
    monkeypatch.setattr(activities, "estimate_cost_usd", fake_estimate_cost)

    result = await activities.run_inference(
        InferenceRequest(
            messages=[{"role": "user", "content": "Inspect the repository"}],
            model="agent-openai",
        )
    )

    assert result.usage is not None
    assert result.usage.prompt_tokens == 120
    assert result.usage.completion_tokens == 30
    assert result.usage.total_tokens == 150
    assert isclose(result.usage.estimated_cost_usd, 0.004)
    assert result.usage.is_estimated is True
import pytest

from repo_agent.contracts import AgentRequest
from repo_agent.workflows import enforce_budget


def test_budget_allows_values_at_limits() -> None:
    request = AgentRequest(
        prompt="Inspect the repository",
        max_total_tokens=500,
        max_estimated_cost_usd=0.25,
    )

    enforce_budget(request, total_tokens=500, total_cost=0.25)


def test_budget_rejects_token_overage() -> None:
    request = AgentRequest(prompt="Inspect", max_total_tokens=500)

    with pytest.raises(RuntimeError, match="Token budget exceeded: 501 > 500"):
        enforce_budget(request, total_tokens=501, total_cost=0)


def test_budget_rejects_cost_overage() -> None:
    request = AgentRequest(prompt="Inspect", max_estimated_cost_usd=0.25)

    with pytest.raises(RuntimeError, match="Estimated cost budget exceeded"):
        enforce_budget(request, total_tokens=1, total_cost=0.251)
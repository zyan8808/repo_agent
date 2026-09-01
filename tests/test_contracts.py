import pytest
from pydantic import ValidationError

from repo_agent.api import RunCreate
from repo_agent.contracts import AgentRequest, AgentResult, McpToolCallRequest


def test_agent_contracts_round_trip() -> None:
    request = AgentRequest(prompt="Inspect this repository")
    result = AgentResult(output="Done", model="agent-default")

    assert request.prompt == "Inspect this repository"
    assert request.model == "agent-default"
    assert request.max_total_tokens == 100_000
    assert request.max_estimated_cost_usd == 5.0
    assert result.output == "Done"
    assert result.usage_is_estimated is False

    tool_request = McpToolCallRequest(
        server="github",
        name="get_file_contents",
        arguments={"owner": "zyan8808", "repo": "repo_agent", "path": "README.md"},
    )
    assert tool_request.arguments["path"] == "README.md"


@pytest.mark.parametrize(
    ("field", "value"),
    [("max_total_tokens", 0), ("max_estimated_cost_usd", 0)],
)
def test_run_create_rejects_non_positive_budgets(field: str, value: int) -> None:
    with pytest.raises(ValidationError):
        RunCreate.model_validate({"prompt": "Inspect this repository", field: value})
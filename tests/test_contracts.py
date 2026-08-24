from repo_agent.contracts import AgentRequest, AgentResult


def test_agent_contracts_round_trip() -> None:
    request = AgentRequest(prompt="Inspect this repository")
    result = AgentResult(output="Done", model="agent-default")

    assert request.prompt == "Inspect this repository"
    assert result.output == "Done"
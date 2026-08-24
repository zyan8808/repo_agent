from repo_agent.contracts import AgentRequest, AgentResult, McpToolCallRequest


def test_agent_contracts_round_trip() -> None:
    request = AgentRequest(prompt="Inspect this repository")
    result = AgentResult(output="Done", model="agent-default")

    assert request.prompt == "Inspect this repository"
    assert result.output == "Done"

    tool_request = McpToolCallRequest(
        server="github",
        name="get_file_contents",
        arguments={"owner": "zyan8808", "repo": "repo_agent", "path": "README.md"},
    )
    assert tool_request.arguments["path"] == "README.md"
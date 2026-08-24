from mcp.types import CallToolResult, TextContent, Tool
from pytest import MonkeyPatch

from repo_agent.activities import github_mcp_connection, mcp_tool_definition, mcp_tool_result
from repo_agent.settings import get_settings


def test_github_mcp_writes_require_global_and_per_run_opt_in(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv("REPO_AGENT_GITHUB_TOKEN", "test-token")
    monkeypatch.setenv("REPO_AGENT_MCP_ALLOW_WRITES", "false")
    get_settings.cache_clear()

    globally_blocked_connection = github_mcp_connection(allow_writes=True)

    assert globally_blocked_connection is not None
    assert globally_blocked_connection.headers["X-MCP-Readonly"] == "true"

    monkeypatch.setenv("REPO_AGENT_MCP_ALLOW_WRITES", "true")
    get_settings.cache_clear()

    read_connection = github_mcp_connection(allow_writes=False)
    write_connection = github_mcp_connection(allow_writes=True)

    assert read_connection is not None
    assert read_connection.headers["X-MCP-Readonly"] == "true"
    assert write_connection is not None
    assert write_connection.headers["X-MCP-Readonly"] == "false"
    get_settings.cache_clear()


def test_mcp_types_are_adapted_for_the_model() -> None:
    definition = mcp_tool_definition(
        "github",
        Tool(
            name="get_file_contents",
            description="Read a repository file",
            inputSchema={"type": "object", "properties": {"path": {"type": "string"}}},
        ),
    )
    result = mcp_tool_result(
        CallToolResult(content=[TextContent(type="text", text="README contents")]),
        max_chars=10_000,
    )

    assert definition.server == "github"
    assert definition.input_schema["type"] == "object"
    assert "README contents" in result.content
    assert result.is_error is False
from dataclasses import dataclass
from datetime import timedelta

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.types import CallToolResult, PaginatedRequestParams, Tool
from openai import AsyncOpenAI
from prometheus_client import Counter, Histogram
from temporalio import activity

from repo_agent.contracts import (
    InferenceRequest,
    InferenceResult,
    McpToolCallRequest,
    McpToolCallResult,
    McpToolDefinition,
    McpToolList,
    McpToolListRequest,
    ToolCall,
)
from repo_agent.settings import get_settings

INFERENCE_CALLS = Counter(
    "repo_agent_inference_calls_total",
    "Inference Activity executions",
    ["model", "status"],
)
INFERENCE_LATENCY = Histogram(
    "repo_agent_inference_duration_seconds",
    "Inference Activity latency",
    ["model"],
)


@dataclass(frozen=True)
class McpConnection:
    url: str
    headers: dict[str, str]
    writes_enabled: bool


def github_mcp_connection(allow_writes: bool) -> McpConnection | None:
    settings = get_settings()
    if not settings.github_token:
        return None
    writes_enabled = settings.mcp_allow_writes and allow_writes
    return McpConnection(
        url=settings.github_mcp_url,
        headers={
            "Authorization": f"Bearer {settings.github_token}",
            "X-MCP-Toolsets": settings.github_mcp_toolsets,
            "X-MCP-Readonly": str(not writes_enabled).lower(),
            "X-MCP-Lockdown": str(settings.mcp_lockdown).lower(),
        },
        writes_enabled=writes_enabled,
    )


def mcp_tool_definition(server: str, tool: Tool) -> McpToolDefinition:
    return McpToolDefinition(
        server=server,
        name=tool.name,
        description=tool.description or tool.title or tool.name,
        input_schema=tool.inputSchema,
    )


@activity.defn
async def list_mcp_tools(request: McpToolListRequest) -> McpToolList:
    if request.server != "github":
        raise ValueError(f"Unknown MCP server: {request.server}")
    connection = github_mcp_connection(request.allow_writes)
    if connection is None:
        return McpToolList(
            server=request.server,
            tools=[],
            writes_enabled=False,
            status="GitHub MCP is unavailable because GITHUB_TOKEN is not configured.",
        )

    settings = get_settings()
    async with httpx.AsyncClient(
        headers=connection.headers,
        timeout=settings.mcp_timeout_seconds,
    ) as client:
        async with streamable_http_client(connection.url, http_client=client) as streams:
            read_stream, write_stream, _ = streams
            async with ClientSession(
                read_stream,
                write_stream,
                read_timeout_seconds=timedelta(seconds=settings.mcp_timeout_seconds),
            ) as session:
                await session.initialize()
                tools: list[McpToolDefinition] = []
                cursor: str | None = None
                while True:
                    page = await session.list_tools(
                        params=PaginatedRequestParams(cursor=cursor)
                    )
                    tools.extend(mcp_tool_definition(request.server, tool) for tool in page.tools)
                    if page.nextCursor is None:
                        break
                    cursor = page.nextCursor
    return McpToolList(
        server=request.server,
        tools=tools,
        writes_enabled=connection.writes_enabled,
    )


def mcp_tool_result(result: CallToolResult, max_chars: int) -> McpToolCallResult:
    content = result.model_dump_json(by_alias=True, exclude_none=True)
    if len(content) > max_chars:
        content = content[:max_chars] + "\n[tool result truncated]"
    return McpToolCallResult(content=content, is_error=result.isError)


@activity.defn
async def call_mcp_tool(request: McpToolCallRequest) -> McpToolCallResult:
    if request.server != "github":
        raise ValueError(f"Unknown MCP server: {request.server}")
    connection = github_mcp_connection(request.allow_writes)
    if connection is None:
        raise ValueError("GitHub MCP requires GITHUB_TOKEN")

    settings = get_settings()
    async with httpx.AsyncClient(
        headers=connection.headers,
        timeout=settings.mcp_timeout_seconds,
    ) as client:
        async with streamable_http_client(connection.url, http_client=client) as streams:
            read_stream, write_stream, _ = streams
            async with ClientSession(
                read_stream,
                write_stream,
                read_timeout_seconds=timedelta(seconds=settings.mcp_timeout_seconds),
            ) as session:
                await session.initialize()
                result = await session.call_tool(request.name, request.arguments)
    return mcp_tool_result(result, settings.mcp_max_result_chars)


@activity.defn
async def run_inference(request: InferenceRequest) -> InferenceResult:
    settings = get_settings()
    client = AsyncOpenAI(base_url=settings.llm_base_url, api_key=settings.llm_api_key)

    try:
        with INFERENCE_LATENCY.labels(model=request.model).time():
            if request.tools:
                response = await client.chat.completions.create(
                    model=request.model,
                    messages=request.messages,  # type: ignore[arg-type]
                    tools=request.tools,  # type: ignore[arg-type]
                )
            else:
                response = await client.chat.completions.create(
                    model=request.model,
                    messages=request.messages,  # type: ignore[arg-type]
                )
        message = response.choices[0].message
        tool_calls: list[ToolCall] = []
        for tool_call in message.tool_calls or []:
            if tool_call.type != "function":
                continue
            tool_calls.append(
                ToolCall(
                    id=tool_call.id,
                    name=tool_call.function.name,
                    arguments=tool_call.function.arguments,
                )
            )
        if message.content is None and not tool_calls:
            raise ValueError("Inference response did not contain text or tool calls")
        INFERENCE_CALLS.labels(model=request.model, status="success").inc()
        return InferenceResult(
            content=message.content,
            model=response.model,
            tool_calls=tool_calls,
        )
    except Exception:
        INFERENCE_CALLS.labels(model=request.model, status="error").inc()
        raise
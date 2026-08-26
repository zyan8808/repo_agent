from dataclasses import dataclass
from datetime import timedelta
from time import perf_counter

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.types import CallToolResult, PaginatedRequestParams, Tool
from openai import AsyncOpenAI
from opentelemetry import trace
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
MCP_OPERATIONS = Counter(
    "repo_agent_mcp_operations_total",
    "GitHub MCP Activity operations",
    ["operation", "access", "status"],
)
MCP_OPERATION_LATENCY = Histogram(
    "repo_agent_mcp_operation_duration_seconds",
    "GitHub MCP Activity operation latency",
    ["operation", "access"],
)
MCP_RESULTS_TRUNCATED = Counter(
    "repo_agent_mcp_results_truncated_total",
    "GitHub MCP results truncated before entering workflow history",
)
TRACER = trace.get_tracer(__name__)


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
        MCP_OPERATIONS.labels(
            operation="list_tools",
            access="read_only",
            status="unavailable",
        ).inc()
        return McpToolList(
            server=request.server,
            tools=[],
            writes_enabled=False,
            status="GitHub MCP is unavailable because GITHUB_TOKEN is not configured.",
        )

    settings = get_settings()
    access = "read_write" if connection.writes_enabled else "read_only"
    started_at = perf_counter()
    try:
        with TRACER.start_as_current_span(
            "mcp.list_tools",
            attributes={"mcp.server": request.server, "mcp.access": access},
        ) as span:
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
                            tools.extend(
                                mcp_tool_definition(request.server, tool) for tool in page.tools
                            )
                            if page.nextCursor is None:
                                break
                            cursor = page.nextCursor
            span.set_attribute("mcp.tools.count", len(tools))
    except Exception:
        MCP_OPERATIONS.labels(operation="list_tools", access=access, status="error").inc()
        raise
    else:
        MCP_OPERATIONS.labels(operation="list_tools", access=access, status="success").inc()
    finally:
        MCP_OPERATION_LATENCY.labels(operation="list_tools", access=access).observe(
            perf_counter() - started_at
        )
    return McpToolList(
        server=request.server,
        tools=tools,
        writes_enabled=connection.writes_enabled,
    )


def mcp_tool_result(result: CallToolResult, max_chars: int) -> McpToolCallResult:
    content = result.model_dump_json(by_alias=True, exclude_none=True)
    if len(content) > max_chars:
        content = content[:max_chars] + "\n[tool result truncated]"
        MCP_RESULTS_TRUNCATED.inc()
    return McpToolCallResult(content=content, is_error=result.isError)


@activity.defn
async def call_mcp_tool(request: McpToolCallRequest) -> McpToolCallResult:
    if request.server != "github":
        raise ValueError(f"Unknown MCP server: {request.server}")
    connection = github_mcp_connection(request.allow_writes)
    if connection is None:
        raise ValueError("GitHub MCP requires GITHUB_TOKEN")

    settings = get_settings()
    access = "read_write" if connection.writes_enabled else "read_only"
    started_at = perf_counter()
    try:
        with TRACER.start_as_current_span(
            "mcp.call_tool",
            attributes={
                "mcp.server": request.server,
                "mcp.tool.name": request.name,
                "mcp.access": access,
            },
        ) as span:
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
            span.set_attribute("mcp.result.is_error", bool(result.isError))
    except Exception:
        MCP_OPERATIONS.labels(operation="call_tool", access=access, status="error").inc()
        raise
    else:
        status = "error" if result.isError else "success"
        MCP_OPERATIONS.labels(operation="call_tool", access=access, status=status).inc()
    finally:
        MCP_OPERATION_LATENCY.labels(operation="call_tool", access=access).observe(
            perf_counter() - started_at
        )
    return mcp_tool_result(result, settings.mcp_max_result_chars)


@activity.defn
async def run_inference(request: InferenceRequest) -> InferenceResult:
    settings = get_settings()
    client = AsyncOpenAI(base_url=settings.llm_base_url, api_key=settings.llm_api_key)

    try:
        with TRACER.start_as_current_span(
            "llm.inference",
            attributes={
                "gen_ai.operation.name": "chat",
                "gen_ai.request.model": request.model,
                "gen_ai.request.tools.count": len(request.tools or []),
            },
        ) as span:
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
            span.set_attribute("gen_ai.response.model", response.model)
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
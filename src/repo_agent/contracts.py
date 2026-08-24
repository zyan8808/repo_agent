from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AgentRequest:
    prompt: str
    allow_writes: bool = False


@dataclass(frozen=True)
class AgentResult:
    output: str
    model: str


@dataclass(frozen=True)
class InferenceRequest:
    messages: list[dict[str, Any]]
    model: str
    tools: list[dict[str, Any]] | None = None


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: str


@dataclass(frozen=True)
class InferenceResult:
    content: str | None
    model: str
    tool_calls: list[ToolCall]


@dataclass(frozen=True)
class McpToolDefinition:
    server: str
    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass(frozen=True)
class McpToolListRequest:
    server: str
    allow_writes: bool = False


@dataclass(frozen=True)
class McpToolList:
    server: str
    tools: list[McpToolDefinition]
    writes_enabled: bool
    status: str | None = None


@dataclass(frozen=True)
class McpToolCallRequest:
    server: str
    name: str
    arguments: dict[str, Any]
    allow_writes: bool = False


@dataclass(frozen=True)
class McpToolCallResult:
    content: str
    is_error: bool
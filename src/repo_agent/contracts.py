from dataclasses import dataclass


@dataclass(frozen=True)
class AgentRequest:
    prompt: str


@dataclass(frozen=True)
class AgentResult:
    output: str
    model: str


@dataclass(frozen=True)
class InferenceRequest:
    messages: list[dict[str, str]]
    model: str


@dataclass(frozen=True)
class InferenceResult:
    content: str
    model: str
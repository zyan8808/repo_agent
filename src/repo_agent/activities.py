from openai import AsyncOpenAI
from prometheus_client import Counter, Histogram
from temporalio import activity

from repo_agent.contracts import InferenceRequest, InferenceResult
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


@activity.defn
async def run_inference(request: InferenceRequest) -> InferenceResult:
    settings = get_settings()
    client = AsyncOpenAI(base_url=settings.llm_base_url, api_key=settings.llm_api_key)

    try:
        with INFERENCE_LATENCY.labels(model=request.model).time():
            response = await client.chat.completions.create(
                model=request.model,
                messages=request.messages,  # type: ignore[arg-type]
            )
        content = response.choices[0].message.content
        if content is None:
            raise ValueError("Inference response did not contain text")
        INFERENCE_CALLS.labels(model=request.model, status="success").inc()
        return InferenceResult(content=content, model=response.model)
    except Exception:
        INFERENCE_CALLS.labels(model=request.model, status="error").inc()
        raise
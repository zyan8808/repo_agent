from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from time import perf_counter
from typing import cast
from uuid import uuid4

import uvicorn
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import FileResponse
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from prometheus_client import Counter, Histogram, make_asgi_app
from pydantic import BaseModel, Field
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import Response
from starlette.types import ASGIApp
from temporalio.client import Client, WorkflowFailureError

from repo_agent.contracts import AgentRequest, AgentResult
from repo_agent.settings import get_settings
from repo_agent.telemetry import configure_tracing
from repo_agent.workflows import AgentWorkflow

HTTP_REQUESTS = Counter(
    "repo_agent_http_requests_total",
    "HTTP requests handled by the agent API",
    ["method", "route", "status"],
)
HTTP_REQUEST_DURATION = Histogram(
    "repo_agent_http_request_duration_seconds",
    "HTTP request duration for the agent API",
    ["method", "route"],
)
WORKFLOWS_STARTED = Counter(
    "repo_agent_workflows_started_total",
    "Agent workflows accepted by the API",
)


class RunCreate(BaseModel):
    prompt: str = Field(min_length=1, max_length=100_000)
    allow_writes: bool = False


class RunAccepted(BaseModel):
    workflow_id: str


class RunStatus(BaseModel):
    workflow_id: str
    status: str


class RunOutput(BaseModel):
    workflow_id: str
    output: str
    model: str


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    settings = get_settings()
    configure_tracing("repo-agent-api", settings.otlp_endpoint)
    app.state.temporal = await Client.connect(
        settings.temporal_host,
        namespace=settings.temporal_namespace,
    )
    yield


app = FastAPI(title="repo_agent", version="0.1.0", lifespan=lifespan)
app.mount("/metrics", cast(ASGIApp, make_asgi_app()))
FastAPIInstrumentor.instrument_app(app)


@app.middleware("http")
async def record_http_metrics(
    request: Request,
    call_next: RequestResponseEndpoint,
) -> Response:
    started_at = perf_counter()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    finally:
        route = request.scope.get("route")
        route_path = getattr(route, "path", "unmatched")
        HTTP_REQUESTS.labels(
            method=request.method,
            route=route_path,
            status=str(status_code),
        ).inc()
        HTTP_REQUEST_DURATION.labels(method=request.method, route=route_path).observe(
            perf_counter() - started_at
        )


def temporal_client(request: Request) -> Client:
    return cast(Client, request.app.state.temporal)


@app.get("/", include_in_schema=False, response_class=FileResponse)
async def console() -> FileResponse:
    return FileResponse(Path(__file__).parent / "static" / "index.html")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/runs", response_model=RunAccepted, status_code=status.HTTP_202_ACCEPTED)
async def create_run(body: RunCreate, request: Request) -> RunAccepted:
    settings = get_settings()
    workflow_id = f"repo-agent-{uuid4()}"
    await temporal_client(request).start_workflow(
        AgentWorkflow.run,
        AgentRequest(prompt=body.prompt, allow_writes=body.allow_writes),
        id=workflow_id,
        task_queue=settings.temporal_task_queue,
    )
    WORKFLOWS_STARTED.inc()
    return RunAccepted(workflow_id=workflow_id)


@app.get("/runs/{workflow_id}", response_model=RunStatus)
async def get_run(workflow_id: str, request: Request) -> RunStatus:
    description = await temporal_client(request).get_workflow_handle(workflow_id).describe()
    workflow_status = description.status.name.lower() if description.status else "unknown"
    return RunStatus(workflow_id=workflow_id, status=workflow_status)


@app.get("/runs/{workflow_id}/result", response_model=RunOutput)
async def get_run_result(workflow_id: str, request: Request) -> RunOutput:
    handle = temporal_client(request).get_workflow_handle(
        workflow_id,
        result_type=AgentResult,
    )
    try:
        result = await handle.result()
    except WorkflowFailureError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return RunOutput(
        workflow_id=workflow_id,
        output=result.output,
        model=result.model,
    )


def run() -> None:
    uvicorn.run("repo_agent.api:app", host="0.0.0.0", port=8000, reload=False)
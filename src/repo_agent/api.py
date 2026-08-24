from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import cast
from uuid import uuid4

import uvicorn
from fastapi import FastAPI, HTTPException, Request, status
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from prometheus_client import make_asgi_app
from pydantic import BaseModel, Field
from starlette.types import ASGIApp
from temporalio.client import Client, WorkflowFailureError

from repo_agent.contracts import AgentRequest, AgentResult
from repo_agent.settings import get_settings
from repo_agent.telemetry import configure_tracing
from repo_agent.workflows import AgentWorkflow


class RunCreate(BaseModel):
    prompt: str = Field(min_length=1, max_length=100_000)


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


def temporal_client(request: Request) -> Client:
    return cast(Client, request.app.state.temporal)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/runs", response_model=RunAccepted, status_code=status.HTTP_202_ACCEPTED)
async def create_run(body: RunCreate, request: Request) -> RunAccepted:
    settings = get_settings()
    workflow_id = f"repo-agent-{uuid4()}"
    await temporal_client(request).start_workflow(
        AgentWorkflow.run,
        AgentRequest(prompt=body.prompt),
        id=workflow_id,
        task_queue=settings.temporal_task_queue,
    )
    return RunAccepted(workflow_id=workflow_id)


@app.get("/runs/{workflow_id}", response_model=RunStatus)
async def get_run(workflow_id: str, request: Request) -> RunStatus:
    description = await temporal_client(request).get_workflow_handle(workflow_id).describe()
    workflow_status = description.status.name.lower() if description.status else "unknown"
    return RunStatus(workflow_id=workflow_id, status=workflow_status)


@app.get("/runs/{workflow_id}/result", response_model=RunOutput)
async def get_run_result(workflow_id: str, request: Request) -> RunOutput:
    handle = temporal_client(request).get_workflow_handle(workflow_id)
    try:
        result = cast(AgentResult, await handle.result())
    except WorkflowFailureError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return RunOutput(
        workflow_id=workflow_id,
        output=result.output,
        model=result.model,
    )


def run() -> None:
    uvicorn.run("repo_agent.api:app", host="0.0.0.0", port=8000, reload=False)
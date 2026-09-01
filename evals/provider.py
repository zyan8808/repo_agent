"""promptfoo custom provider for repo_agent.

Drives the real HTTP API end to end: submits a run, polls for completion,
and returns the final agent output plus token/cost metadata for assertions
and reporting. This exercises the full stack (FastAPI -> Temporal ->
inference Activity -> MCP Activities), not a mocked shortcut, so a passing
eval run is a real signal about tool-selection and answer quality.

promptfoo python provider contract:
https://www.promptfoo.dev/docs/providers/python/
"""

from __future__ import annotations

import os
from typing import Any

import httpx

BASE_URL = os.environ.get("REPO_AGENT_EVAL_BASE_URL", "http://localhost:8000")
# /runs/{id}/result blocks server-side until the workflow finishes, so the
# client timeout just needs to be longer than the slowest expected run
# (the workflow itself caps inference at 10 min/iteration, 12 iterations max).
RESULT_TIMEOUT_SECONDS = float(os.environ.get("REPO_AGENT_EVAL_TIMEOUT_SECONDS", "600"))


def call_api(prompt: str, options: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    config = options.get("config", {})
    model = config.get("model", "agent-default")
    allow_writes = bool(config.get("allow_writes", False))
    max_total_tokens = int(config.get("max_total_tokens", 25_000))
    max_estimated_cost_usd = float(config.get("max_estimated_cost_usd", 1.0))

    with httpx.Client(base_url=BASE_URL, timeout=30) as client:
        create_response = client.post(
            "/runs",
            json={
                "prompt": prompt,
                "model": model,
                "allow_writes": allow_writes,
                "max_total_tokens": max_total_tokens,
                "max_estimated_cost_usd": max_estimated_cost_usd,
            },
        )
        create_response.raise_for_status()
        workflow_id = create_response.json()["workflow_id"]

        result_response = client.get(
            f"/runs/{workflow_id}/result",
            timeout=RESULT_TIMEOUT_SECONDS,
        )
        if result_response.status_code == 409:
            return {"error": f"Workflow {workflow_id} failed: {result_response.text}"}
        result_response.raise_for_status()

    body = result_response.json()
    return {
        "output": body["output"],
        "tokenUsage": {"total": body.get("total_tokens", 0)},
        "metadata": {
            "workflow_id": workflow_id,
            "model": body.get("model"),
            "estimated_cost_usd": body.get("estimated_cost_usd"),
            "usage_is_estimated": body.get("usage_is_estimated"),
            "allow_writes": allow_writes,
            "max_total_tokens": max_total_tokens,
            "max_estimated_cost_usd": max_estimated_cost_usd,
        },
    }

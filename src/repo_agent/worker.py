import asyncio
import logging

from prometheus_client import start_http_server
from temporalio.client import Client
from temporalio.worker import Worker

from repo_agent.activities import call_mcp_tool, list_mcp_tools, run_inference
from repo_agent.settings import get_settings
from repo_agent.telemetry import configure_tracing
from repo_agent.workflows import AgentWorkflow


async def serve() -> None:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)
    configure_tracing("repo-agent-worker", settings.otlp_endpoint)
    start_http_server(settings.worker_metrics_port)
    client = await Client.connect(
        settings.temporal_host,
        namespace=settings.temporal_namespace,
    )
    worker = Worker(
        client,
        task_queue=settings.temporal_task_queue,
        workflows=[AgentWorkflow],
        activities=[run_inference, list_mcp_tools, call_mcp_tool],
    )
    await worker.run()


def run() -> None:
    asyncio.run(serve())


if __name__ == "__main__":
    run()
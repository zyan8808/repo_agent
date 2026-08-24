# repo_agent

`repo_agent` is a local-first foundation for durable AI agent workflows. It combines a
FastAPI web/API surface, Temporal orchestration, a LiteLLM model gateway, Ollama local
inference, and a complete local observability stack.

The current workflow accepts a text task, runs model inference as a retryable Temporal
Activity, and stores the durable result. It does not yet read, edit, or execute against
repository files automatically; those capabilities can be added as explicit Activities
with appropriate safety and idempotency controls.

## What It Provides

- A browser console for submitting tasks and reviewing recent results
- Durable workflow execution with retries and persisted state
- Local model inference through Ollama, routed by LiteLLM
- Workflow status and result APIs
- Prometheus metrics, OpenTelemetry traces, and a provisioned Grafana dashboard
- Containerized local infrastructure with persistent service data

## Architecture

```mermaid
flowchart LR
	 Browser[Web console] --> API[FastAPI]
	 API --> Temporal[Temporal]
	 Temporal --> Worker[Agent worker]
	 Worker --> LiteLLM[LiteLLM]
	 LiteLLM --> Ollama[Ollama on host]
	 API -. traces .-> OTel[OpenTelemetry Collector]
	 Worker -. traces .-> OTel
	 API -. metrics .-> Prometheus
	 Worker -. metrics .-> Prometheus
	 OTel --> Tempo
	 Prometheus --> Grafana
	 Tempo --> Grafana
```

See [Architecture](docs/architecture.md) for component responsibilities, request flow,
durability boundaries, and extension guidance.

## Prerequisites

- Docker Desktop with Docker Compose v2
- Ollama running on macOS
- Enough memory and disk for the selected model
- `uv` for host-side Python development
- `jq` for the optional command-line examples

The default `qwen3.8:27b` model uses about 17 GB on disk. Select a smaller Ollama model
through `LOCAL_MODEL` when the host cannot run it comfortably.

## Quick Start

1. Install and start Ollama, then pull the configured model:

	```bash
	brew install ollama
	brew services start ollama
	ollama pull qwen3.8:27b
	```

2. Create the local environment file and start the stack:

	```bash
	cp .env.example .env
	docker compose up --build -d
	```

3. Open the agent console:

	**http://localhost:8000/**

Enter a task and select **Run agent**. The console displays workflow state, model output,
and browser-local history. Temporal persists workflow state independently of that browser
history.

## Use the API

Start a workflow:

```bash
response=$(curl --fail --silent --show-error \
  -X POST http://localhost:8000/runs \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"Explain the architecture of this agent service"}')

workflow_id=$(printf '%s' "$response" | jq -r '.workflow_id')
printf '%s\n' "$workflow_id"
```

Check its state and retrieve the result:

```bash
curl --fail --silent "http://localhost:8000/runs/$workflow_id" | jq .
curl --fail --silent "http://localhost:8000/runs/$workflow_id/result" | jq .
```

The result request waits for a running workflow to finish. A failed workflow returns HTTP
`409`; invalid requests use standard FastAPI validation responses.

## Local Services

| Service | Purpose | URL |
| --- | --- | --- |
| Agent console | Submit and inspect agent runs | http://localhost:8000/ |
| API documentation | Interactive OpenAPI documentation | http://localhost:8000/docs |
| Temporal UI | Workflow history and Activity attempts | http://localhost:8080 |
| LiteLLM | OpenAI-compatible local model gateway | http://localhost:4000 |
| Grafana | Provisioned project dashboard and trace exploration | http://localhost:3000/d/repo-agent-overview/repo-agent-overview |
| Prometheus | Metrics queries and target health | http://localhost:9090 |

## Documentation

- [Architecture](docs/architecture.md): components, execution flow, durability, and extension points
- [Operations and configuration](docs/operations.md): environment variables, lifecycle commands, APIs, and troubleshooting
- [Metrics and observability](docs/metrics.md): telemetry pipeline, metric reference, PromQL examples, dashboards, and traces

## Development

Install dependencies and run the project checks:

```bash
uv sync
uv run pytest
uv run ruff check src tests
uv run pyright
```

The main code is organized as follows:

```text
src/repo_agent/
  api.py          HTTP API, web console, and API metrics
  workflows.py    deterministic Temporal workflow definitions
  activities.py   model inference and side effects
  worker.py       Temporal worker process
  telemetry.py    OpenTelemetry trace configuration
  settings.py     environment-backed application settings
configs/          LiteLLM, Prometheus, Tempo, Grafana, and collector config
docs/             architecture, operations, and observability guides
tests/            automated tests
```

## Design Rules

- Keep Temporal workflow code deterministic.
- Put model calls, file access, Git operations, and other side effects in Activities.
- Give mutating Activities idempotency keys before enabling retries.
- Validate repository paths and command inputs before adding repository execution tools.
- Keep secrets in `.env` or a secret manager; `.env` is intentionally ignored by Git.

## Stop or Reset

Stop containers while preserving data:

```bash
docker compose down
```

Delete containers and all local service volumes:

```bash
docker compose down -v
```

The second command permanently removes local Temporal history, Prometheus data, Grafana
state, Tempo traces, and PostgreSQL data. See [Operations and configuration](docs/operations.md)
for safer service-specific commands and troubleshooting steps.
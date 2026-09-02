# repo_agent

`repo_agent` is a local-first foundation for durable AI agent workflows. It combines a
FastAPI web/API surface, Temporal orchestration, a LiteLLM model gateway, Ollama local
inference, and a local metrics and tracing stack.

The workflow accepts a text task, discovers tools from GitHub's official MCP server, runs
each external call as a Temporal Activity, and stores the durable result. MCP provides a
standard capability layer for repository contents, commits, issues, pull requests, users,
and additional GitHub toolsets without requiring a new Activity for each operation.

## What It Provides

- A browser console for submitting tasks and reviewing recent results
- Durable workflow execution with retries and persisted state
- Selectable local Ollama, hosted Anthropic, and hosted OpenAI inference through LiteLLM
- Workflow status and result APIs
- Extensible GitHub tools through the official remote GitHub MCP server
- Read-only operation by default with explicit worker-level and per-run write gates
- Prometheus metrics, OpenTelemetry traces, and a provisioned Grafana dashboard
- Containerized local infrastructure with persistent service data

## Architecture

```mermaid
flowchart TB
	subgraph edge["Client and API gateway"]
		Client["Client<br/>Browser console, REST, or curl"]
		API["API gateway<br/>FastAPI 0.116+ and Uvicorn<br/>Pydantic validation, OpenAPI, HTTP metrics"]
		Client -->|"GET /models<br/>POST /runs<br/>GET status and result"| API
	end

	subgraph backend["Durable backend inference system"]
		Temporal["Workflow engine<br/>Temporal Server 1.28.1<br/>durable history, timers, retries"]
		Worker["Agent worker<br/>Python 3.12 and Temporal SDK 1.15+<br/>repo-agent task queue"]
		Loop["AgentWorkflow<br/>discover tools, infer, invoke tools<br/>maximum 12 inference iterations"]
		Infer["run_inference Activity<br/>OpenAI SDK 2.20+<br/>30 minute timeout, up to 4 attempts"]
		MCP["MCP Activities<br/>MCP SDK 1.29+ and httpx<br/>Streamable HTTP, 3/5 minute timeouts"]

		Temporal <-->|"workflow and Activity tasks"| Worker
		Worker --> Loop
		Loop --> Infer
		Loop --> MCP
	end

	subgraph models["Model catalog and selection"]
		LiteLLM["Model gateway<br/>LiteLLM 1.75+ proxy<br/>OpenAI-compatible API, aliases, provider credentials"]
		Ollama["Local inference<br/>Ollama on macOS<br/>qwen3.8:27b or qwen3:8b"]
		Anthropic["Hosted inference<br/>Anthropic API"]
		OpenAI["Hosted inference<br/>OpenAI API"]

		LiteLLM -->|"agent-default or agent-qwen3-8b"| Ollama
		LiteLLM -->|"agent-anthropic"| Anthropic
		LiteLLM -->|"agent-openai"| OpenAI
	end

	subgraph tools["Repository capability plane"]
		GitHubMCP["GitHub MCP server<br/>tool discovery and typed invocation<br/>token auth, readonly and lockdown headers"]
		GitHub["GitHub APIs and repositories"]
		GitHubMCP --> GitHub
	end

	subgraph data["Persistence"]
		Postgres["PostgreSQL 16<br/>Temporal workflow and Activity history<br/>postgres-data volume"]
	end

	subgraph observe["Tracing and metrics"]
		Collector["OpenTelemetry Collector 0.136<br/>OTLP gRPC and HTTP receivers, batch processor"]
		Prometheus["Prometheus 3.6<br/>15 second scrapes<br/>API, worker, and collector metrics"]
		Tempo["Tempo 2.8<br/>local trace storage<br/>tempo-data volume"]
		Grafana["Grafana 12.1<br/>provisioned dashboard and trace Explore"]

		Collector -->|"OTLP traces"| Tempo
		Prometheus --> Grafana
		Tempo --> Grafana
	end

	API -->|"start, describe, await result"| Temporal
	API -->|"live model catalog, 10 second timeout"| LiteLLM
	Infer -->|"selected alias is fixed for the run"| LiteLLM
	MCP -->|"tools and results, 100,000 character cap"| GitHubMCP
	Temporal -->|"durable state"| Postgres
	API -.->|"FastAPI request spans via OTLP"| Collector
	Worker -.->|"Temporal workflow, Activity, LLM, and MCP spans"| Collector
	API -.->|"/metrics"| Prometheus
	Worker -.->|":9100/metrics"| Prometheus
	Collector -.->|":9464/metrics"| Prometheus
```

See [Architecture](docs/architecture.md) for component responsibilities, request flow,
durability boundaries, design tradeoffs, failure modes, and scaling guidance. See
[Metrics and observability](docs/metrics.md) for metric definitions, PromQL, dashboards,
and the current trace-coverage boundary.

### Design at a Glance

| Decision | Benefit | Tradeoff |
| --- | --- | --- |
| Temporal orchestration | Runs survive worker and API restarts with durable retry state | Additional infrastructure and deterministic workflow constraints |
| LiteLLM aliases | One model API across local and hosted providers | Extra network hop and a central routing dependency |
| Model fixed per run | Predictable privacy, cost, and replay behavior | No automatic provider failover |
| Runtime MCP discovery | Tool schemas can evolve without Python Activity changes | Discovery latency and schemas are recorded per workflow |
| Two write gates | Requires both operator and per-run intent | Ambiguous remote writes still require idempotency or reconciliation |
| Per-run token and cost limits | Stops continued execution after a configured budget is crossed | One call and failed retries can have unreported overage |
| Prometheus plus Tempo | Metrics and traces stay inspectable in the local stack | Local volumes are neither highly available nor long-term storage |

The current design optimizes for understandable local operation and durable execution, not
public multi-tenancy or high availability. The main production gaps are API authentication,
mutation idempotency, exact failed-attempt billing, provider-aware concurrency, and
backed-up state stores.

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
	ollama pull qwen3:8b
	```

2. Create the local environment file, add a fine-grained GitHub token, and start the stack:

	```bash
	cp .env.example .env
	# Edit GITHUB_TOKEN in .env
	docker compose up --build -d
	```

3. Open the agent console:

	**http://localhost:8000/**

Enter a task, choose a model, and select **Run agent**. The model menu is populated from
LiteLLM's live catalog. The console displays workflow state, model output, and browser-local
history. Temporal persists workflow state independently of that browser history.

The checked-in aliases are `agent-default` for the `LOCAL_MODEL` Ollama tag,
`agent-qwen3-8b` for local `qwen3:8b`, `agent-anthropic` for `ANTHROPIC_MODEL`, and
`agent-openai` for `OPENAI_MODEL`. Set the corresponding provider API key in `.env`
before using a hosted option. Selection is manual per run; automatic cross-provider
fallback is not enabled.

Try a repository activity question:

```text
Which repo has the most commits in the past 12 months under user zyan8808?
```

The non-interactive worker authenticates to `https://api.githubcopilot.com/mcp/` with
`GITHUB_TOKEN`. The token is passed only to the worker and is never included in model
messages or Temporal workflow inputs. Grant only the GitHub permissions the agent needs.

## Use the API

List the model aliases currently advertised by LiteLLM:

```bash
curl --fail --silent http://localhost:8000/models | jq .
```

Start a workflow with a selected alias:

```bash
response=$(curl --fail --silent --show-error \
  -X POST http://localhost:8000/runs \
  -H 'Content-Type: application/json' \
	-d '{"prompt":"Explain the architecture of this agent service","model":"agent-qwen3-8b"}')

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
| Promptfoo | Eval results, when `promptfoo view --port 15500` is running | http://localhost:15500 |
| Grafana | Provisioned project dashboard and trace exploration | http://localhost:3000/d/repo-agent-overview/repo-agent-overview |
| Prometheus | Metrics queries and target health | http://localhost:9090 |

## Documentation

- [Architecture](docs/architecture.md): components, execution flow, durability, and extension points
- [Operations and configuration](docs/operations.md): environment variables, lifecycle commands, APIs, and troubleshooting
- [Metrics and observability](docs/metrics.md): telemetry pipeline, metric reference, PromQL examples, dashboards, and traces
- [Evaluation guide](evals/EVALUATION.md): scoring, model matrix, execution, and results

## Evaluation

Install dependencies and run the project checks before evaluating:

```bash
uv sync
uv run pytest
uv run ruff check src tests
uv run pyright
```

Run the live agent eval across both configured Ollama models and the Anthropic and OpenAI
routes after populating their API keys in `.env`:

```bash
cd evals
PATH="$PWD/../.venv/bin:$PATH" npx promptfoo@0.122.0 eval \
	-c promptfooconfig.yaml --no-cache --max-concurrency 2
npx promptfoo@0.122.0 view --port 15500
```

Each of the 20 model/task runs has a 100,000-token and $1 estimated-cost ceiling. Local cases
allow two hours; hosted cases allow 30 minutes. See the [eval guide](evals/EVALUATION.md) for
credentials, timeout rationale, and Markdown report generation.

The latest merged evaluation is
[eval-MRG-2026-09-01T23:21:54](evals/eval-MRG-2026-09-01T23-21-54.md). It combines the
completed default, Qwen, and OpenAI cases from `eval-Lut` with the repaired Anthropic cases
from `eval-gtx`.

| Provider | Model alias | Passed | Pass rate | Agent tokens | Estimated agent cost | Average latency |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| repo-agent-default | `agent-default` | 3/5 | 60% | 74,064 | $0.0000 | 6.8m |
| repo-agent-qwen3-8b | `agent-qwen3-8b` | 4/5 | 80% | 140,437 | $0.0000 | 8.5m |
| repo-agent-anthropic | `agent-anthropic` | 5/5 | 100% | 203,939 | $0.6650 | 34.0s |
| repo-agent-openai | `agent-openai` | 4/5 | 80% | 81,423 | $0.2376 | 21.9s |

Overall, 16 of 20 cases passed, with 2 assertion failures and 2 timeout errors. See the
[evaluation guide](evals/EVALUATION.md) for scoring methodology, source eval details,
budgets, reproduction steps, and historical results.

The 100,000-token change was verified by a focused rerun of the OpenAI owner task:
[eval-CVq-2026-09-01T20:03:39](evals/eval-CVq-2026-09-01T20-03-39.md) passed in 14.3 seconds
using 11,740 tokens. The updated Anthropic credential is not expired, but Anthropic rejects
requests without a workspace selector. Set `ANTHROPIC_WORKSPACE_ID` for multi-workspace
personal or service-account keys; the LiteLLM startup wrapper adds the required provider
header.

## Project Layout

The main code is organized as follows:

```text
src/repo_agent/
  api.py          HTTP API, web console, and API metrics
  workflows.py    deterministic Temporal workflow definitions
  activities.py   model inference and generic MCP client Activities
  worker.py       Temporal worker process
  telemetry.py    OpenTelemetry trace configuration
  settings.py     environment-backed application settings
configs/          LiteLLM, Prometheus, Tempo, Grafana, and collector config
docs/             architecture, operations, and observability guides
tests/            automated tests
```

This uses Python's standard `src` layout. The outer `src/` directory is an import boundary,
not a package; `src/repo_agent/` is the installable `repo_agent` package used by entry points
and imports. Keeping the package below `src/` prevents tests and local commands from
accidentally importing an uninstalled working-tree copy. Flattening these files directly
into `src/` would create top-level modules rather than one coherent package.

## Design Rules

- Keep Temporal workflow code deterministic.
- Put model calls, file access, Git operations, and other side effects in Activities.
- Do not automatically retry mutating MCP tool calls.
- Require both worker configuration and per-run authorization for GitHub writes.
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
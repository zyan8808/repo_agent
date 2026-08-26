# Operations and Configuration

This guide covers local prerequisites, environment settings, service lifecycle commands,
API behavior, dependency management, capacity signals, and common operational failures.
The checked-in Compose topology is a single-host development deployment, not a
high-availability production configuration.

## Local Prerequisites

- Docker Desktop with the Docker daemon running
- Docker Compose v2 (`docker compose`)
- Ollama installed and running on the host
- The `LOCAL_MODEL` tag and any additional local model aliases downloaded in Ollama
- `uv` for running tests and development tools on the host

Verify the main prerequisites:

```bash
docker info
docker compose version
curl --fail http://localhost:11434/api/version
ollama list
```

## Environment Variables

Copy `.env.example` to `.env`. Docker Compose reads this file automatically, and Git
ignores it.

### Compose and LiteLLM

| Variable | Default | Purpose |
| --- | --- | --- |
| `LOCAL_MODEL` | `qwen3.8:27b` | Ollama model routed through the `agent-default` alias |
| `LITELLM_MASTER_KEY` | `local-development` | Authentication key enforced by the LiteLLM gateway |
| `REPO_AGENT_LLM_API_KEY` | `local-development` | API key sent from the API and worker to LiteLLM |
| `ANTHROPIC_API_KEY` | empty | Anthropic credential used only by LiteLLM |
| `ANTHROPIC_MODEL` | `anthropic/claude-sonnet-4-5-20250929` | Model routed through `agent-anthropic` |
| `OPENAI_API_KEY` | empty | OpenAI credential used only by LiteLLM |
| `OPENAI_MODEL` | `openai/gpt-5-mini` | Model routed through `agent-openai` |
| `GITHUB_TOKEN` | empty | Required PAT for the non-interactive GitHub MCP client |
| `GITHUB_MCP_URL` | `https://api.githubcopilot.com/mcp/` | Remote MCP endpoint |
| `GITHUB_MCP_TOOLSETS` | `repos,issues,pull_requests,users` | GitHub MCP capability groups |
| `MCP_ALLOW_WRITES` | `false` | Administrative gate for mutating GitHub tools |
| `MCP_LOCKDOWN` | `true` | Filter untrusted public GitHub content where supported |
| `GEMINI_API_KEY` | empty | Reserved for additional hosted LiteLLM routes |

Provider API keys are passed only to the LiteLLM container. They are not available to the
API or worker containers.

### Application Settings

Application settings use the `REPO_AGENT_` prefix.

| Variable | Host default | Container value |
| --- | --- | --- |
| `REPO_AGENT_TEMPORAL_HOST` | `localhost:7233` | `temporal:7233` |
| `REPO_AGENT_TEMPORAL_NAMESPACE` | `default` | `default` |
| `REPO_AGENT_TEMPORAL_TASK_QUEUE` | `repo-agent` | `repo-agent` |
| `REPO_AGENT_LLM_BASE_URL` | `http://localhost:4000/v1` | `http://litellm:4000/v1` |
| `REPO_AGENT_LLM_API_KEY` | `local-development` | From `.env` |
| `REPO_AGENT_GITHUB_MCP_URL` | `https://api.githubcopilot.com/mcp/` | Same |
| `REPO_AGENT_GITHUB_MCP_TOOLSETS` | `repos,issues,pull_requests,users` | From `.env` |
| `REPO_AGENT_GITHUB_TOKEN` | unset | From `GITHUB_TOKEN` in `.env` |
| `REPO_AGENT_MCP_ALLOW_WRITES` | `false` | From `MCP_ALLOW_WRITES` in `.env` |
| `REPO_AGENT_MCP_LOCKDOWN` | `true` | From `MCP_LOCKDOWN` in `.env` |
| `REPO_AGENT_MCP_TIMEOUT_SECONDS` | `120` | `120` |
| `REPO_AGENT_MCP_MAX_RESULT_CHARS` | `100000` | `100000` |
| `REPO_AGENT_OTLP_ENDPOINT` | `http://localhost:4317` | `http://otel-collector:4317` |
| `REPO_AGENT_WORKER_METRICS_PORT` | `9100` | `9100` |
| `REPO_AGENT_LOG_LEVEL` | `INFO` | `INFO` |

The MCP HTTP/read timeout is distinct from Temporal's Activity start-to-close timeout.
The workflow allows three minutes for discovery and five minutes for a tool call, while
each individual MCP HTTP session uses the 120-second application default. Increasing only
one layer may leave the other as the effective limit.

## Runtime Dependencies

| Service | Hard dependency | Behavior when unavailable |
| --- | --- | --- |
| API | Temporal at startup | Startup fails until a Temporal connection can be established |
| API model routes | LiteLLM | `GET /models` and new `POST /runs` requests return `503` |
| Temporal | PostgreSQL | Durable workflow progress stops when history cannot be persisted |
| Worker | Temporal at startup | No workflow or Activity tasks are polled |
| Inference Activity | LiteLLM and selected provider | Temporal retries up to four attempts, then fails the workflow |
| MCP discovery/calls | GitHub MCP and token | Discovery returns no tools when the token is absent; remote failures are retried |
| Grafana | Prometheus and Tempo | UI starts, but affected panels or trace queries are empty |

Compose health-gates Temporal on PostgreSQL. The API and worker use `restart: on-failure`,
which is convenient locally but is not readiness orchestration: repeated failures still
require inspecting container state and logs.

## Service Lifecycle

Start or rebuild the complete stack:

```bash
docker compose up --build -d
```

Inspect state and logs:

```bash
docker compose ps
docker compose logs --tail=100 api worker litellm
docker compose logs -f api worker
```

Rebuild only application services after source changes:

```bash
docker compose up --build -d api worker
```

Reload Grafana provisioning after dashboard changes:

```bash
docker compose up -d --force-recreate grafana
```

Stop services while preserving volumes:

```bash
docker compose down
```

Delete all local service data only when a full reset is intended:

```bash
docker compose down -v
```

## API Reference

| Method and path | Behavior |
| --- | --- |
| `GET /` | Web console |
| `GET /health` | API liveness response |
| `GET /models` | Return model aliases currently advertised by LiteLLM |
| `POST /runs` | Start from `{ "prompt": "...", "model": "agent-default", "allow_writes": false }` |
| `GET /runs/{workflow_id}` | Return normalized workflow status |
| `GET /runs/{workflow_id}/result` | Wait for and return the typed workflow result |
| `GET /metrics/` | Prometheus exposition endpoint |
| `GET /docs` | Interactive OpenAPI documentation |

Prompts must contain between 1 and 100,000 characters. The model defaults to
`agent-default` and must match the live `/models` catalog. Successful submissions return
HTTP `202`. An unknown model returns HTTP `400`; a failed workflow result returns HTTP
`409`.

## Model Selection

LiteLLM currently advertises these aliases:

| Alias | Provider target |
| --- | --- |
| `agent-default` | Ollama model selected by `LOCAL_MODEL` |
| `agent-qwen3-8b` | Ollama `qwen3:8b` |
| `agent-anthropic` | Anthropic model selected by `ANTHROPIC_MODEL` |
| `agent-openai` | OpenAI model selected by `OPENAI_MODEL` |

The web console loads this list from `GET /models`, so aliases added to
`configs/litellm.yaml` appear without a UI code change. The chosen alias is stored in the
Temporal workflow input and used for every inference step in that run. Routing is manual
per run; the checked-in LiteLLM configuration does not automatically load-balance or fall
back between providers. If the selected target is unavailable, Temporal retries the same
alias; it never moves the run to a provider with a different privacy or cost boundary.

After changing model settings or provider credentials, recreate LiteLLM:

```bash
docker compose up -d --force-recreate litellm
```

## GitHub MCP

The worker uses the official remote GitHub MCP server over Streamable HTTP. Add a
fine-grained token to `.env`:

```dotenv
GITHUB_TOKEN=github_pat_replace_with_your_token
```

Grant only the permissions needed by enabled toolsets. Never place the token in a prompt.
After changing MCP settings, recreate the worker with `docker compose up -d
--force-recreate worker`.

Read-only mode is the default. To permit writes, set `MCP_ALLOW_WRITES=true`, recreate the
worker, and set `allow_writes: true` on the specific API run (or use the console checkbox).
Both gates are required. Write-enabled tool calls are not automatically retried.

## Health Checks

```bash
curl --fail http://localhost:8000/health
curl --fail http://localhost:4000/health/liveliness
curl --fail http://localhost:8080
curl --fail http://localhost:3000/api/health
curl --fail http://localhost:9090/-/ready
curl --fail http://localhost:11434/api/version
```

These probes answer different questions. `/health` confirms that the API process can serve
a request, but does not prove that LiteLLM, Temporal, the worker, GitHub MCP, or a model is
ready. Use a model-catalog request plus a small workflow as an end-to-end readiness test:

```bash
curl --fail http://localhost:8000/models
curl --fail --silent --show-error \
	-X POST http://localhost:8000/runs \
	-H 'Content-Type: application/json' \
	-d '{"prompt":"Reply with ready and do not use tools","model":"agent-default"}'
```

## Capacity and Scaling

The local stack has one API process, one worker process, one LiteLLM gateway, and one
PostgreSQL instance. Before adding replicas, identify the constrained layer:

| Signal | Likely constraint | First response |
| --- | --- | --- |
| API latency rises while inference is stable | API process or client polling volume | Add API replicas or reduce polling frequency |
| Temporal schedule-to-start time rises | Worker capacity | Add workers on the same task queue; add queue metrics first |
| Inference latency rises for local aliases | Ollama compute, memory, or model queue | Use a smaller model or constrain model concurrency |
| Hosted inference returns rate limits | Provider quota or excessive worker concurrency | Apply provider-specific concurrency and backoff |
| MCP calls dominate duration | GitHub latency, pagination, or broad results | Narrow toolsets and requests; add MCP latency metrics |
| Temporal persistence slows | PostgreSQL resources or history growth | Tune or scale PostgreSQL and review workflow-history size |

More workers can increase throughput only while LiteLLM, Ollama, hosted-provider quotas,
GitHub MCP, and PostgreSQL have spare capacity. Unbounded worker scaling can amplify rate
limits and cost. Separate task queues are the next step when inference and repository
Activities need different concurrency limits or worker hardware.

## Deployment and Security Posture

The Compose file binds published ports to loopback, keeps provider keys in LiteLLM, keeps
the GitHub token in the worker, and defaults GitHub MCP to read-only lockdown mode. Those
are useful local boundaries, but opening the host or placing the stack behind a public
load balancer changes the threat model.

Before a shared or public deployment, add:

1. TLS plus authentication and per-user authorization at the API gateway.
2. Request rate limits, prompt/body limits at the edge, and workflow quotas.
3. A secret manager and credential rotation instead of Compose environment injection.
4. Grafana authentication; anonymous Admin access is local-development only.
5. Managed or backed-up PostgreSQL and explicit Prometheus/Tempo retention policies.
6. Network policies that restrict direct access to Temporal, LiteLLM, telemetry ports, and
	 database services.
7. Structured audit logs and provider-supported idempotency for mutating GitHub calls.
8. Alerts for queue, provider, MCP, and workflow-outcome failures.

For the reasoning behind these boundaries, see [Architecture](architecture.md). For the
signals used to operate them, see [Metrics and observability](metrics.md).

## Troubleshooting

### Ollama Reports an Invalid or Missing Model

Confirm the `.env` name exactly matches an installed tag:

```bash
grep '^LOCAL_MODEL=' .env
ollama list
```

Pull a missing model, then recreate LiteLLM:

```bash
ollama pull qwen3.8:27b
ollama pull qwen3:8b
docker compose up -d --force-recreate litellm
```

### Anthropic Requests Fail

Confirm `ANTHROPIC_API_KEY` is set in `.env` and `ANTHROPIC_MODEL` names a model available
to that account. Recreate LiteLLM after changing either value, then inspect only its logs:

```bash
docker compose up -d --force-recreate litellm
docker compose logs --tail=100 litellm
```

### OpenAI Requests Fail

Confirm `OPENAI_API_KEY` is set in `.env` and `OPENAI_MODEL` names a model available to
that OpenAI project. Recreate LiteLLM after changing either value, then inspect its logs:

```bash
docker compose up -d --force-recreate litellm
docker compose logs --tail=100 litellm
```

### A Workflow Stays Running

Check the Temporal UI first, then worker and LiteLLM logs:

```bash
docker compose logs --tail=200 worker litellm
```

Temporal shows every Activity attempt and retry delay. Initial model loading can take
significantly longer than later requests.

### GitHub MCP Is Unavailable

Check worker logs for authentication or Streamable HTTP errors. Confirm `GITHUB_TOKEN` is
non-empty and has access to the requested repositories, then recreate the worker. Tool
availability is controlled by `GITHUB_MCP_TOOLSETS` and the token's permissions.

### The API Does Not Start

The API connects to Temporal during startup. Confirm PostgreSQL is healthy and Temporal is
running:

```bash
docker compose ps postgres temporal api
docker compose logs --tail=100 postgres temporal api
```

### Port Conflicts

The stack publishes ports `3000`, `3200`, `4000`, `4317`, `4318`, `7233`, `8000`, `8080`,
`9090`, `9100`, and `9464`. Stop the conflicting process or change the relevant Compose
port mapping.

For telemetry-specific diagnosis, see [Metrics and observability](metrics.md).
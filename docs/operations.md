# Operations and Configuration

This guide covers local prerequisites, environment settings, service lifecycle commands,
API behavior, and common operational failures.

## Local Prerequisites

- Docker Desktop with the Docker daemon running
- Docker Compose v2 (`docker compose`)
- Ollama installed and running on the host
- The model named by `LOCAL_MODEL` downloaded in Ollama
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
| `LITELLM_MASTER_KEY` | `local-development` | LiteLLM gateway key used by the worker |
| `REPO_AGENT_LLM_API_KEY` | `local-development` | API key sent from the worker to LiteLLM |
| `GITHUB_TOKEN` | empty | Required PAT for the non-interactive GitHub MCP client |
| `GITHUB_MCP_URL` | `https://api.githubcopilot.com/mcp/` | Remote MCP endpoint |
| `GITHUB_MCP_TOOLSETS` | `repos,issues,pull_requests,users` | GitHub MCP capability groups |
| `MCP_ALLOW_WRITES` | `false` | Administrative gate for mutating GitHub tools |
| `MCP_LOCKDOWN` | `true` | Filter untrusted public GitHub content where supported |
| `OPENAI_API_KEY` | empty | Reserved for optional hosted LiteLLM routes |
| `ANTHROPIC_API_KEY` | empty | Reserved for optional hosted LiteLLM routes |
| `GEMINI_API_KEY` | empty | Reserved for optional hosted LiteLLM routes |

Optional hosted-provider keys are not used by the checked-in LiteLLM model route.

### Application Settings

Application settings use the `REPO_AGENT_` prefix.

| Variable | Host default | Container value |
| --- | --- | --- |
| `REPO_AGENT_TEMPORAL_HOST` | `localhost:7233` | `temporal:7233` |
| `REPO_AGENT_TEMPORAL_NAMESPACE` | `default` | `default` |
| `REPO_AGENT_TEMPORAL_TASK_QUEUE` | `repo-agent` | `repo-agent` |
| `REPO_AGENT_LLM_BASE_URL` | `http://localhost:4000/v1` | `http://litellm:4000/v1` |
| `REPO_AGENT_LLM_API_KEY` | `local-development` | From `.env` |
| `REPO_AGENT_LLM_MODEL` | `agent-default` | `agent-default` |
| `REPO_AGENT_GITHUB_MCP_URL` | `https://api.githubcopilot.com/mcp/` | Same |
| `REPO_AGENT_GITHUB_MCP_TOOLSETS` | `repos,issues,pull_requests,users` | From `.env` |
| `REPO_AGENT_GITHUB_TOKEN` | unset | From `GITHUB_TOKEN` in `.env` |
| `REPO_AGENT_MCP_ALLOW_WRITES` | `false` | From `MCP_ALLOW_WRITES` in `.env` |
| `REPO_AGENT_MCP_LOCKDOWN` | `true` | From `MCP_LOCKDOWN` in `.env` |
| `REPO_AGENT_OTLP_ENDPOINT` | `http://localhost:4317` | `http://otel-collector:4317` |
| `REPO_AGENT_WORKER_METRICS_PORT` | `9100` | `9100` |
| `REPO_AGENT_LOG_LEVEL` | `INFO` | `INFO` |

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
| `POST /runs` | Start from `{ "prompt": "...", "allow_writes": false }` |
| `GET /runs/{workflow_id}` | Return normalized workflow status |
| `GET /runs/{workflow_id}/result` | Wait for and return the typed workflow result |
| `GET /metrics/` | Prometheus exposition endpoint |
| `GET /docs` | Interactive OpenAPI documentation |

Prompts must contain between 1 and 100,000 characters. Successful submissions return
HTTP `202`. A failed workflow result returns HTTP `409`.

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
docker compose up -d --force-recreate litellm
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
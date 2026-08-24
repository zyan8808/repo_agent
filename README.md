# repo_agent

Durable, local-first repository agent built with FastAPI, Temporal, LiteLLM, and
OpenTelemetry.

## Prerequisites

- Docker Desktop
- Ollama running on macOS
- `uv` for host-side Python development

Pull the configured local model before starting the stack:

```bash
ollama pull qwen3.8:27b
```

For machines that cannot comfortably run the 27B model, change `LOCAL_MODEL` in
`.env` and select a smaller Ollama model.

## Start locally

```bash
cp .env.example .env
docker-compose up --build -d
```

The local services are:

| Service | URL |
| --- | --- |
| Agent API and OpenAPI | http://localhost:8000/docs |
| Temporal UI | http://localhost:8080 |
| LiteLLM gateway | http://localhost:4000 |
| Grafana | http://localhost:3000 |
| Prometheus | http://localhost:9090 |

Start an agent run:

```bash
curl -X POST http://localhost:8000/runs \
	-H 'Content-Type: application/json' \
	-d '{"prompt":"Summarize the architecture of this repository"}'
```

Use the returned workflow ID with `/runs/{workflow_id}` and
`/runs/{workflow_id}/result`.

## Development

```bash
uv sync
uv run pytest
uv run ruff check src tests
uv run pyright
```

LLM calls and other side effects belong in Temporal Activities. Workflow code must
remain deterministic. Side-effecting Activities should accept idempotency keys before
they are used for filesystem writes, Git operations, or external mutations.
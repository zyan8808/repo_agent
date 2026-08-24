# Architecture

`repo_agent` separates durable orchestration from side effects. Temporal owns workflow
state and retry behavior, while a worker performs model inference through LiteLLM and
connects to GitHub's official remote MCP server through generic Activities.

## Components

| Component | Responsibility |
| --- | --- |
| Web console | Submits tasks, polls workflow state, displays results, and keeps browser-local history |
| FastAPI service | Validates requests, starts Temporal workflows, exposes results, and publishes API metrics |
| Temporal | Persists workflow history, schedules Activities, and applies retry policies |
| Worker | Registers inference plus generic MCP discovery and invocation Activities |
| GitHub MCP | Publishes typed GitHub tool schemas and executes authorized tool calls |
| LiteLLM | Exposes the `agent-default` model through an OpenAI-compatible API |
| Ollama | Runs the configured local model on the macOS host |
| PostgreSQL | Stores Temporal server state |
| OpenTelemetry Collector | Receives OTLP traces and exports them to Tempo |
| Prometheus | Scrapes application and collector metrics |
| Tempo | Stores distributed traces |
| Grafana | Visualizes Prometheus metrics and provides Tempo exploration |

## Request Flow

1. A client sends a prompt to `POST /runs`.
2. FastAPI assigns a unique `repo-agent-<uuid>` workflow ID.
3. Temporal starts `AgentWorkflow` on the `repo-agent` task queue.
4. The workflow schedules `list_mcp_tools`; the worker negotiates with GitHub MCP and
	returns its current tool schemas.
5. The workflow converts those schemas to OpenAI-compatible function definitions and
	schedules `run_inference`.
6. The model selects a tool; Temporal schedules the generic `call_mcp_tool` Activity.
7. The worker invokes the named tool through MCP Streamable HTTP and returns its typed
	result to workflow history.
8. The workflow sends the result back to the model and repeats for up to 12 iterations.
9. Temporal persists the final response for `/runs/{workflow_id}/result`.

The inference Activity has a ten-minute start-to-close timeout and retries up to four
times with exponential intervals bounded at one minute.

## Durability Boundary

Temporal replays workflow code to reconstruct state. Code in `workflows.py` must therefore
remain deterministic: it should not read the clock directly, generate unmanaged random
values, access files, call network services, or execute commands.

Side effects belong in Activities. This includes:

- LLM requests
- Repository reads and writes
- Git operations
- Shell commands
- Remote API calls
- Notifications

Activities may run more than once after timeouts or worker failures. Any Activity that
mutates state should accept an idempotency key and make repeated execution safe.

## Current Scope

The agent can use any tool exposed by configured GitHub MCP toolsets. The default toolsets
cover repositories, issues, pull requests, and users. Changing `GITHUB_MCP_TOOLSETS`
expands or narrows capabilities without Python changes.

GitHub MCP runs read-only unless the worker has `MCP_ALLOW_WRITES=true` and the individual
run has `allow_writes=true`. Write-enabled tool calls have one Temporal attempt to avoid
automatically repeating a mutation after an ambiguous timeout. Lockdown mode is enabled by
default to reduce prompt-injection exposure from untrusted public GitHub content.

A repository-capable implementation should add narrow Activities rather than broad shell
access. Useful first capabilities include:

1. Read a validated repository-relative file.
2. Search tracked text with explicit result limits.
3. Produce a proposed patch without applying it.
4. Apply an approved patch with an idempotency key.
5. Run allowlisted tests with time and output limits.

Each capability should validate paths, reject traversal outside the workspace, constrain
resource use, and record relevant telemetry.

## Persistence

Docker volumes retain local state across container recreation:

| Volume | Data |
| --- | --- |
| `postgres-data` | Temporal persistence |
| `prometheus-data` | Metrics history |
| `tempo-data` | Trace history |
| `grafana-data` | Grafana database and preferences |

`docker compose down` preserves these volumes. `docker compose down -v` deletes them.
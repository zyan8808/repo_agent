# Metrics and Observability

The local observability stack combines Prometheus metrics, OpenTelemetry traces, Grafana
visualization, and Tempo trace storage. This guide describes telemetry semantics and
operations; the end-to-end system flow is documented in [Architecture](architecture.md).

## Telemetry Surfaces

| Signal | Producer | Transport and collection | Storage and query |
| --- | --- | --- | --- |
| API metrics | FastAPI middleware and Python Prometheus client | Prometheus scrapes `/metrics/` every 15 seconds | Prometheus and Grafana |
| Inference metrics | Temporal worker Activities and Python Prometheus client | Prometheus scrapes `:9100/metrics` every 15 seconds | Prometheus and Grafana |
| MCP metrics | MCP discovery and invocation Activities | Same worker scrape target | Prometheus and Grafana |
| Runtime metrics | Python Prometheus client process collectors | Same API and worker scrape targets | Prometheus and Grafana |
| Distributed traces | FastAPI instrumentation, Temporal interceptor, and Activity child spans | OTLP/gRPC to the collector, then batched OTLP to Tempo | Dashboard trace panel, Tempo, and Grafana Explore |
| Collector metrics | OpenTelemetry Collector Prometheus exporter | Prometheus scrapes `:9464/metrics` | Prometheus and Grafana |

Temporal trace headers connect the API's workflow-start span to worker workflow and
Activity spans. The inference and MCP Activities add child spans around external calls;
payloads and credentials are deliberately excluded.

## Endpoints

| Surface | URL |
| --- | --- |
| Grafana project dashboard | http://localhost:3000/d/repo-agent-overview/repo-agent-overview |
| Prometheus UI | http://localhost:9090 |
| Prometheus targets | http://localhost:9090/targets |
| API metrics | http://localhost:8000/metrics/ |
| Worker metrics | http://localhost:9100/metrics |
| Collector metrics | http://localhost:9464/metrics |
| Tempo API | http://localhost:3200 |

Grafana uses anonymous local Admin access and provisions Prometheus and Tempo data sources
at startup. This configuration is intended for local development only.

## Project Metric Reference

### API Metrics

| Metric | Type | Labels | Meaning |
| --- | --- | --- | --- |
| `repo_agent_http_requests_total` | Counter | `method`, `route`, `status` | Requests completed by the FastAPI service |
| `repo_agent_http_request_duration_seconds` | Histogram | `method`, `route` | End-to-end API request duration |
| `repo_agent_workflows_started_total` | Counter | none | Workflows accepted by `POST /runs` |

The `route` label uses route templates such as `/runs/{workflow_id}` rather than concrete
workflow IDs. This prevents unbounded Prometheus label cardinality. Requests handled by a
mounted ASGI application or redirects may appear as `unmatched`.

### Worker Metrics

| Metric | Type | Labels | Meaning |
| --- | --- | --- | --- |
| `repo_agent_inference_calls_total` | Counter | `model`, `status` | Inference Activity outcomes, where status is `success` or `error` |
| `repo_agent_inference_duration_seconds` | Histogram | `model` | Time spent waiting for LiteLLM inference |
| `repo_agent_inference_tokens_total` | Counter | `model`, `kind` | Provider-reported or estimated prompt/completion tokens; failed attempts use `estimated_failed_prompt` |
| `repo_agent_inference_cost_usd_total` | Counter | `model` | Model-aware estimated cost for successful inference calls |
| `repo_agent_inference_usage_gaps_total` | Counter | `model`, `status` | Attempts without provider-reported usage |

Activity retries produce a metric event for each attempt. An eventual workflow success may
therefore coexist with earlier inference errors.
Successful responses without usage are tokenized locally and marked as estimated in the
API result and trace. For failed attempts, only an estimated prompt count is recorded;
completion usage and billing are unknown and are not folded into the cost counter.

### MCP Metrics

| Metric | Type | Labels | Meaning |
| --- | --- | --- | --- |
| `repo_agent_mcp_operations_total` | Counter | `operation`, `access`, `status` | Discovery and tool-call outcomes per Activity attempt |
| `repo_agent_mcp_operation_duration_seconds` | Histogram | `operation`, `access` | End-to-end GitHub MCP session latency |
| `repo_agent_mcp_results_truncated_total` | Counter | none | Tool results capped before entering workflow history |

`operation` is `list_tools` or `call_tool`; `access` is `read_only` or `read_write`;
`status` is `success`, `error`, or `unavailable`. Tool names are omitted from metrics to
keep cardinality bounded and appear only as trace attributes.

Neither worker metric includes workflow ID, repository, tool name, or provider account.
That keeps cardinality bounded and avoids leaking user input, but it also means Prometheus
cannot reconstruct one run. Use Temporal history for workflow-level diagnosis.

### Runtime Metrics

The Python Prometheus client also publishes process and interpreter metrics, including:

- `process_resident_memory_bytes`
- `process_cpu_seconds_total`
- `process_open_fds`
- `python_gc_collections_total`
- `python_gc_objects_collected_total`

Use the Prometheus `job` label to distinguish `repo-agent-api` and `repo-agent-worker`.

## What the Metrics Answer

| Design question | Current signal | Interpretation |
| --- | --- | --- |
| Is the service reachable? | `up` by scrape job | Distinguishes API, worker, and collector target health |
| Is API demand changing? | HTTP request rate by templated route | Shows client polling and submission load without workflow-ID cardinality |
| Is the API slowing down? | HTTP duration histogram | Includes route handling time; the result route may wait for workflow completion |
| Are runs being accepted? | Workflows-started counter | Counts accepted submissions, not successful completions |
| Is inference healthy? | Inference attempts by `model` and `status` | Counts Activity attempts, so retries increase both traffic and errors |
| Is inference slow? | Inference duration histogram by model alias | Measures worker wait time around the LiteLLM request |
| How quickly are tokens and cost accumulating? | Token-rate and estimated-cost panels by model | Successful missing-usage responses are estimates; failures may be undercounted |
| Is a process resource constrained? | CPU, memory, file descriptor, and GC metrics | Indicates process pressure but not Ollama GPU or model memory usage |

The result endpoint's latency is intentionally different from ordinary API latency: it
waits on `handle.result()`, so its histogram can approximate client-observed workflow wait
time for clients that call it immediately. It is not a durable workflow-duration metric,
because clients can call it late, disconnect, or never call it.

## Grafana Dashboard

The provisioned **repo_agent overview** dashboard contains:

- API and worker scrape health
- Workflows started in the selected range
- API 5xx response count
- Successful inference count
- Inference p95 latency
- API request rate by method, route, and status
- API p95 latency by route
- Inference outcomes by status
- Token rate by model and usage kind
- Estimated inference cost by model
- Missing-usage attempts by model and status
- Recent API, Temporal workflow, Activity, LLM, and MCP traces
- MCP outcomes and p95 latency by operation and access mode
- API and worker resident memory

The default time range is one hour and panels refresh every ten seconds. Newly created
counter series may need two Prometheus scrapes before range functions such as `rate()` or
`increase()` display a value.

Dashboard provisioning is defined by:

- `configs/grafana-datasources.yaml`
- `configs/grafana-dashboards.yaml`
- `configs/dashboards/repo-agent-overview.json`

After editing a provisioned dashboard file, recreate Grafana:

```bash
docker compose up -d --force-recreate grafana
```

## Useful PromQL

Service target health:

```promql
up{job=~"repo-agent-api|repo-agent-worker|otel-collector"}
```

API request rate by route and status:

```promql
sum by (method, route, status) (
  rate(repo_agent_http_requests_total{route!="unmatched"}[5m])
)
```

API p95 latency:

```promql
histogram_quantile(
  0.95,
  sum by (le, method, route) (
    rate(repo_agent_http_request_duration_seconds_bucket[5m])
  )
)
```

Workflow submissions in the last hour:

```promql
sum(increase(repo_agent_workflows_started_total[1h]))
```

Inference attempts by outcome:

```promql
sum by (status) (increase(repo_agent_inference_calls_total[1h]))
```

Inference p95 latency:

```promql
histogram_quantile(
  0.95,
  sum by (le) (rate(repo_agent_inference_duration_seconds_bucket[5m]))
)
```

MCP attempts by operation and outcome:

```promql
sum by (operation, access, status) (
  increase(repo_agent_mcp_operations_total[1h])
)
```

MCP p95 latency:

```promql
histogram_quantile(
  0.95,
  sum by (le, operation, access) (
    rate(repo_agent_mcp_operation_duration_seconds_bucket[15m])
  )
)
```

Resident memory by application process:

```promql
process_resident_memory_bytes{job=~"repo-agent-api|repo-agent-worker"}
```

Five-minute API error ratio:

```promql
sum(rate(repo_agent_http_requests_total{status=~"5.."}[5m]))
/
clamp_min(sum(rate(repo_agent_http_requests_total[5m])), 1e-9)
```

Inference error ratio by selected alias:

```promql
sum by (model) (rate(repo_agent_inference_calls_total{status="error"}[15m]))
/
clamp_min(sum by (model) (rate(repo_agent_inference_calls_total[15m])), 1e-9)
```

Suggested local alert candidates are sustained scrape failure, API 5xx ratio, inference
error ratio, p95 inference latency, resident-memory growth, and file-descriptor pressure.
Thresholds are workload- and model-dependent; establish a baseline before assigning an
SLO or paging policy.

## Traces

FastAPI instrumentation creates server spans with service name `repo-agent-api`, and model
catalog requests add an `llm.list_models` child span. Both Temporal clients install the
OpenTelemetry interceptor, which propagates context through workflow headers and creates
client, workflow, and Activity spans. The worker adds `llm.inference`, `mcp.list_tools`,
and `mcp.call_tool` child spans under the relevant Activity span. The collector exports all
received spans to Tempo.

Use the dashboard's **Recent API and worker traces** panel or Grafana **Explore** with the
Tempo data source. Filter by `service.name` equal to `repo-agent-api` or
`repo-agent-worker`. Trace retention is local and follows the lifecycle of the
`tempo-data` Docker volume.

Span attributes use operational metadata such as model alias, MCP operation, tool name,
access mode, and result status. Do not add prompts, tool arguments/results, credentials,
workflow IDs as metric labels, or arbitrary repository names without a retention and
privacy policy.

OpenTelemetry uses a batch span processor. Batching lowers request overhead but can lose
recent spans on abrupt process termination. The current code also uses the default sampler,
which is appropriate for local volume but needs an explicit sampling and retention policy
before higher-throughput deployment.

## Coverage Gaps

The current telemetry intentionally remains small. A production-oriented iteration should
add the following in priority order:

1. Workflow completion, failure, cancellation, and durable end-to-end duration metrics.
2. Temporal schedule-to-start latency and task-queue backlog for worker capacity planning.
3. Provider rate-limit responses, exact failed-attempt billing, and time to first token.
4. Ollama host CPU, accelerator, memory, queue depth, and model-load duration.
5. PostgreSQL, Temporal Server, Prometheus, Tempo, and container-level health metrics.

Keep labels bounded. Model aliases, operation classes, and status codes are suitable;
prompts, workflow IDs, commit SHAs, repository names, and exception messages are usually
high-cardinality or sensitive and belong in traces or structured logs instead.

## Populate the Dashboard

Start one workflow through the web console or API. A completed run creates workflow and
inference metrics, while normal console polling creates API traffic metrics. Wait at least
one scrape interval before evaluating range queries.

For a lightweight API-only sample:

```bash
for endpoint in health health health openapi.json; do
  curl --fail --silent --output /dev/null "http://localhost:8000/$endpoint"
done
```

## Troubleshooting Empty Panels

1. Confirm all targets are `UP` at http://localhost:9090/targets.
2. Query the metric name directly in Prometheus before debugging Grafana.
3. Expand Grafana's time range and allow at least two scrape intervals for rate panels.
4. Run an agent workflow to create inference and workflow series.
5. Check provisioning and scrape logs:

   ```bash
   docker compose logs --tail=100 grafana prometheus otel-collector
   ```

6. Confirm the application endpoints expose data:

   ```bash
   curl --fail http://localhost:8000/metrics/
   curl --fail http://localhost:9100/metrics
   ```

If Grafana has no dashboard at all, recreate it so file provisioning runs. Do not delete
`grafana-data` unless losing local Grafana state is acceptable.

If metrics exist but traces do not, submit a new workflow after recreating the API and
worker containers. Search Tempo for `service.name = repo-agent-api`, then open its workflow
start span to follow the trace into `repo-agent-worker`. Check collector logs and the
`:9464` target if either service is absent.
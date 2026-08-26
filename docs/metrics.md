# Metrics and Observability

The local observability stack combines Prometheus metrics, OpenTelemetry traces, Grafana
visualization, and Tempo trace storage. This guide describes telemetry semantics and
operations; the end-to-end system flow is documented in [Architecture](architecture.md).

## Telemetry Surfaces

| Signal | Producer | Transport and collection | Storage and query |
| --- | --- | --- | --- |
| API metrics | FastAPI middleware and Python Prometheus client | Prometheus scrapes `/metrics/` every 15 seconds | Prometheus and Grafana |
| Inference metrics | Temporal worker Activities and Python Prometheus client | Prometheus scrapes `:9100/metrics` every 15 seconds | Prometheus and Grafana |
| Runtime metrics | Python Prometheus client process collectors | Same API and worker scrape targets | Prometheus and Grafana |
| API request traces | OpenTelemetry FastAPI instrumentation | OTLP/gRPC to the collector, then batched OTLP to Tempo | Tempo and Grafana Explore |
| Collector metrics | OpenTelemetry Collector Prometheus exporter | Prometheus scrapes `:9464/metrics` | Prometheus and Grafana |

The worker configures an OTLP trace provider, but the current application does not create
worker Activity spans or install a Temporal tracing interceptor. The configured exporter
is therefore plumbing for future instrumentation, not evidence of end-to-end traces.

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

Activity retries produce a metric event for each attempt. An eventual workflow success may
therefore coexist with earlier inference errors.

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

FastAPI instrumentation creates server spans with service name `repo-agent-api`. The API
and worker both configure OTLP trace exporters, and the collector exports received spans
to Tempo. The current worker has no explicit Activity spans, OpenAI/httpx client
instrumentation, or Temporal OpenTelemetry interceptor, so a normal trace ends at the API
boundary rather than following a run through Temporal, LiteLLM, and GitHub MCP.

Use Grafana **Explore**, select the Tempo data source, and filter by service name. Trace
retention is local and follows the lifecycle of the `tempo-data` Docker volume.

To produce a true end-to-end trace, add Temporal client/worker propagation and Activity
spans around model discovery, inference, MCP discovery, and MCP invocation. Span attributes
should use bounded values such as model alias, Activity name, attempt, and status. Do not
attach prompts, tool results, credentials, workflow IDs as metric labels, or arbitrary
repository names without a retention and privacy policy.

OpenTelemetry uses a batch span processor. Batching lowers request overhead but can lose
recent spans on abrupt process termination. The current code also uses the default sampler,
which is appropriate for local volume but needs an explicit sampling and retention policy
before higher-throughput deployment.

## Coverage Gaps

The current telemetry intentionally remains small. A production-oriented iteration should
add the following in priority order:

1. Workflow completion, failure, cancellation, and durable end-to-end duration metrics.
2. Temporal schedule-to-start latency and task-queue backlog for worker capacity planning.
3. MCP discovery/call counts, latency, tool category, truncation, and error status.
4. LiteLLM/provider token counts, rate-limit responses, estimated cost, and time to first
  token where the provider exposes them.
5. Ollama host CPU, accelerator, memory, queue depth, and model-load duration.
6. PostgreSQL, Temporal Server, Prometheus, Tempo, and container-level health metrics.

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

If metrics exist but traces do not, first trigger an API request and search Tempo for
`service.name = repo-agent-api`. Do not expect `repo-agent-worker` Activity spans until
worker instrumentation is implemented.
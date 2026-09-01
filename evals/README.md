# Agent evals

Golden-task regression suite for `repo_agent`'s tool-calling loop, run with
[promptfoo](https://www.promptfoo.dev/). Unlike the unit tests in `tests/`,
these hit the live API and exercise the full path: FastAPI -> Temporal
workflow -> inference Activity -> GitHub MCP Activity -> back through the
model.

## What it checks

- **Grounding** — does the agent actually call MCP tools for facts instead
  of guessing?
- **Safety** — does it respect the read-only default instead of claiming a
  write succeeded?
- **Efficiency** — does it converge on simple questions without excessive
  tool-call iterations?
- **Budgets** — does each run stay within the configured token and estimated-cost limits?
- **Write mode** — does the provider submit every checked-in task as read-only?

## Run it

The suite runs each of its five tasks against every LiteLLM alias:

| Eval provider | LiteLLM alias | Default target |
| --- | --- | --- |
| `repo-agent-default` | `agent-default` | Ollama `qwen3.8:27b` |
| `repo-agent-qwen3-8b` | `agent-qwen3-8b` | Ollama `qwen3:8b` |
| `repo-agent-anthropic` | `agent-anthropic` | `ANTHROPIC_MODEL` |
| `repo-agent-openai` | `agent-openai` | `OPENAI_MODEL` |

Install both local models and populate `GITHUB_TOKEN`, `ANTHROPIC_API_KEY`, and
`OPENAI_API_KEY` in the root `.env`. Hosted evals consume provider credits.

```bash
ollama pull qwen3.8:27b
ollama pull qwen3:8b
docker compose up --build -d
cd evals
PATH="$PWD/../.venv/bin:$PATH" npx promptfoo@0.122.0 eval \
  -c promptfooconfig.yaml --no-cache --max-concurrency 2
npx promptfoo@0.122.0 view --port 15500
```

Open http://localhost:15500 to inspect the stored result. The 20-run matrix executes with
Promptfoo concurrency, so local Ollama providers may compete for host resources.

Set `REPO_AGENT_EVAL_BASE_URL` if the API isn't on `http://localhost:8000`.
Set `REPO_AGENT_EVAL_TIMEOUT_SECONDS` to override the two-hour fallback result timeout.
The two Ollama providers allow two hours per case. Anthropic and OpenAI allow 30 minutes;
hosted calls should normally complete much sooner. Each run is capped at 100,000 tokens and
an estimated $1.00. Concurrency is limited to two because both Ollama routes share one host.
Model-graded assertions use the local `agent-default` LiteLLM route, so filtering the eval
to `repo-agent-default` does not invoke a paid grader.

Export an eval and generate the checked-in Markdown summary from the same Promptfoo record:

```bash
npx promptfoo@0.122.0 export eval <eval-id> --output /tmp/<eval-id>.json
python report.py /tmp/<eval-id>.json --output <eval-id>.md
```

The report links back to that eval ID on port `15500`, summarizes each model, and lists all
failed cases. Agent token and cost totals are kept separate from rubric-grader token usage.

## Latest result

The September 1, 2026 merged evaluation contains all 20 model/task combinations with 16
passes, 2 assertion failures, and 2 timeout errors. It used 499,863 agent tokens plus 14,653
grader tokens at an estimated agent cost of $0.9027. See the
[full report](eval-MRG-2026-09-01T23-21-54.md) or open eval
`eval-MRG-2026-09-01T23:21:54` in the Promptfoo server on port `15500`.

The merged record uses the completed default, Qwen, and OpenAI cases from `eval-Lut` and the
five repaired Anthropic cases from `eval-gtx`. Its 147.2-minute duration is the cumulative
duration of those source runs, not the wall time of one concurrent execution. Model results
were 3/5 for `agent-default`, 4/5 for `agent-qwen3-8b`, 5/5 for `agent-anthropic`, and 4/5 for
`agent-openai`.

The checked-in configuration allows two hours for local cases and 30 minutes for hosted
cases, with a 100,000-token ceiling. Anthropic personal or service-account keys that span
multiple workspaces require `ANTHROPIC_WORKSPACE_ID`; the LiteLLM startup wrapper injects
that value as the `anthropic-workspace-id` provider header.

A focused rerun of the formerly over-budget OpenAI owner task passed all assertions in 14.3
seconds using 11,740 tokens. See [eval-CVq-2026-09-01T20:03:39](eval-CVq-2026-09-01T20-03-39.md).
The replacement Anthropic credential reached Anthropic but returned HTTP `400` because it
requires a workspace ID. The merged run confirms that configuring the workspace ID resolves
the failure: all five Anthropic cases passed.

## Adding a task

Add an entry to `tests:` in `promptfooconfig.yaml`. Prefer `llm-rubric`
assertions for open-ended answers and `icontains`/`latency` for anything
checkable mechanically — mechanical checks are cheaper and don't add a
second model call's worth of nondeterminism to your eval signal.

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
  -c promptfooconfig.yaml --no-cache --max-concurrency 4
npx promptfoo@0.122.0 view --port 15500
```

Open http://localhost:15500 to inspect the stored result. The 20-run matrix executes with
Promptfoo concurrency, so local Ollama providers may compete for host resources.

Set `REPO_AGENT_EVAL_BASE_URL` if the API isn't on `http://localhost:8000`.
Set `REPO_AGENT_EVAL_TIMEOUT_SECONDS` to override the provider's one-hour result timeout.
The checked-in providers cap each run at 50,000 tokens and an estimated $1.00.
Model-graded assertions use the local `agent-default` LiteLLM route, so filtering the eval
to `repo-agent-default` does not invoke a paid grader.

Export an eval and generate the checked-in Markdown summary from the same Promptfoo record:

```bash
npx promptfoo@0.122.0 export eval <eval-id> --output /tmp/<eval-id>.json
python report.py /tmp/<eval-id>.json --output <eval-id>.md
```

The report links back to that eval ID on port `15500`, summarizes each model, and lists all
failed cases. Agent token and cost totals are kept separate from rubric-grader token usage.

## Adding a task

Add an entry to `tests:` in `promptfooconfig.yaml`. Prefer `llm-rubric`
assertions for open-ended answers and `icontains`/`latency` for anything
checkable mechanically — mechanical checks are cheaper and don't add a
second model call's worth of nondeterminism to your eval signal.

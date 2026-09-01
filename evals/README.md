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

## Run it

```bash
docker compose up --build -d
cd evals
npx promptfoo eval
npx promptfoo view
```

Set `REPO_AGENT_EVAL_BASE_URL` if the API isn't on `http://localhost:8000`.

## Adding a task

Add an entry to `tests:` in `promptfooconfig.yaml`. Prefer `llm-rubric`
assertions for open-ended answers and `icontains`/`latency` for anything
checkable mechanically — mechanical checks are cheaper and don't add a
second model call's worth of nondeterminism to your eval signal.

import importlib.util
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

REPORT_PATH = Path(__file__).parents[1] / "evals" / "report.py"
SPEC = importlib.util.spec_from_file_location("eval_report", REPORT_PATH)
assert SPEC is not None and SPEC.loader is not None
REPORT_MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(REPORT_MODULE)
render_report = cast(Callable[[dict[str, Any], str], str], REPORT_MODULE.render_report)


def test_render_report_summarizes_models_and_failures() -> None:
    exported_eval = {
        "evalId": "eval-example",
        "config": {
            "description": "example suite",
            "providers": [
                {
                    "label": "repo-agent-default",
                    "config": {"model": "agent-default", "max_total_tokens": 50_000},
                },
                {
                    "label": "repo-agent-openai",
                    "config": {"model": "agent-openai", "max_total_tokens": 50_000},
                },
            ],
        },
        "results": {
            "timestamp": "2026-09-01T00:00:00.000Z",
            "stats": {"successes": 1, "failures": 1, "errors": 1, "durationMs": 90_000},
            "results": [
                {
                    "success": True,
                    "provider": {"label": "repo-agent-default"},
                    "latencyMs": 10_000,
                    "tokenUsage": {"total": 1_000, "assertions": {"total": 100}},
                    "response": {"metadata": {"estimated_cost_usd": 0}},
                    "testCase": {"description": "passes"},
                    "gradingResult": {"reason": "All assertions passed"},
                },
                {
                    "success": False,
                    "provider": {"label": "repo-agent-openai"},
                    "latencyMs": 20_000,
                    "tokenUsage": {"total": 2_000, "assertions": {"total": 200}},
                    "response": {"metadata": {"estimated_cost_usd": 0.25}},
                    "testCase": {"description": "fails"},
                    "gradingResult": {"reason": "Expected grounded output"},
                },
                {
                    "success": False,
                    "provider": {"label": "repo-agent-openai"},
                    "latencyMs": 30_000,
                    "tokenUsage": {"total": 0},
                    "response": {"error": "Provider authentication failed"},
                    "testCase": {"description": "provider error"},
                    "gradingResult": None,
                },
            ],
        },
    }

    report = render_report(exported_eval, "http://localhost:15500")

    assert "[​" not in report
    assert "[`eval-example`](http://localhost:15500/eval/eval-example)" in report
    assert "| 1 | 1 | 1 | 33% | 3,000 | 300 | $0.2500 | 1.5m |" in report
    assert "| repo-agent-default | `agent-default` | 1/1 | 100%" in report
    assert "| repo-agent-openai | `agent-openai` | 0/2 | 0%" in report
    assert "Expected grounded output" in report
    assert "Provider authentication failed" in report
    assert "## Failures and Errors" in report
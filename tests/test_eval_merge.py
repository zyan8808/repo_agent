import importlib.util
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

MODULE_PATH = Path(__file__).parents[1] / "evals" / "merge.py"
SPEC = importlib.util.spec_from_file_location("eval_merge", MODULE_PATH)
assert SPEC and SPEC.loader
MERGE_MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MERGE_MODULE)
merge_exports = cast(Callable[..., dict[str, Any]], MERGE_MODULE.merge_exports)


def _export(eval_id: str, provider: str, passed: int, errors: int, tokens: int) -> dict[str, Any]:
    return {
        "evalId": eval_id,
        "metadata": {},
        "results": {
            "timestamp": "2026-09-01T00:00:00Z",
            "results": [{"provider": {"label": provider}, "success": bool(passed)}],
            "prompts": [
                {
                    "provider": provider,
                    "metrics": {
                        "testPassCount": passed,
                        "testFailCount": 0,
                        "testErrorCount": errors,
                        "tokenUsage": {"total": tokens, "assertions": {"total": tokens // 2}},
                    },
                }
            ],
            "stats": {"durationMs": 100},
        },
    }


def test_merge_exports_replaces_provider_and_recomputes_stats() -> None:
    base = _export("base", "old-provider", 1, 0, 10)
    base["results"]["results"].append(
        {"provider": {"label": "new-provider"}, "success": False}
    )
    base["results"]["prompts"].append(
        {
            "provider": "new-provider",
            "metrics": {
                "testPassCount": 0,
                "testFailCount": 0,
                "testErrorCount": 1,
                "tokenUsage": {"total": 0, "assertions": {"total": 0}},
            },
        }
    )
    replacement = _export("replacement", "new-provider", 1, 0, 20)

    merged = merge_exports(base, replacement, "new-provider", "merged")

    assert merged["evalId"] == "merged"
    assert merged["results"]["stats"]["successes"] == 2
    assert merged["results"]["stats"]["errors"] == 0
    assert merged["results"]["stats"]["tokenUsage"]["total"] == 30
    assert merged["results"]["stats"]["durationMs"] == 200
    assert merged["metadata"]["sourceEvalIds"] == ["base", "replacement"]
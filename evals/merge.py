"""Merge selected provider results from one Promptfoo export into another."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any, cast


def _mapping(value: object) -> dict[str, Any]:
    return cast(dict[str, Any], value) if isinstance(value, dict) else {}


def _provider_label(result: dict[str, Any]) -> str:
    return str(_mapping(result.get("provider")).get("label", ""))


def _sum_token_usage(prompts: list[dict[str, Any]]) -> dict[str, Any]:
    totals: dict[str, Any] = {}
    for prompt in prompts:
        usage = _mapping(_mapping(prompt.get("metrics")).get("tokenUsage"))
        for key, value in usage.items():
            if isinstance(value, (int, float)):
                totals[key] = totals.get(key, 0) + value
            elif isinstance(value, dict):
                nested = totals.setdefault(key, {})
                for nested_key, nested_value in value.items():
                    if isinstance(nested_value, (int, float)):
                        nested[nested_key] = nested.get(nested_key, 0) + nested_value
    return totals


def merge_exports(
    base: dict[str, Any],
    replacement: dict[str, Any],
    provider: str,
    eval_id: str,
) -> dict[str, Any]:
    merged = copy.deepcopy(base)
    base_results = cast(list[dict[str, Any]], base["results"]["results"])
    replacement_results = cast(list[dict[str, Any]], replacement["results"]["results"])
    selected_results = [
        result for result in replacement_results if _provider_label(result) == provider
    ]
    if not selected_results:
        raise ValueError(f"Replacement export has no results for provider {provider!r}")

    base_prompts = cast(list[dict[str, Any]], base["results"]["prompts"])
    replacement_prompts = cast(list[dict[str, Any]], replacement["results"]["prompts"])
    selected_prompts = [
        prompt for prompt in replacement_prompts if prompt.get("provider") == provider
    ]
    if not selected_prompts:
        raise ValueError(f"Replacement export has no prompt metrics for provider {provider!r}")

    results = [result for result in base_results if _provider_label(result) != provider]
    results.extend(copy.deepcopy(selected_results))
    prompts = [prompt for prompt in base_prompts if prompt.get("provider") != provider]
    prompts.extend(copy.deepcopy(selected_prompts))

    successes = sum(
        int(_mapping(prompt.get("metrics")).get("testPassCount", 0)) for prompt in prompts
    )
    failures = sum(
        int(_mapping(prompt.get("metrics")).get("testFailCount", 0)) for prompt in prompts
    )
    errors = sum(
        int(_mapping(prompt.get("metrics")).get("testErrorCount", 0)) for prompt in prompts
    )
    duration = int(_mapping(base["results"].get("stats")).get("durationMs", 0)) + int(
        _mapping(replacement["results"].get("stats")).get("durationMs", 0)
    )

    merged["evalId"] = eval_id
    merged["results"]["timestamp"] = replacement["results"]["timestamp"]
    merged["results"]["results"] = results
    merged["results"]["prompts"] = prompts
    merged["results"]["stats"] = {
        "successes": successes,
        "failures": failures,
        "errors": errors,
        "tokenUsage": _sum_token_usage(prompts),
        "durationMs": duration,
        "evaluationDurationMs": duration,
    }
    metadata = _mapping(merged.get("metadata"))
    metadata["sourceEvalIds"] = [base["evalId"], replacement["evalId"]]
    metadata["replacedProvider"] = provider
    merged["metadata"] = metadata
    return merged


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base", type=Path)
    parser.add_argument("replacement", type=Path)
    parser.add_argument("--provider", required=True)
    parser.add_argument("--eval-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    base = json.loads(args.base.read_text(encoding="utf-8"))
    replacement = json.loads(args.replacement.read_text(encoding="utf-8"))
    merged = merge_exports(base, replacement, args.provider, args.eval_id)
    args.output.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
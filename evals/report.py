"""Render a Promptfoo eval export as a concise Markdown report."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, cast


def _mapping(value: object) -> dict[str, Any]:
    return cast(dict[str, Any], value) if isinstance(value, dict) else {}


def _cell(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ").strip()


def _duration(milliseconds: int | float) -> str:
    seconds = float(milliseconds) / 1_000
    return f"{seconds:.1f}s" if seconds < 60 else f"{seconds / 60:.1f}m"


def render_report(export: dict[str, Any], server_url: str) -> str:
    eval_id = str(export["evalId"])
    result_set = export["results"]
    results: list[dict[str, Any]] = result_set["results"]
    stats: dict[str, Any] = result_set["stats"]
    providers = {provider["label"]: provider for provider in export["config"]["providers"]}
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for result in results:
        grouped[result["provider"]["label"]].append(result)

    successes = int(stats.get("successes", sum(bool(result["success"]) for result in results)))
    failures = int(stats.get("failures", len(results) - successes))
    errors = int(stats.get("errors", 0))
    agent_tokens = sum(int(result.get("tokenUsage", {}).get("total", 0)) for result in results)
    grader_tokens = sum(
        int(result.get("tokenUsage", {}).get("assertions", {}).get("total", 0))
        for result in results
    )
    target_cost = sum(
        float(
            _mapping(_mapping(result.get("response")).get("metadata")).get(
                "estimated_cost_usd"
            )
            or 0
        )
        for result in results
    )

    lines = [
        "# Repo Agent Eval Results",
        "",
        f"Promptfoo eval: [`{eval_id}`]({server_url.rstrip('/')}/eval/{eval_id})  ",
        f"Started: `{result_set['timestamp']}`  ",
        f"Suite: {_cell(export['config'].get('description', ''))}",
        "",
        "## Overall",
        "",
        "| Passed | Failed | Errors | Pass rate | Agent tokens | Grader tokens | "
        "Estimated agent cost | Duration |",
        "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        f"| {successes} | {failures} | {errors} | "
        f"{successes / len(results):.0%} | {agent_tokens:,} | {grader_tokens:,} | "
        f"${target_cost:.4f} | {_duration(stats.get('durationMs', 0))} |",
        "",
        "## Models",
        "",
        "| Provider | Model alias | Passed | Pass rate | Agent tokens | "
        "Estimated agent cost | Average latency | Token limit |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]

    for label, provider in providers.items():
        provider_results = grouped.get(label, [])
        passed = sum(bool(result["success"]) for result in provider_results)
        total = len(provider_results)
        tokens = sum(
            int(result.get("tokenUsage", {}).get("total", 0)) for result in provider_results
        )
        cost = sum(
            float(
                _mapping(_mapping(result.get("response")).get("metadata")).get(
                    "estimated_cost_usd"
                )
                or 0
            )
            for result in provider_results
        )
        average_latency = (
            sum(float(result.get("latencyMs", 0)) for result in provider_results) / total
            if total
            else 0
        )
        config = provider.get("config", {})
        pass_rate = f"{passed / total:.0%}" if total else "not run"
        lines.append(
            f"| {_cell(label)} | `{_cell(config.get('model', ''))}` | {passed}/{total} | "
            f"{pass_rate} | {tokens:,} | ${cost:.4f} | {_duration(average_latency)} | "
            f"{int(config.get('max_total_tokens', 0)):,} |"
        )

    unsuccessful_results = [result for result in results if not result["success"]]
    lines.extend(["", "## Failures and Errors", ""])
    if not unsuccessful_results:
        lines.append("All assertions passed.")
    else:
        lines.extend(
            [
                "| Provider | Test | Reason |",
                "| --- | --- | --- |",
            ]
        )
        for result in unsuccessful_results:
            grading_result = _mapping(result.get("gradingResult"))
            response = _mapping(result.get("response"))
            reason = (
                grading_result.get("reason")
                or result.get("error")
                or response.get("error")
                or "Unknown"
            )
            lines.append(
                f"| {_cell(result['provider']['label'])} | "
                f"{_cell(result['testCase'].get('description', ''))} | {_cell(reason)} |"
            )

    lines.extend(
        [
            "",
            "## Reproduce",
            "",
            "```bash",
            "cd evals",
            "npx promptfoo@0.122.0 eval -c promptfooconfig.yaml",
            f"npx promptfoo@0.122.0 export eval {eval_id} --output /tmp/{eval_id}.json",
            f"python report.py /tmp/{eval_id}.json --output {eval_id}.md",
            "npx promptfoo@0.122.0 view --port 15500",
            "```",
            "",
            "Agent tokens and estimated agent cost come from the repo_agent workflow response. "
            "Grader tokens are reported separately from Promptfoo assertion usage.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("export", type=Path, help="JSON file produced by promptfoo export")
    parser.add_argument("--output", type=Path, required=True, help="Markdown report path")
    parser.add_argument("--server-url", default="http://localhost:15500")
    args = parser.parse_args()

    with args.export.open(encoding="utf-8") as export_file:
        exported_eval: dict[str, Any] = json.load(export_file)
    args.output.write_text(render_report(exported_eval, args.server_url), encoding="utf-8")


if __name__ == "__main__":
    main()
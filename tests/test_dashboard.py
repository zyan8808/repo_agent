import json
from pathlib import Path
from typing import cast


def test_dashboard_exposes_worker_traces_and_mcp_metrics() -> None:
    dashboard_path = Path(__file__).parents[1] / "configs/dashboards/repo-agent-overview.json"
    dashboard = cast(dict[str, object], json.loads(dashboard_path.read_text()))
    panels = cast(list[dict[str, object]], dashboard["panels"])

    panel_ids = [cast(int, panel["id"]) for panel in panels]
    assert len(panel_ids) == len(set(panel_ids))

    trace_panels = [panel for panel in panels if panel["type"] == "traces"]
    assert len(trace_panels) == 1
    trace_targets = cast(list[dict[str, object]], trace_panels[0]["targets"])
    assert trace_targets[0]["queryType"] == "traceql"
    assert "repo-agent-(api|worker)" in cast(str, trace_targets[0]["query"])

    prometheus_queries = " ".join(
        cast(str, target.get("expr", ""))
        for panel in panels
        for target in cast(list[dict[str, object]], panel.get("targets", []))
    )
    assert "repo_agent_mcp_operations_total" in prometheus_queries
    assert "repo_agent_mcp_operation_duration_seconds_bucket" in prometheus_queries
    assert "repo_agent_inference_tokens_total" in prometheus_queries
    assert "repo_agent_inference_cost_usd_total" in prometheus_queries
    assert "repo_agent_inference_usage_gaps_total" in prometheus_queries
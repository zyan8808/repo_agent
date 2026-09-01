from pathlib import Path


def test_console_uses_default_budgets_and_displays_usage() -> None:
    console = (
        Path(__file__).parents[1] / "src/repo_agent/static/index.html"
    ).read_text()

    assert 'id="token-budget"' not in console
    assert 'id="cost-budget"' not in console
    assert "max_total_tokens" not in console
    assert "max_estimated_cost_usd" not in console
    assert "completed.total_tokens" in console
    assert "completed.estimated_cost_usd" in console
    assert "completed.usage_is_estimated" in console
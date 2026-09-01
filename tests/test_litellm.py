from pathlib import Path

import yaml

from repo_agent.litellm import configured_proxy


def test_configured_proxy_adds_anthropic_workspace_header(tmp_path: Path) -> None:
    source = tmp_path / "litellm.yaml"
    source.write_text(
        "model_list:\n"
        "  - model_name: agent-anthropic\n"
        "    litellm_params:\n"
        "      model: anthropic/test\n"
    )

    rendered = configured_proxy(source, "workspace-id")

    config = yaml.safe_load(rendered.read_text())
    assert config["model_list"][0]["litellm_params"]["extra_headers"] == {
        "anthropic-workspace-id": "workspace-id"
    }
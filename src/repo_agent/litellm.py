import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

import yaml


def configured_proxy(config_path: Path, workspace_id: str | None) -> Path:
    config: dict[str, Any] = yaml.safe_load(config_path.read_text())
    if workspace_id:
        for deployment in config.get("model_list", []):
            if deployment.get("model_name") == "agent-anthropic":
                deployment["litellm_params"]["extra_headers"] = {
                    "anthropic-workspace-id": workspace_id
                }

    with NamedTemporaryFile(mode="w", prefix="litellm-", suffix=".yaml", delete=False) as file:
        yaml.safe_dump(config, file)
        return Path(file.name)


def run() -> None:
    config_path = Path(os.getenv("LITELLM_CONFIG_PATH", "/app/config.yaml"))
    runtime_config = configured_proxy(config_path, os.getenv("ANTHROPIC_WORKSPACE_ID"))
    os.execvp("litellm", ["litellm", "--config", str(runtime_config), "--port", "4000"])
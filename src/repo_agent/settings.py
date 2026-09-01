from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="REPO_AGENT_",
        extra="ignore",
    )

    temporal_host: str = "localhost:7233"
    temporal_namespace: str = "default"
    temporal_task_queue: str = "repo-agent"
    llm_base_url: str = "http://localhost:4000/v1"
    llm_api_key: str = "local-development"
    llm_model: str = "agent-default"
    max_total_tokens: int = Field(default=100_000, gt=0)
    max_estimated_cost_usd: float = Field(default=5.0, gt=0)
    github_mcp_url: str = "https://api.githubcopilot.com/mcp/"
    github_mcp_toolsets: str = "repos,issues,pull_requests,users"
    github_token: str | None = None
    mcp_allow_writes: bool = False
    mcp_lockdown: bool = True
    mcp_timeout_seconds: int = 120
    mcp_max_result_chars: int = 100_000
    otlp_endpoint: str = "http://localhost:4317"
    worker_metrics_port: int = 9100
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
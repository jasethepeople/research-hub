import os
from dataclasses import dataclass, field
from pathlib import Path

DEPLOY_DIR = Path(__file__).resolve().parent.parent
DEFAULT_STATE_DIR = "~/.local/share/intel-hub"
DEFAULT_PORT = 8471


def _path_env(name: str, default: str) -> Path:
    return Path(os.environ.get(name, default)).expanduser()


@dataclass(frozen=True)
class Settings:
    deploy_dir: Path = DEPLOY_DIR
    state_dir: Path = field(default_factory=lambda: _path_env("HUB_STATE", DEFAULT_STATE_DIR))
    host: str = field(default_factory=lambda: os.environ.get("HUB_HOST", "127.0.0.1"))
    port: int = field(default_factory=lambda: int(os.environ.get("HUB_PORT", str(DEFAULT_PORT))))
    tier_timeout: float = field(default_factory=lambda: float(os.environ.get("HUB_TIER_TIMEOUT", "12")))
    fourth_pane: bool = field(default_factory=lambda: os.environ.get("HUB_FOURTH_PANE", "0") == "1")
    registry_path: Path = field(
        default_factory=lambda: _path_env("HUB_MCP_SERVERS", str(DEPLOY_DIR / "mcp_servers.json"))
    )


DEFAULT_SETTINGS = Settings()

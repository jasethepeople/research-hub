import os
from dataclasses import dataclass
from pathlib import Path

DEPLOY_DIR = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    deploy_dir: Path = DEPLOY_DIR
    state_dir: Path = Path(os.environ.get("HUB_STATE", "~/.local/share/intel-hub")).expanduser()
    port: int = int(os.environ.get("HUB_PORT", "8471"))
    tier_timeout: float = float(os.environ.get("HUB_TIER_TIMEOUT", "12"))
    fourth_pane: bool = os.environ.get("HUB_FOURTH_PANE", "0") == "1"
    registry_path: Path = Path(os.environ.get("HUB_MCP_SERVERS", str(DEPLOY_DIR / "mcp_servers.json"))).expanduser()


DEFAULT_SETTINGS = Settings()

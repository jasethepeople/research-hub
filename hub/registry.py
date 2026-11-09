import asyncio
import importlib.metadata
import json
import os
import sys
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any

import mcp
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from pydantic import BaseModel, ConfigDict, Field, ValidationError

REQUIRED_TOOLS = {"search", "fetch_page", "pin_result", "pinned", "unpin"}


class TierSpec(BaseModel):
    model_config = ConfigDict(extra="ignore")

    command: str
    args: list[str] = Field(default_factory=list)


class Tier:
    def __init__(self, name: str, spec: TierSpec | None, state: str, detail: str = ""):
        self.name = name
        self.spec = spec
        self.state = state
        self.detail = detail
        self.tools: set[str] = set()
        self._stack: AsyncExitStack | None = None
        self.session: ClientSession | None = None

    async def connect(self, deploy_dir: Path) -> None:
        if self.spec is None:
            return
        args = [arg.replace("{{DEPLOY_DIR}}", str(deploy_dir)) for arg in self.spec.args]
        for arg in args:
            path = Path(arg)
            if path.suffix == ".py" and path.is_absolute() and not path.exists():
                self.state = "absent"
                self.detail = f"Server file does not exist: {path}"
                return
        self._stack = AsyncExitStack()
        try:
            read_stream, write_stream = await self._stack.enter_async_context(
                stdio_client(
                    StdioServerParameters(
                        command=self.spec.command,
                        args=args,
                        env=tier_environment(self.name),
                    )
                )
            )
            self.session = await self._stack.enter_async_context(ClientSession(read_stream, write_stream))
            await self.session.initialize()
            response = await self.session.list_tools()
            self.tools = {tool.name for tool in response.tools}
            missing = REQUIRED_TOOLS - self.tools
            if missing:
                self.state = "degraded"
                self.detail = "Missing tools: " + ", ".join(sorted(missing))
            else:
                self.state = "ok"
                self.detail = ""
        except FileNotFoundError as error:
            self.state = "skipped"
            self.detail = f"Could not start server: {error}"
            await self.close()
        except Exception as error:
            self.state = "degraded"
            self.detail = f"MCP startup failed: {error.__class__.__name__}: {error}"
            await self.close()

    async def close(self) -> None:
        if self._stack is not None:
            try:
                await self._stack.aclose()
            except Exception:
                pass
        self._stack = None
        self.session = None

    async def call(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        if self.session is None:
            raise RuntimeError(self.detail or "Tier is unavailable.")
        if tool_name not in self.tools:
            raise RuntimeError(f"Tier does not expose required tool {tool_name!r}.")
        result = await self.session.call_tool(tool_name, arguments)
        if result.isError:
            text = "; ".join(block.text for block in result.content if hasattr(block, "text"))
            raise RuntimeError(text or f"MCP tool {tool_name!r} returned an error.")
        for block in result.content:
            if hasattr(block, "text"):
                try:
                    return json.loads(block.text)
                except json.JSONDecodeError:
                    return block.text
        if result.structuredContent is not None:
            return result.structuredContent
        return None

    def health(self) -> dict[str, Any]:
        return {"state": self.state, "tools": sorted(self.tools), "note": self.detail}


def tier_environment(name: str) -> dict[str, str]:
    prefix = f"HUB_TIER_{name.upper().replace('-', '_')}__"
    return {
        key[len(prefix) :]: value for key, value in os.environ.items() if key.startswith(prefix) and key[len(prefix) :]
    }


class Registry:
    def __init__(self, registry_path: Path, deploy_dir: Path, timeout: float = 12):
        self.registry_path = registry_path
        self.deploy_dir = deploy_dir
        self.timeout = timeout
        self.tiers: dict[str, Tier] = {}
        self.load_note = ""

    def load(self) -> None:
        self.tiers.clear()
        try:
            raw = json.loads(self.registry_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            self.load_note = f"Registry file does not exist: {self.registry_path}"
            return
        except (OSError, json.JSONDecodeError) as error:
            self.load_note = f"Could not read registry: {error}"
            return
        if not isinstance(raw, dict):
            self.load_note = "Registry root must be a JSON object."
            return
        self.load_note = ""
        for name, value in raw.items():
            if not isinstance(name, str) or not name:
                continue
            try:
                spec = TierSpec.model_validate(value)
            except ValidationError as error:
                self.tiers[name] = Tier(name, None, "skipped", f"Invalid tier configuration: {error}")
                continue
            self.tiers[name] = Tier(name, spec, "skipped", "Not started.")

    async def start(self) -> None:
        if not self.tiers and not self.load_note:
            self.load()

        async def connect_one(tier: Tier) -> None:
            startup_timeout = max(self.timeout, 5.0)
            try:
                await asyncio.wait_for(tier.connect(self.deploy_dir), timeout=startup_timeout)
            except TimeoutError:
                tier.state = "degraded"
                tier.detail = f"MCP startup timed out after {startup_timeout:g} seconds."
                await tier.close()

        await asyncio.gather(*(connect_one(tier) for tier in self.tiers.values()))

    async def close(self) -> None:
        await asyncio.gather(*(tier.close() for tier in self.tiers.values()))

    def health(self) -> dict[str, Any]:
        return {name: tier.health() for name, tier in self.tiers.items()}


def assert_mcp_v1() -> None:
    if not hasattr(mcp, "__version__"):
        try:
            mcp.__version__ = importlib.metadata.version("mcp")
        except importlib.metadata.PackageNotFoundError:
            mcp.__version__ = "unknown"
    version = mcp.__version__
    try:
        major = int(version.split(".", maxsplit=1)[0])
    except (AttributeError, TypeError, ValueError):
        major = 2
    if major >= 2:
        message = f"Unsupported MCP version {version}; this host requires mcp 1.x (mcp<2)."
        print(message, file=sys.stderr)
        raise SystemExit(2)

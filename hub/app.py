import asyncio
from contextlib import asynccontextmanager, suppress
from datetime import datetime
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict, Field

from hub.cache import CACHE_TTL, ResponseCache
from hub.config import DEFAULT_SETTINGS, Settings
from hub.dashboard import DASHBOARD_HTML
from hub.fetch import TIMEOUT_SECONDS, FetchError, fetch_url
from hub.orchestrator import search_all
from hub.registry import Registry, assert_mcp_v1
from hub.storage import Store


class PinRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    item: dict[str, Any]
    expires_at: datetime | None = None


class WatchRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    query: str = Field(min_length=1, max_length=2000)


def create_app(settings: Settings = DEFAULT_SETTINGS) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        assert_mcp_v1()
        settings.state_dir.mkdir(parents=True, exist_ok=True)
        store = Store(settings.state_dir)
        store.initialize()
        registry = Registry(settings.registry_path, settings.deploy_dir, settings.tier_timeout)
        registry.load()
        await registry.start()
        app.state.settings = settings
        app.state.store = store
        app.state.registry = registry
        app.state.cache = ResponseCache(ttl=CACHE_TTL, maxsize=500)

        async def sweep_loop():
            while True:
                await asyncio.sleep(15 * 60)
                await asyncio.to_thread(store.sweep_expired)

        sweeper = asyncio.create_task(sweep_loop())
        try:
            yield
        finally:
            sweeper.cancel()
            with suppress(asyncio.CancelledError):
                await sweeper
            await registry.close()

    app = FastAPI(title="Local Research Hub", lifespan=lifespan)

    @app.get("/", response_class=HTMLResponse)
    async def dashboard():
        return HTMLResponse(DASHBOARD_HTML.replace("__FOURTH_PANE__", "true" if settings.fourth_pane else "false"))

    @app.get("/api/search")
    async def search(query: str = Query(min_length=1), limit: int = Query(default=20, ge=1, le=100)):
        cleaned_query = query.strip()
        if not cleaned_query:
            raise HTTPException(status_code=422, detail="query must not be blank")
        registry: Registry = app.state.registry
        cache: ResponseCache = app.state.cache
        response = await search_all(registry, cache, cleaned_query, limit, settings.tier_timeout)
        return response

    @app.get("/api/health")
    async def health():
        registry: Registry = app.state.registry
        tiers = registry.health()
        reserved = {"tiers", "cache_ttl", "tier_meta"}
        top_level = {name: info for name, info in tiers.items() if name not in reserved}
        collisions = {name: tiers[name] for name in tiers if name in reserved}
        payload: dict[str, Any] = {"tiers": tiers, **top_level, "cache_ttl": CACHE_TTL}
        if collisions:
            payload["tier_meta"] = collisions
        return payload

    @app.get("/api/fetch")
    async def fetch(url: str, internal: bool = False):
        try:
            async with asyncio.timeout(TIMEOUT_SECONDS):
                return await fetch_url(url, internal=internal)
        except FetchError as error:
            raise HTTPException(status_code=error.status_code, detail=str(error)) from error
        except TimeoutError as error:
            raise HTTPException(status_code=504, detail="Fetch timed out after 20 seconds.") from error
        except Exception as error:
            raise HTTPException(status_code=502, detail=f"Fetch failed: {error.__class__.__name__}.") from error

    @app.post("/api/pin")
    async def pin(request: PinRequest):
        store: Store = app.state.store
        try:
            return await asyncio.to_thread(store.pin, request.item, request.expires_at)
        except OverflowError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @app.get("/api/pins")
    async def pins():
        store: Store = app.state.store
        return {"pins": await asyncio.to_thread(store.list_pins)}

    @app.delete("/api/pin/{pin_id}")
    async def unpin(pin_id: str):
        store: Store = app.state.store
        if not await asyncio.to_thread(store.unpin, pin_id):
            raise HTTPException(status_code=404, detail="Pin not found.")
        return {"deleted": True, "id": pin_id}

    @app.get("/api/watch")
    async def watches():
        store: Store = app.state.store
        return {"watches": await asyncio.to_thread(store.list_watches)}

    @app.post("/api/watch")
    async def add_watch(request: WatchRequest):
        store: Store = app.state.store
        query = request.query.strip()
        if not query:
            raise HTTPException(status_code=422, detail="query must not be blank")
        return await asyncio.to_thread(store.add_watch, query)

    return app


app = create_app()


def main():
    assert_mcp_v1()
    import uvicorn

    uvicorn.run(app, host=DEFAULT_SETTINGS.host, port=DEFAULT_SETTINGS.port, log_level="info")

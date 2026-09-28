from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .catalog import CATALOG
from .agents import AGENTS
from .config import ROOT, load_config
from .exchange_log import configure_logging
from .messages import parse_messages
from .service import stream_turn

configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with httpx.AsyncClient(limits=httpx.Limits(max_keepalive_connections=10, keepalive_expiry=120)) as client:
        app.state.http_client = client
        yield


app = FastAPI(title="Jev Intent Router", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")


@app.get("/")
@app.get("/route")
def page() -> FileResponse:
    return FileResponse(ROOT / "static" / "index.html")


@app.get("/api/status")
def status() -> dict:
    config = load_config()
    return {
        "ready": {name: bool(getattr(config, name).api_key.strip()) for name in ("jev", "qwen", "deepseek")},
        "models": {name: getattr(config, name).model for name in ("jev", "qwen", "deepseek")},
        "routes": {route: {"label": value["label"], "description": value["description"], "agent": AGENTS[route].public(config)} for route, value in CATALOG.items()},
    }


@app.post("/api/turn")
async def turn(request: Request):
    origin = request.headers.get("origin")
    if origin and origin != str(request.base_url).rstrip("/"):
        return JSONResponse({"error": "仅接受同源请求"}, status_code=403)
    try:
        payload = await request.json()
        messages = parse_messages(payload.get("messages"))
        config = load_config()
    except (ValueError, TypeError, AttributeError) as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    return StreamingResponse(stream_turn(messages, config, request.app.state.http_client), media_type="application/x-ndjson", headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})

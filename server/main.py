import asyncio
import logging

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware

from server.api.calls import router as calls_router
from server.api.agents import router as agents_router
from server.config import settings
from server.core.call_manager import CallManager
from server.core.agent_manager import AgentManager

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Voice Agent API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(calls_router)
app.include_router(agents_router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.websocket("/v2/web-call/{call_id}")
async def websocket_call(websocket: WebSocket, call_id: str, token: str | None = None) -> None:
    from server.websocket.handler import handle_web_call

    await handle_web_call(websocket, call_id, token)


@app.on_event("startup")
async def startup() -> None:
    CallManager.initialize()
    AgentManager.initialize()
    if settings.discord_bot_token:
        from server.discord_bot.bot import bot

        asyncio.create_task(bot.start(settings.discord_bot_token))
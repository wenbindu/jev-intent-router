import asyncio
import json
from time import perf_counter
from uuid import uuid4
from typing import AsyncIterator

import httpx

from .agents import AGENTS
from .config import Config
from .conversation import routing_history
from .exchange_log import log_trace
from .providers import classify


async def stream_turn(messages: list[dict], config: Config, client: httpx.AsyncClient) -> AsyncIterator[bytes]:
    queue: asyncio.Queue[dict | None] = asyncio.Queue()
    trace_id = str(uuid4())

    def send(**event: object) -> None:
        queue.put_nowait(event)

    async def work() -> None:
        started = perf_counter()
        try:
            log_trace(trace_id, "Jev 上下文", {
                "source_messages": messages,
                "selected_history": routing_history(messages),
                "latest_message": messages[-1],
            })
            send(type="status", text="Jev 正在选择路径")
            route, confidence, timing = await classify(messages, config.jev, client, trace_id)
            selected = AGENTS[route]
            agent = selected.public(config)
            send(type="route", route=route, confidence=confidence, agent=agent)
            send(type="timing", timing=timing)
            answer = await selected.run(messages, config, client, trace_id, send)
            send(type="done", assistant={"role": "assistant", "content": answer}, agent=agent, ends_session=agent["ends_session"], total_ms=round((perf_counter() - started) * 1000))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            send(type="error", message=str(exc) or type(exc).__name__)
        finally:
            queue.put_nowait(None)

    task = asyncio.create_task(work())
    try:
        while (event := await queue.get()) is not None:
            yield (json.dumps(event, ensure_ascii=False) + "\n").encode("utf-8")
    finally:
        if not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

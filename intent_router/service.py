import asyncio
import json
from time import perf_counter
from uuid import uuid4
from typing import AsyncIterator

import httpx

from .agents import HANDLERS
from .config import Config
from .exchange_log import log_trace
from .providers import classify
from .state import TaskState
from .device import device_state, apply_device_result
from .routes import AGENT_ROUTES


async def stream_turn(messages: list[dict], config: Config, client: httpx.AsyncClient, task_state: TaskState | None = None) -> AsyncIterator[bytes]:
    state = task_state or TaskState()
    device = device_state(messages)
    ends_session = False
    queue: asyncio.Queue[dict | None] = asyncio.Queue()
    trace_id = str(uuid4())

    def send(**event: object) -> None:
        nonlocal state, device, ends_session
        if event.get("type") == "tool":
            result = event["result"]
            output = json.loads(result["content"])
            state = state.after_tool(result["name"], output)
            device = apply_device_result(device, output)
            ends_session = output.get("ok") is True and output.get("ends_session") is True
            event.update(task_state=state.public(), device_state=device, ends_session=ends_session)
        queue.put_nowait(event)

    async def work() -> None:
        nonlocal state
        started = perf_counter()
        try:
            send(type="status", text="Jev 正在选择路径")
            proposed_route, confidence, timing = await classify(messages, config.jev, client, trace_id, state, device_state=device)
            threshold = config.route_thresholds[proposed_route]
            route = proposed_route if confidence > threshold else state.fallback_route
            fallback = confidence <= threshold
            log_trace(trace_id, "Jev 阈值决策", {"proposed_route": proposed_route, "confidence": confidence, "threshold": threshold, "selected_route": route, "fallback": fallback, "task_state": state.public()})
            selected = HANDLERS[route]
            agent = selected.public(config)
            send(type="route", route=route, proposed_route=proposed_route, confidence=confidence, threshold=threshold, fallback=fallback, agent=agent, state_before=state.public())
            send(type="timing", timing=timing)
            before = state.public()
            answer = await selected.run(messages, config, client, trace_id, send, context={"task_state": before, "device_state": device})
            if route in AGENT_ROUTES and not fallback:
                state = state.transition(route)
            log_trace(trace_id, "持久任务状态", {"before": before, "after": state.public()})
            send(type="done", assistant={"role": "assistant", "content": answer, "_route": route}, agent=agent, task_state=state.public(), device_state=device, ends_session=ends_session, total_ms=round((perf_counter() - started) * 1000))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            send(type="error", message=str(exc) or type(exc).__name__, task_state=state.public(), device_state=device, ends_session=ends_session)
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

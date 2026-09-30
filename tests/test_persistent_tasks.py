import asyncio
from dataclasses import replace
import json

import httpx
import pytest

from intent_router.agents import HANDLERS
from intent_router.config import Provider, load_config
from intent_router.device import apply_device_result, device_state
from intent_router.providers import classify
from intent_router.routes import ROUTES
from intent_router.service import stream_turn
from intent_router.state import TaskState


def song_history():
    result = HANDLERS["tool_song_play"].execute("{}", [{"role": "user", "content": "播放歌曲"}])
    return [
        {"role": "user", "content": "播放歌曲"},
        {"role": "assistant", "content": None, "tool_calls": [{"id": "previous", "type": "function", "function": {"name": "tool_song_play", "arguments": "{}"}}]},
        {"role": "tool", "tool_call_id": "previous", "name": "tool_song_play", "content": json.dumps(result)},
        {"role": "assistant", "content": "已模拟播放", "_route": "tool_song_play"},
    ]


@pytest.mark.parametrize("route,args,current,fail_answer,expected,ok", [
    ("tool_song_play", {}, "agent_story", False, "tool_song_play", True),
    ("tool_song_play", {}, "agent_story", True, "tool_song_play", True),
    ("tool_song_play", {"unexpected": 1}, "agent_story", False, "agent_story", False),
    ("tool_volume_adjust", {"action": "raise"}, "tool_song_play", True, "tool_song_play", True),
    ("tool_weather", {"location": "北京"}, "tool_song_play", False, "tool_song_play", True),
    ("tool_shutdown", {"reason": "测试"}, "tool_song_play", False, "tool_song_play", True),
    ("tool_song_control", {"action": "next"}, "tool_song_play", False, "tool_song_play", True),
    ("tool_song_control", {"action": "pause"}, "tool_song_play", False, "tool_song_play", True),
    ("tool_song_control", {"action": "stop"}, "tool_song_play", False, None, True),
    ("tool_song_control", {"action": "stop"}, "agent_story", False, "agent_story", True),
    ("tool_goodbye", {"farewell_reply": "再见"}, "tool_song_play", True, None, True),
])
def test_real_tool_pipeline_commits_persistent_task_on_success(monkeypatch, route, args, current, fail_answer, expected, ok):
    messages = [*song_history(), {"role": "user", "content": "测试本轮操作"}]
    provider = Provider("https://test.local", "fake", "test", 30000)
    config = replace(load_config(), deepseek=provider, route_thresholds={key: 0.5 for key in ROUTES})

    async def fake_classify(*values, **kwargs):
        assert values[-1].public() == {"current_task": current}
        assert kwargs["device_state"] == {"volume": 50, "muted": False}
        return route, 0.99, {"name": "Jev", "total_ms": 1}

    monkeypatch.setattr("intent_router.service.classify", fake_classify)

    def respond(request):
        body = json.loads(request.content)
        background = body["messages"][1]["content"]
        assert current in background and '"volume": 50' in background
        if body["tool_choice"] == "required":
            delta = {"tool_calls": [{"index": 0, "id": "c1", "function": {"name": route, "arguments": json.dumps(args)}}]}
        elif fail_answer:
            return httpx.Response(500, json={"error": "test answer failure"})
        else:
            delta = {"content": "测试完成"}
        return httpx.Response(200, text=f'data: {json.dumps({"choices": [{"delta": delta}]})}\n\ndata: [DONE]\n\n')

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            return [json.loads(line) async for line in stream_turn(messages, config, client, TaskState(current))]

    events = asyncio.run(run())
    tool = next(event for event in events if event["type"] == "tool")
    assert json.loads(tool["result"]["content"])["ok"] is ok
    assert tool["task_state"] == {"current_task": expected}
    assert events[-1]["type"] == ("error" if fail_answer else "done")
    assert events[-1]["task_state"] == tool["task_state"]
    if route == "tool_volume_adjust":
        assert tool["device_state"] == {"volume": 60, "muted": False}
        assert events[-1]["device_state"] == tool["device_state"]
    if route == "tool_goodbye":
        assert tool["ends_session"] is True and events[-1]["ends_session"] is True


def test_fallback_never_replays_persistent_tool_or_replaces_it(monkeypatch):
    async def fake_classify(*args, **kwargs):
        return "tool_song_play", 0.2, {"name": "Jev", "total_ms": 1}

    monkeypatch.setattr("intent_router.service.classify", fake_classify)
    provider = Provider("https://test.local", "fake", "qwen", 30000)
    config = replace(load_config(), qwen=provider)

    def respond(request):
        body = json.loads(request.content)
        assert "tools" not in body
        assert "tool_song_play" in body["messages"][1]["content"]
        return httpx.Response(200, text='data: {"choices":[{"delta":{"content":"请说明需要怎样调整。"}}]}\n\ndata: [DONE]\n\n')

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            return [json.loads(line) async for line in stream_turn([*song_history(), {"role": "user", "content": "改改"}], config, client, TaskState("tool_song_play"))]

    events = asyncio.run(run())
    selected = next(event for event in events if event["type"] == "route")
    assert selected["route"] == "agent_chat" and selected["fallback"] is True
    assert not any(event["type"] == "tool" for event in events)
    assert events[-1]["task_state"] == {"current_task": "tool_song_play"}


def test_jev_receives_persistent_tool_background_and_device_json():
    messages = [*song_history(), {"role": "user", "content": "下一首"}]

    def respond(request):
        state = json.loads(request.content)["state"]
        assert state["task_state"] == {"current_task": "tool_song_play"}
        assert state["device_state"] == {"volume": 50, "muted": False}
        assert "tool_song_play" in state["persistent_tasks"]
        assert "tool_weather" not in state["persistent_tasks"]
        return httpx.Response(200, json={"answers": {"route": {"type": "choice", "choice": "tool_song_control", "confidence": 0.99}}})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            return await classify(messages, Provider("https://test.local", "fake", "jev", 30000), client, "test", TaskState("tool_song_play"))

    assert asyncio.run(run())[0] == "tool_song_control"


def test_device_properties_merge_without_task_or_player_fields():
    initial = {"volume": 50, "muted": False}
    changed = apply_device_result(initial, {"ok": True, "device_state": {"volume": 30, "battery": 80}})
    assert changed == {"volume": 30, "muted": False, "battery": 80}
    assert initial == {"volume": 50, "muted": False}
    assert apply_device_result(changed, {"ok": False, "device_state": {"volume": 99}}) == changed
    messages = [{"role": "tool", "content": json.dumps({"ok": True, "device_state": changed})}]
    assert device_state(messages) == changed


def test_failed_volume_command_preserves_last_successful_device_state():
    messages = [
        {"role": "tool", "name": "tool_volume_set", "content": json.dumps({"ok": True, "volume": 35, "muted": False})},
        {"role": "tool", "name": "tool_volume_adjust", "content": json.dumps({"ok": False, "error": "invalid action", "device_state": {"volume": 99}})},
        {"role": "user", "content": "再大点"},
    ]
    assert device_state(messages) == {"volume": 35, "muted": False}
    result = HANDLERS["tool_volume_adjust"].execute('{"action":"raise"}', messages)
    assert result["volume"] == 45
    assert result["device_state"] == {"volume": 45, "muted": False}


@pytest.mark.parametrize("failed_content", ['{"ok":false,"error":"invalid arguments"}', 'not json'])
def test_failed_song_command_does_not_erase_playback(failed_content):
    messages = [
        *song_history(),
        {"role": "user", "content": "无效操作"},
        {"role": "assistant", "content": None, "tool_calls": [{"id": "failed", "type": "function", "function": {"name": "tool_song_control", "arguments": "{}"}}]},
        {"role": "tool", "tool_call_id": "failed", "name": "tool_song_control", "content": failed_content},
        {"role": "assistant", "content": "操作失败"},
        {"role": "user", "content": "暂停歌曲"},
    ]
    result = HANDLERS["tool_song_control"].execute('{"action":"pause"}', messages)
    assert result["ok"] is True
    assert result["playback_state"] == "paused"

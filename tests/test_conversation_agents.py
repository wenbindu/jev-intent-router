import asyncio
from dataclasses import replace
import json

import httpx
import pytest
import yaml

from intent_router.agents import HANDLERS
from intent_router.agents.prompts import AGENT_PROMPTS
from intent_router.config import ROOT, Provider, load_config, save_route_threshold
from intent_router.conversation import dialogue_history, routing_history
from intent_router.main import app
from intent_router.messages import parse_messages
from intent_router.routes import AGENT_ROUTES, ROUTES, TOOL_ROUTES
from intent_router.service import stream_turn
from intent_router.state import TaskState
from intent_router.catalog import CATALOG


def master_messages():
    return parse_messages([
        {"role": "user", "content": "主角是阿蓝，不会飞", "_route": "agent_story"},
        {"role": "assistant", "content": "阿蓝住在山谷里。", "_route": "agent_story"},
        {"role": "user", "content": "把角色的名字改成阿青", "_route": "agent_chat"},
        {"role": "assistant", "content": "好的，叫阿青。", "_route": "agent_chat"},
        {"role": "user", "content": "音量设为30", "_route": "tool_volume_set"},
        {"role": "assistant", "content": None, "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "tool_volume_set", "arguments": '{"value":30}'}}]},
        {"role": "tool", "tool_call_id": "c1", "name": "tool_volume_set", "content": '{"ok":true,"volume":30,"muted":false}'},
        {"role": "assistant", "content": "模拟音量已设为30。", "_route": "tool_volume_set"},
        {"role": "user", "content": "继续", "_route": None},
    ])


@pytest.mark.parametrize("route", AGENT_ROUTES)
def test_each_agent_receives_own_prompt_and_shared_history(route, monkeypatch):
    messages = master_messages()
    provider = Provider("https://example.test", "fake", "qwen-test", 30000)
    config = replace(load_config(), qwen=provider)
    monkeypatch.setattr("intent_router.providers.log_request", lambda *args: None)
    monkeypatch.setattr("intent_router.providers.log_exchange", lambda **kwargs: None)

    def handler(request):
        body = json.loads(request.content)
        assert body["messages"][0] == {"role": "system", "content": AGENT_PROMPTS[route]}
        assert body["messages"][1:] == dialogue_history(messages)
        assert all(not any(key.startswith("_") for key in message) for message in body["messages"])
        assert body["max_tokens"] == 4096
        assert "tools" not in body
        context = json.dumps(body["messages"], ensure_ascii=False)
        assert "阿蓝" in context and "阿青" in context and "不会飞" in context
        assert "volume" in context and "30" in context
        return httpx.Response(200, text='data: {"choices":[{"delta":{"content":"继续回答"}}]}\n\ndata: [DONE]\n\n')

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await HANDLERS[route].run(messages, config, client, "test", lambda **event: None)

    assert asyncio.run(run()) == "继续回答"


def test_shared_history_keeps_long_content_and_does_not_modify_master():
    messages = master_messages()
    messages[1]["content"] = "故事细节" * 2300
    original = json.dumps(messages)
    history = dialogue_history(messages)
    assert history[1]["content"] == messages[1]["content"]
    assert history[:-1] == routing_history(messages)
    assert all(HANDLERS[route].context(messages) == history for route in AGENT_ROUTES)
    assert json.dumps(messages) == original


def test_state_uses_persistent_task_flag_for_agents_and_tools(monkeypatch):
    state = TaskState().transition("agent_story").transition("agent_english")
    assert state.public() == {"current_task": "agent_english"}
    for route in TOOL_ROUTES:
        assert state.transition(route).current_task == (route if CATALOG[route]["persistent_task"] else state.current_task)
    assert TaskState.parse(state.public()) == state
    assert TaskState.parse({"current_task": "tool_song_play"}).current_task == "tool_song_play"
    assert TaskState.parse({"current_task": None}).current_task is None
    for value in ({"current_task": "tool_volume_set"}, {"current_task": "missing"}, {"current_task": []}, {"extra": True}, []):
        with pytest.raises(ValueError):
            TaskState.parse(value)
    monkeypatch.setitem(CATALOG["agent_english"], "persistent_task", False)
    assert TaskState("agent_story").transition("agent_english").current_task == "agent_story"


@pytest.mark.parametrize("proposed,confidence,fail,expected", [
    ("agent_english", 0.9, False, "agent_english"),
    ("tool_song_play", 0.9, False, "agent_story"),
    ("tool_weather", 0.5, False, "agent_story"),
    ("agent_roleplay", 0.9, True, "agent_story"),
])
def test_stream_state_commit_fallback_and_failure(monkeypatch, proposed, confidence, fail, expected):
    config = replace(load_config(), route_thresholds={route: 0.5 for route in ROUTES})
    used = []

    async def classify(*args, **kwargs):
        assert args[-1].current_task == "agent_story"
        return proposed, confidence, {"name": "Jev", "total_ms": 1}

    class Stub:
        def __init__(self, route):
            self.route = route

        def public(self, config):
            return {"name": self.route, "model": "test", "ends_session": False}

        async def run(self, messages, config, client, trace_id, send, context=None):
            used.append(self.route)
            assert context["task_state"] == {"current_task": "agent_story"}
            if fail:
                raise ValueError("generation failed")
            return "完成"

    monkeypatch.setattr("intent_router.service.classify", classify)
    monkeypatch.setattr("intent_router.service.HANDLERS", {route: Stub(route) for route in ROUTES})
    state = TaskState("agent_story")

    async def run():
        async with httpx.AsyncClient() as client:
            return [json.loads(line) async for line in stream_turn(master_messages(), config, client, state)]

    events = asyncio.run(run())
    assert used == [proposed if confidence > 0.5 else "agent_story"]
    assert events[-1]["type"] == ("error" if fail else "done")
    assert events[-1]["task_state"]["current_task"] == expected
    if proposed in TOOL_ROUTES and confidence > 0.5 or fail:
        assert events[-1]["task_state"] == state.public()
    assert state == TaskState("agent_story")


def test_catalog_status_prompts_and_state_api_validation():
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
            data = (await client.get("/api/status")).json()["routes"]
            assert set(data) == set(ROUTES)
            assert set(AGENT_PROMPTS) == set(AGENT_ROUTES)
            for route in AGENT_ROUTES:
                assert data[route]["agent"]["kind"] == "agent"
                assert data[route]["agent"]["persistent_task"] is True
                assert data[route]["prompt"] == AGENT_PROMPTS[route]
            for route in TOOL_ROUTES:
                assert data[route]["agent"]["kind"] == "tool"
                assert data[route]["prompt"] is None
            assert data["tool_song_play"]["agent"]["persistent_task"] is True
            assert data["tool_volume_set"]["agent"]["persistent_task"] is False
            response = await client.post("/api/turn", json={"messages": [{"role": "user", "content": "你好"}], "task_state": {"current_task": "tool_volume_set"}})
            assert response.status_code == 400
    asyncio.run(run())


def test_existing_threshold_names_migrate_without_losing_settings(tmp_path):
    (tmp_path / "config.example.yaml").write_text((ROOT / "config.example.yaml").read_text())
    local = tmp_path / "config.local.yaml"
    local.write_text("route_thresholds:\n  chat: 0.7\n  play_song: 0.8\n  agent_chat: 0.6\njev:\n  api_key: fake-key\n")
    config = load_config(tmp_path)
    assert config.route_thresholds["agent_chat"] == 0.6
    assert config.route_thresholds["tool_song_play"] == 0.8
    assert config.route_thresholds["agent_english"] == 0.5
    save_route_threshold("agent_english", 0.75, tmp_path)
    data = yaml.safe_load(local.read_text())
    assert "chat" not in data["route_thresholds"] and "play_song" not in data["route_thresholds"]
    assert data["route_thresholds"]["tool_song_play"] == 0.8
    assert data["jev"]["api_key"] == "fake-key"

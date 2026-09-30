import asyncio
from dataclasses import replace
import json
from pathlib import Path
from stat import S_IMODE

import httpx
import pytest
import yaml
from loguru import logger

from intent_router.agents import HANDLERS
from intent_router.config import Provider, ROOT, load_config, save_route_threshold
from intent_router.conversation import last_tool_result, routing_history, tool_history
from intent_router.exchange_log import log_exchange, log_request, log_trace
from intent_router.main import app
from intent_router.messages import parse_messages
from intent_router.providers import classify, completion
from intent_router.service import stream_turn


def _tool_turn(route: str, text: str, args: dict, result: dict, number: int) -> list[dict]:
    call_id = f"call-{number}"
    return [
        {"role": "user", "content": text},
        {"role": "assistant", "content": None, "tool_calls": [{"id": call_id, "type": "function", "function": {"name": route, "arguments": json.dumps(args, ensure_ascii=False)}}]},
        {"role": "tool", "content": json.dumps(result, ensure_ascii=False), "tool_call_id": call_id, "name": route},
        {"role": "assistant", "content": "已下发到虚拟设备"},
    ]


def test_repeated_volume_uses_complete_own_turns_and_last_state():
    messages = parse_messages([
        *_tool_turn("tool_volume_set", "音量设为 35", {"value": 35}, {"ok": True, "volume": 35, "muted": False, "dispatch": "tool_volume_set"}, 1),
        *_tool_turn("tool_weather", "北京天气", {"location": "北京"}, {"ok": True, "location": "北京", "current": {"temperature_2m": 27}}, 2),
        *_tool_turn("tool_volume_adjust", "大点", {"action": "raise"}, {"ok": True, "volume": 45, "muted": False, "action": "raise", "dispatch": "tool_volume_adjust"}, 3),
        {"role": "user", "content": "再大点"},
    ])
    context = HANDLERS["tool_volume_adjust"].context(messages)
    assert [m["role"] for m in context] == ["user", "assistant", "tool", "assistant", "user", "assistant", "tool", "assistant", "user"]
    assert [m["content"] for m in context if m["role"] == "user"] == ["音量设为 35", "大点", "再大点"]
    assert "北京" not in json.dumps(context, ensure_ascii=False)
    assert last_tool_result(messages, "tool_volume_adjust")["volume"] == 45
    assert "45" in HANDLERS["tool_volume_adjust"].parameter_instructions(messages)
    assert HANDLERS["tool_volume_adjust"].execute('{"action":"raise"}', messages)["volume"] == 55
    route_context = routing_history(messages)
    assert "tool_volume_adjust" in route_context[-1]["content"] and "45" in route_context[-1]["content"]
    assert [m["role"] for m in HANDLERS["agent_chat"].context(messages)].count("tool") == 0


def test_agent_context_limits_are_local():
    messages = parse_messages([
        *_tool_turn("tool_weather", "北京天气", {"location": "北京"}, {"ok": True, "location": "北京"}, 1),
        *_tool_turn("tool_song_play", "播放晴天", {"title": "晴天", "artist": ""}, {"ok": True, "title": "晴天"}, 2),
        {"role": "user", "content": "上海呢"},
    ])
    assert [m["role"] for m in tool_history(messages, "tool_weather", 2)] == ["user", "assistant", "tool", "assistant", "user"]
    assert "播放晴天" not in json.dumps(HANDLERS["tool_weather"].context(messages), ensure_ascii=False)
    assert "北京天气" in json.dumps(HANDLERS["tool_weather"].context(messages), ensure_ascii=False)


def test_master_messages_keep_route_and_drop_agent_name():
    previous = _tool_turn("tool_volume_adjust", "声音大点", {"action": "raise"}, {"ok": True, "volume": 60}, 1)
    messages = parse_messages([
        *({**message, "_agent": "旧名称", "_route": "tool_volume_adjust"} for message in previous),
        {"role": "user", "content": "再大点", "_route": None},
    ])
    assert all("_agent" not in message for message in messages)
    assert all(message["_route"] == "tool_volume_adjust" for message in messages[:-1])
    assert messages[-1]["_route"] is None
    assert all("_agent" not in message for message in routing_history(messages))
    for route in ("agent_chat", "tool_volume_adjust", "tool_weather", "tool_song_control"):
        assert all("_route" not in message for message in HANDLERS[route].context(messages))
    async def send_unfiltered():
        async with httpx.AsyncClient() as client:
            await completion("qwen", Provider("https://example.test", "test", "qwen", 30000), messages[-1:], "agent_chat", client, "trace")

    with pytest.raises(ValueError, match="未过滤的私有消息字段"):
        asyncio.run(send_unfiltered())


def test_jev_history_keeps_master_conversation_across_turns():
    prior = [message for number in range(7) for message in (
        {"role": "user", "content": f"问题 {number}", "_agent": "聊天 Agent"},
        {"role": "assistant", "content": f"回答 {number}", "_agent": "聊天 Agent"},
    )]
    messages = parse_messages([*prior, {"role": "user", "content": "当前问题", "_agent": None}])
    history = routing_history(messages)
    assert [message["content"] for message in history if message["role"] == "user"] == [f"问题 {number}" for number in range(7)]
    assert len(history) == 14
    assert all("_agent" not in message for message in history)


def test_new_agent_boundaries_and_virtual_dispatch():
    assert HANDLERS["tool_volume_set"].execute('{"value":160}', [{"role": "user", "content": "调到160"}])["volume"] == 100
    assert HANDLERS["tool_song_play"].tool_spec()["function"]["parameters"]["required"] == []
    selection = HANDLERS["tool_song_play"].execute('{"emotion":"calm"}', [{"role": "user", "content": "播放点舒缓的歌"}])
    assert selection["selection"] == {"emotion": "calm"}
    messages = parse_messages([*_tool_turn("tool_song_play", "播放点舒缓的歌", {"emotion": "calm"}, selection, 1), {"role": "user", "content": "下一首"}])
    assert HANDLERS["tool_song_control"].execute('{"action":"next"}', messages)["ok"] is True
    assert HANDLERS["tool_song_control"].execute('{"action":"next"}', [{"role": "user", "content": "下一首"}])["ok"] is False
    assert HANDLERS["tool_goodbye"].context([{"role": "user", "content": "再见"}]) == [{"role": "user", "content": "再见"}]
    assert HANDLERS["tool_goodbye"].execute('{"farewell_reply":"下次见！"}', [{"role": "user", "content": "再见"}])["ends_session"] is True


def test_song_control_playback_state_transitions():
    play = HANDLERS["tool_song_play"].execute("{}", [{"role": "user", "content": "放点歌"}])
    assert play["playback_state"] == "playing"
    history = _tool_turn("tool_song_play", "放点歌", {}, play, 1)
    actions = HANDLERS["tool_song_control"].tool_spec()["function"]["parameters"]["properties"]["action"]["enum"]
    assert actions == ["previous", "next", "replay", "pause", "resume", "stop"]

    def control(action: str) -> dict:
        result = HANDLERS["tool_song_control"].execute(json.dumps({"action": action}), parse_messages([*history, {"role": "user", "content": action}]))
        history.extend(_tool_turn("tool_song_control", action, {"action": action}, result, len(history) + 1))
        return result

    assert control("pause")["playback_state"] == "paused"
    repeated_pause = control("pause")
    assert repeated_pause["ok"] is False and repeated_pause["playback_state"] == "paused"
    assert control("resume")["playback_state"] == "playing"
    assert control("pause")["playback_state"] == "paused"
    for action in ("next", "previous", "replay"):
        assert control(action)["playback_state"] == "playing"
    assert control("stop")["playback_state"] == "stopped"
    after_stop = control("resume")
    assert after_stop["ok"] is False and after_stop["playback_state"] == "stopped"
    assert HANDLERS["tool_song_control"].execute('{"action":"pause"}', [{"role": "user", "content": "暂停"}])["ok"] is False
    with pytest.raises(ValueError, match="action 参数无效"):
        control("exit")


def test_route_threshold_config_and_persistence(tmp_path: Path):
    (tmp_path / "config.example.yaml").write_text((ROOT / "config.example.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    local_path = tmp_path / "config.local.yaml"
    local_path.write_text("server:\n  port: 3107\njev:\n  api_key: test-secret\n", encoding="utf-8")
    assert set(load_config(tmp_path).route_thresholds.values()) == {0.5}
    assert save_route_threshold("tool_song_play", 0.75, tmp_path) == 0.75
    saved = yaml.safe_load(local_path.read_text(encoding="utf-8"))
    assert saved["jev"]["api_key"] == "test-secret" and saved["server"]["port"] == 3107
    assert S_IMODE(local_path.stat().st_mode) == 0o600
    assert saved["route_thresholds"] == {"tool_song_play": 0.75}
    assert load_config(tmp_path).route_thresholds["tool_song_play"] == 0.75
    for invalid in (-0.1, 1.1, True, "0.5", float("nan")):
        with pytest.raises(ValueError, match="0 到 1"):
            save_route_threshold("tool_song_play", invalid, tmp_path)
    with pytest.raises(ValueError, match="未知路由"):
        save_route_threshold("missing", 0.5, tmp_path)
    local_path.write_text("route_thresholds:\n  tool_song_play: 1.1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="0 到 1"):
        load_config(tmp_path)


def test_low_jev_confidence_falls_back_to_chat(monkeypatch, tmp_path: Path):
    used = []

    class StubAgent:
        def __init__(self, name: str):
            self.name = name

        def public(self, config):
            return {"name": self.name, "model": "test", "ends_session": False}

        async def run(self, messages, config, client, trace_id, send, context=None):
            used.append(self.name)
            return self.name

    proposed_confidence = 0.5

    async def fake_classify(*args, **kwargs):
        return "tool_volume_set", proposed_confidence, {"name": "Jev", "total_ms": 1}

    monkeypatch.setattr("intent_router.service.classify", fake_classify)
    monkeypatch.setattr("intent_router.service.HANDLERS", {"tool_volume_set": StubAgent("volume"), "agent_chat": StubAgent("agent_chat")})
    (tmp_path / "config.example.yaml").write_text((ROOT / "config.example.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    config = load_config(tmp_path)

    async def run(current_config):
        async with httpx.AsyncClient() as client:
            return [json.loads(line) async for line in stream_turn([{"role": "user", "content": "声音大点"}], current_config, client)]

    events = asyncio.run(run(config))
    route = next(event for event in events if event["type"] == "route")
    assert route["proposed_route"] == "tool_volume_set" and route["route"] == "agent_chat"
    assert route["threshold"] == 0.5 and route["fallback"] is True and used == ["agent_chat"]
    proposed_confidence = 0.51
    events = asyncio.run(run(config))
    assert next(event for event in events if event["type"] == "route")["route"] == "tool_volume_set"
    assert used[-1] == "volume"
    proposed_confidence = 0.7
    configured = replace(config, route_thresholds={**config.route_thresholds, "tool_volume_set": 0.8})
    events = asyncio.run(run(configured))
    assert next(event for event in events if event["type"] == "route")["route"] == "agent_chat"


def test_jev_choice_request_and_metrics(monkeypatch):
    logged = []
    monkeypatch.setattr("intent_router.providers.log_request", lambda *args: logged.append("request"))
    monkeypatch.setattr("intent_router.providers.log_exchange", lambda **record: logged.append("response"))

    def handler(request: httpx.Request) -> httpx.Response:
        assert logged == ["request"]
        body = json.loads(request.content)
        assert request.url.path.endswith("/systemone")
        assert body["questions"]["route"]["type"] == "choice"
        assert "source_messages" not in json.dumps(body, ensure_ascii=False)
        assert "暂停" in body["questions"]["route"]["criteria"]["tool_song_control"]
        assert "退出歌曲模式" not in body["questions"]["route"]["criteria"]["tool_song_control"]
        assert body["state"]["latest_message"]["content"] == "再大点"
        assert "tool_volume_adjust" in body["state"]["history"][-1]["content"]
        assert json.dumps({"ok": True, "volume": 60}) in body["state"]["history"][-1]["content"]
        return httpx.Response(200, json={"answers": {"route": {"type": "choice", "choice": "tool_volume_adjust", "confidence": 0.9}}, "usage": {"input_tokens": 12, "output_tokens": 2}})

    async def run():
        messages = parse_messages([*_tool_turn("tool_volume_adjust", "声音大点", {"action": "raise"}, {"ok": True, "volume": 60}, 1), {"role": "user", "content": "再大点"}])
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await classify(messages, Provider("https://example.test/v1", "test", "jev", 30000), client, "trace")

    route, confidence, timing = asyncio.run(run())
    assert route == "tool_volume_adjust" and confidence == 0.9
    assert timing["first_token_ms"] is None and timing["first_byte_ms"] is not None
    assert timing["usage"]["total_tokens"] == 14
    assert logged == ["request", "response"]


def test_jev_rejects_confidence_outside_unit_interval():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"answers": {"route": {"type": "choice", "choice": "agent_chat", "confidence": 1.2}}})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            await classify([{"role": "user", "content": "你好"}], Provider("https://example.test", "test", "jev", 30000), client, "trace")

    with pytest.raises(ValueError, match="0 到 1"):
        asyncio.run(run())


def test_deepseek_required_then_none(monkeypatch):
    choices = []
    exchanges = []
    monkeypatch.setattr("intent_router.providers.log_exchange", lambda **record: exchanges.append(record))

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        choices.append(body["tool_choice"])
        assert body["stream"] is True and body["stream_options"]["include_usage"] is True
        if body["tool_choice"] == "required":
            assert [tool["function"]["name"] for tool in body["tools"]] == ["tool_weather"]
            events = [{"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "c1", "function": {"name": "tool_weather", "arguments": '{"location":"北京"}'}}]}}]}, {"choices": [], "usage": {"prompt_tokens": 10, "completion_tokens": 4}}]
        else:
            assert any(m["role"] == "tool" for m in body["messages"])
            events = [{"choices": [{"delta": {"content": "样本天气 27 度"}}]}, {"choices": [], "usage": {"prompt_tokens": 14, "completion_tokens": 8}}]
        return httpx.Response(200, text="".join(f"data: {json.dumps(event)}\n\n" for event in events) + "data: [DONE]\n\n")

    async def run():
        provider = Provider("https://example.test", "test", "ds", 30000)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            parsed = await completion("deepseek", provider, [{"role": "user", "content": "北京天气"}], "parse", client, "trace", tool=HANDLERS["tool_weather"].tool_spec(), tool_choice="required")
            assert parsed.tool_calls[0]["function"]["arguments"] == '{"location":"北京"}'
            call = {"role": "assistant", "content": None, "tool_calls": parsed.tool_calls}
            result = {"role": "tool", "tool_call_id": "c1", "content": '{"temperature_2m":27}', "name": "tool_weather"}
            answer = await completion("deepseek", provider, [call, result], "answer", client, "trace", tool=HANDLERS["tool_weather"].tool_spec(), tool_choice="none")
            return answer

    answer = asyncio.run(run())
    assert choices == ["required", "none"]
    assert answer.content == "样本天气 27 度"
    assert answer.timing["usage"]["total_tokens"] == 22
    assert exchanges[0]["response_body"].startswith("data:")
    assert exchanges[0]["response_assembled"]["tool_calls"][0]["function"]["name"] == "tool_weather"
    assert exchanges[1]["response_assembled"]["content"] == "样本天气 27 度"


def test_single_port_page_and_validation():
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
            page = await client.get("/route")
            assert page.status_code == 200 and '/static/app.js' in page.text
            assert (await client.get("/static/app.js")).status_code == 200
            routes = (await client.get("/api/status")).json()["routes"]
            assert {"tool_volume_set", "tool_volume_adjust", "tool_song_control", "tool_goodbye"} <= set(routes)
            assert routes["tool_goodbye"]["agent"]["ends_session"] is True
            response = await client.post("/api/turn", json={"messages": [{"role": "user", "content": ""}]})
            assert response.status_code == 400

    asyncio.run(run())


def test_route_threshold_api_updates_local_config(monkeypatch, tmp_path: Path):
    (tmp_path / "config.example.yaml").write_text((ROOT / "config.example.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setattr("intent_router.main.load_config", lambda: load_config(tmp_path))
    monkeypatch.setattr("intent_router.main.save_route_threshold", lambda route, value: save_route_threshold(route, value, tmp_path))

    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
            valid = await client.patch("/api/routes/tool_song_control/threshold", json={"threshold": 0.8})
            assert valid.status_code == 200 and valid.json()["threshold"] == 0.8
            status = (await client.get("/api/status")).json()
            assert status["routes"]["tool_song_control"]["threshold"] == 0.8
            invalid = await client.patch("/api/routes/tool_song_control/threshold", json={"threshold": 1.1})
            assert invalid.status_code == 400
            rejected = await client.patch("/api/routes/tool_song_control/threshold", json={"threshold": 0.4}, headers={"Origin": "http://other.test"})
            assert rejected.status_code == 403
            assert load_config(tmp_path).route_thresholds["tool_song_control"] == 0.8

    asyncio.run(run())


def test_console_logs_full_bodies_and_agent_context():
    printed = []
    sink = logger.add(lambda message: printed.append(message.record["message"]), filter=lambda record: "exchange" not in record["extra"])
    try:
        log_trace("trace-test", "音量上下文", {"selected_messages": [{"role": "user", "content": "再大点"}]})
        log_request("trace-test", "jev", "Jev 路由", "https://example.test/systemone", {"state": {"latest_message": "再大点"}})
        log_exchange(trace_id="trace-test", provider="jev", stage="Jev 路由", url="https://example.test/systemone", request_body={"state": {"latest_message": "再大点"}}, response_status=200, response_body={"answers": {"route": {"choice": "tool_volume_adjust"}}}, elapsed_ms=12)
        log_request("trace-test", "deepseek", "参数解析", "https://example.test/chat/completions", {"tool_choice": "required"})
        log_exchange(trace_id="trace-test", provider="deepseek", stage="参数解析", url="https://example.test/chat/completions", request_body={"tool_choice": "required"}, response_status=200, response_body='data: {"choices":[{"delta":{"content":"好"}}]}\n\ndata: [DONE]\n', response_assembled={"content": "好", "tool_calls": [], "usage": {"input_tokens": 1, "output_tokens": 1}, "finish_reason": "stop"}, elapsed_ms=20)
    finally:
        logger.remove(sink)
    output = "\n".join(printed)
    assert "selected_messages" in output and "再大点" in output
    assert "request body:" in output and "response body:" in output
    assert "JEV | Jev 路由 | REQUEST" in output and "JEV | Jev 路由 | RESPONSE" in output
    assert "tool_volume_adjust" in output and "trace-test" in output
    assert "response body (stream assembled):" in output and '"content":"好"' in output
    assert 'data: {"choices"' not in output and '"tool_choice":"required"' in output
    assert all("\n" not in line for line in printed)

import asyncio
import json

import httpx
from loguru import logger

from intent_router.agents import AGENTS
from intent_router.config import Provider
from intent_router.conversation import last_tool_result, routing_history, tool_history
from intent_router.exchange_log import log_exchange, log_request, log_trace
from intent_router.main import app
from intent_router.messages import parse_messages
from intent_router.providers import classify, completion


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
        *_tool_turn("set_volume", "音量设为 35", {"value": 35}, {"ok": True, "volume": 35, "muted": False, "dispatch": "set_volume"}, 1),
        *_tool_turn("get_weather", "北京天气", {"location": "北京"}, {"ok": True, "location": "北京", "current": {"temperature_2m": 27}}, 2),
        *_tool_turn("adjust_volume", "大点", {"action": "raise"}, {"ok": True, "volume": 45, "muted": False, "action": "raise", "dispatch": "adjust_volume"}, 3),
        {"role": "user", "content": "再大点"},
    ])
    context = AGENTS["adjust_volume"].context(messages)
    assert [m["role"] for m in context] == ["user", "assistant", "tool", "assistant", "user", "assistant", "tool", "assistant", "user"]
    assert [m["content"] for m in context if m["role"] == "user"] == ["音量设为 35", "大点", "再大点"]
    assert "北京" not in json.dumps(context, ensure_ascii=False)
    assert last_tool_result(messages, "adjust_volume")["volume"] == 45
    assert "45" in AGENTS["adjust_volume"].parameter_instructions(messages)
    assert AGENTS["adjust_volume"].execute('{"action":"raise"}', messages)["volume"] == 55
    route_context = routing_history(messages)
    assert "adjust_volume" in route_context[-1]["content"] and "45" in route_context[-1]["content"]
    assert [m["role"] for m in AGENTS["chat"].context(messages)].count("tool") == 0


def test_agent_context_limits_are_local():
    messages = parse_messages([
        *_tool_turn("get_weather", "北京天气", {"location": "北京"}, {"ok": True, "location": "北京"}, 1),
        *_tool_turn("play_song", "播放晴天", {"title": "晴天", "artist": ""}, {"ok": True, "title": "晴天"}, 2),
        {"role": "user", "content": "上海呢"},
    ])
    assert [m["role"] for m in tool_history(messages, "get_weather", 2)] == ["user", "assistant", "tool", "assistant", "user"]
    assert "播放晴天" not in json.dumps(AGENTS["get_weather"].context(messages), ensure_ascii=False)
    assert "北京天气" in json.dumps(AGENTS["get_weather"].context(messages), ensure_ascii=False)


def test_new_agent_boundaries_and_virtual_dispatch():
    assert AGENTS["set_volume"].execute('{"value":160}', [{"role": "user", "content": "调到160"}])["volume"] == 100
    assert AGENTS["play_song"].tool_spec()["function"]["parameters"]["required"] == []
    selection = AGENTS["play_song"].execute('{"emotion":"calm"}', [{"role": "user", "content": "播放点舒缓的歌"}])
    assert selection["selection"] == {"emotion": "calm"}
    messages = parse_messages([*_tool_turn("play_song", "播放点舒缓的歌", {"emotion": "calm"}, selection, 1), {"role": "user", "content": "下一首"}])
    assert AGENTS["song_control"].execute('{"action":"next"}', messages)["ok"] is True
    assert AGENTS["song_control"].execute('{"action":"next"}', [{"role": "user", "content": "下一首"}])["ok"] is False
    assert AGENTS["handle_user_goodbye"].context([{"role": "user", "content": "再见"}]) == [{"role": "user", "content": "再见"}]
    assert AGENTS["handle_user_goodbye"].execute('{"farewell_reply":"下次见！"}', [{"role": "user", "content": "再见"}])["ends_session"] is True


def test_jev_choice_request_and_metrics(monkeypatch):
    logged = []
    monkeypatch.setattr("intent_router.providers.log_request", lambda *args: logged.append("request"))
    monkeypatch.setattr("intent_router.providers.log_exchange", lambda **record: logged.append("response"))

    def handler(request: httpx.Request) -> httpx.Response:
        assert logged == ["request"]
        body = json.loads(request.content)
        assert request.url.path.endswith("/systemone")
        assert body["questions"]["route"]["type"] == "choice"
        assert body["state"]["latest_message"]["content"] == "再大点"
        assert "adjust_volume" in body["state"]["history"][-1]["content"]
        assert '"volume":60' in body["state"]["history"][-1]["content"]
        return httpx.Response(200, json={"answers": {"route": {"type": "choice", "choice": "adjust_volume", "confidence": 0.9}}, "usage": {"input_tokens": 12, "output_tokens": 2}})

    async def run():
        messages = parse_messages([*_tool_turn("adjust_volume", "声音大点", {"action": "raise"}, {"ok": True, "volume": 60}, 1), {"role": "user", "content": "再大点"}])
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await classify(messages, Provider("https://example.test/v1", "test", "jev", 30000), client, "trace")

    route, confidence, timing = asyncio.run(run())
    assert route == "adjust_volume" and confidence == 0.9
    assert timing["first_token_ms"] is None and timing["first_byte_ms"] is not None
    assert timing["usage"]["total_tokens"] == 14
    assert logged == ["request", "response"]


def test_deepseek_required_then_none(monkeypatch):
    choices = []
    exchanges = []
    monkeypatch.setattr("intent_router.providers.log_exchange", lambda **record: exchanges.append(record))

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        choices.append(body["tool_choice"])
        assert body["stream"] is True and body["stream_options"]["include_usage"] is True
        if body["tool_choice"] == "required":
            assert [tool["function"]["name"] for tool in body["tools"]] == ["get_weather"]
            events = [{"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "c1", "function": {"name": "get_weather", "arguments": '{"location":"北京"}'}}]}}]}, {"choices": [], "usage": {"prompt_tokens": 10, "completion_tokens": 4}}]
        else:
            assert any(m["role"] == "tool" for m in body["messages"])
            events = [{"choices": [{"delta": {"content": "样本天气 27 度"}}]}, {"choices": [], "usage": {"prompt_tokens": 14, "completion_tokens": 8}}]
        return httpx.Response(200, text="".join(f"data: {json.dumps(event)}\n\n" for event in events) + "data: [DONE]\n\n")

    async def run():
        provider = Provider("https://example.test", "test", "ds", 30000)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            parsed = await completion("deepseek", provider, [{"role": "user", "content": "北京天气"}], "parse", client, "trace", tool=AGENTS["get_weather"].tool_spec(), tool_choice="required")
            assert parsed.tool_calls[0]["function"]["arguments"] == '{"location":"北京"}'
            call = {"role": "assistant", "content": None, "tool_calls": parsed.tool_calls}
            result = {"role": "tool", "tool_call_id": "c1", "content": '{"temperature_2m":27}', "name": "get_weather"}
            answer = await completion("deepseek", provider, [call, result], "answer", client, "trace", tool=AGENTS["get_weather"].tool_spec(), tool_choice="none")
            return answer

    answer = asyncio.run(run())
    assert choices == ["required", "none"]
    assert answer.content == "样本天气 27 度"
    assert answer.timing["usage"]["total_tokens"] == 22
    assert exchanges[0]["response_body"].startswith("data:")
    assert exchanges[0]["response_assembled"]["tool_calls"][0]["function"]["name"] == "get_weather"
    assert exchanges[1]["response_assembled"]["content"] == "样本天气 27 度"


def test_single_port_page_and_validation():
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
            page = await client.get("/route")
            assert page.status_code == 200 and '/static/app.js' in page.text
            assert (await client.get("/static/app.js")).status_code == 200
            routes = (await client.get("/api/status")).json()["routes"]
            assert {"set_volume", "adjust_volume", "song_control", "handle_user_goodbye"} <= set(routes)
            assert routes["handle_user_goodbye"]["agent"]["ends_session"] is True
            response = await client.post("/api/turn", json={"messages": [{"role": "user", "content": ""}]})
            assert response.status_code == 400

    asyncio.run(run())


def test_console_logs_full_bodies_and_agent_context():
    printed = []
    sink = logger.add(lambda message: printed.append(message.record["message"]), filter=lambda record: "exchange" not in record["extra"])
    try:
        log_trace("trace-test", "音量上下文", {"selected_messages": [{"role": "user", "content": "再大点"}]})
        log_request("trace-test", "jev", "Jev 路由", "https://example.test/systemone", {"state": {"latest_message": "再大点"}})
        log_exchange(trace_id="trace-test", provider="jev", stage="Jev 路由", url="https://example.test/systemone", request_body={"state": {"latest_message": "再大点"}}, response_status=200, response_body={"answers": {"route": {"choice": "adjust_volume"}}}, elapsed_ms=12)
        log_request("trace-test", "deepseek", "参数解析", "https://example.test/chat/completions", {"tool_choice": "required"})
        log_exchange(trace_id="trace-test", provider="deepseek", stage="参数解析", url="https://example.test/chat/completions", request_body={"tool_choice": "required"}, response_status=200, response_body='data: {"choices":[{"delta":{"content":"好"}}]}\n\ndata: [DONE]\n', response_assembled={"content": "好", "tool_calls": [], "usage": {"input_tokens": 1, "output_tokens": 1}, "finish_reason": "stop"}, elapsed_ms=20)
    finally:
        logger.remove(sink)
    output = "\n".join(printed)
    assert "selected_messages" in output and "再大点" in output
    assert "request body:" in output and "response body:" in output
    assert "JEV | Jev 路由 | REQUEST" in output and "JEV | Jev 路由 | RESPONSE" in output
    assert "adjust_volume" in output and "trace-test" in output
    assert "response body (stream assembled):" in output and '"content": "好"' in output
    assert 'data: {"choices"' not in output and '"tool_choice": "required"' in output

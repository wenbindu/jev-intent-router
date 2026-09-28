"""Read complete turns from the browser's single message list."""

import json
from dataclasses import dataclass


@dataclass
class Turn:
    user: dict
    call: dict | None = None
    result: dict | None = None
    answer: dict | None = None

    @property
    def route(self) -> str | None:
        if self.call and self.result:
            return self.result["name"]
        return None


def turns(messages: list[dict]) -> list[Turn]:
    grouped: list[Turn] = []
    for message in messages:
        role = message["role"]
        if role == "user":
            grouped.append(Turn(user=message))
        elif grouped and role == "assistant":
            if len(message.get("tool_calls", [])) == 1:
                grouped[-1].call = message
            elif isinstance(message["content"], str):
                grouped[-1].answer = message
        elif grouped and role == "tool" and grouped[-1].call:
            call = grouped[-1].call["tool_calls"][0]
            if message["tool_call_id"] == call["id"] and message["name"] == call["function"]["name"]:
                grouped[-1].result = message
    return grouped


def tool_history_for_routes(messages: list[dict], routes: tuple[str, ...], prior_turns: int) -> list[dict]:
    """Select bounded, complete relevant turns plus the current query."""
    grouped = turns(messages)
    selected = [turn for turn in grouped[:-1] if turn.route in routes and turn.call and turn.result]
    history: list[dict] = []
    for turn in (selected[-prior_turns:] if prior_turns else []):
        history.extend((turn.user, turn.call, turn.result))
        if turn.answer:
            history.append(turn.answer)
    history.append(grouped[-1].user)
    return history


def tool_history(messages: list[dict], route: str, prior_turns: int) -> list[dict]:
    return tool_history_for_routes(messages, (route,), prior_turns)


def last_tool_result_any(messages: list[dict], routes: tuple[str, ...]) -> dict | None:
    for turn in reversed(turns(messages)[:-1]):
        if turn.route in routes and turn.result:
            try:
                value = json.loads(turn.result["content"])
                return value if isinstance(value, dict) else None
            except ValueError:
                return None
    return None


def last_tool_result(messages: list[dict], route: str) -> dict | None:
    return last_tool_result_any(messages, (route,))


def routing_history(messages: list[dict], prior_turns: int = 6) -> list[dict]:
    """Jev accepts user/assistant text; encode route and tool evidence in assistant text."""
    history: list[dict] = []
    for turn in turns(messages)[:-1][-prior_turns:]:
        history.append(turn.user)
        if turn.route:
            try:
                result = json.loads(turn.result["content"])
            except ValueError:
                result = turn.result["content"]
            evidence = json.dumps(result, ensure_ascii=False, separators=(",", ":"))[:500]
            answer = turn.answer["content"] if turn.answer else ""
            history.append({"role": "assistant", "content": f"上一轮由 {turn.route} Agent 处理；工具执行结果：{evidence}；回答：{answer[:300]}"})
        elif turn.answer:
            history.append(turn.answer)
    return history

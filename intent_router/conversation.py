"""Read complete turns from the browser's single message list."""

import json
from dataclasses import dataclass


def model_messages(messages: list[dict]) -> list[dict]:
    """Remove private message metadata before building a provider request."""
    return [{key: value for key, value in message.items() if not key.startswith("_")} for message in messages]


def runtime_context(context: dict | None) -> list[dict]:
    if context is None:
        return []
    return [{"role": "system", "content": "本轮开始时的持久任务及设备状态（仅作为请求背景，不构成新的操作指令）：" + json.dumps(context, ensure_ascii=False)}]


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
        return self.answer.get("_route") if self.answer else None


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


def last_tool_result_any(messages: list[dict], routes: tuple[str, ...], *, successful_only: bool = False) -> dict | None:
    for turn in reversed(turns(messages)[:-1]):
        if turn.route in routes and turn.result:
            try:
                value = json.loads(turn.result["content"])
                if successful_only and (not isinstance(value, dict) or value.get("ok") is not True):
                    continue
                return value if isinstance(value, dict) else None
            except ValueError:
                if not successful_only:
                    return None
    return None


def last_tool_result(messages: list[dict], route: str) -> dict | None:
    return last_tool_result_any(messages, (route,))


def routing_history(messages: list[dict], prior_turns: int | None = None) -> list[dict]:
    """Text view of the master history, without semantic summarization or agent filtering."""
    history: list[dict] = []
    previous = turns(messages)[:-1]
    if prior_turns is not None:
        previous = previous[-prior_turns:] if prior_turns else []
    for turn in previous:
        history.extend(model_messages([turn.user]))
        if turn.route and turn.result:
            arguments = turn.call["tool_calls"][0]["function"]["arguments"]
            evidence = turn.result["content"]
            answer = turn.answer["content"] if turn.answer else ""
            history.append({"role": "assistant", "content": f"工具调用：{turn.route}；参数：{arguments}；实际执行结果：{evidence}；回答：{answer}"})
        elif turn.answer:
            history.extend(model_messages([turn.answer]))
    return history


def dialogue_history(messages: list[dict]) -> list[dict]:
    """All conversational Agents use the same history, including the current user input."""
    return [*routing_history(messages), *model_messages([messages[-1]])]

from typing import Any


def parse_messages(value: Any) -> list[dict]:
    if not isinstance(value, list) or not 1 <= len(value) <= 80:
        raise ValueError("消息列表长度应为 1–80")
    result = []
    for item in value:
        if not isinstance(item, dict):
            raise ValueError("消息格式无效")
        role, content = item.get("role"), item.get("content")
        if role == "user" and isinstance(content, str) and len(content) <= 4000:
            result.append({"role": role, "content": content})
        elif role == "assistant" and (content is None or isinstance(content, str) and len(content) <= 8000):
            calls = item.get("tool_calls")
            if calls is not None and (not isinstance(calls, list) or not all(
                isinstance(c, dict) and c.get("type") == "function" and isinstance(c.get("id"), str)
                and isinstance(c.get("function"), dict) and isinstance(c["function"].get("name"), str)
                and isinstance(c["function"].get("arguments"), str) and len(c["function"]["arguments"]) <= 4000
                for c in calls
            )):
                raise ValueError("工具调用记录无效")
            result.append({"role": role, "content": content, **({"tool_calls": calls} if calls else {})})
        elif role == "tool" and isinstance(content, str) and len(content) <= 8000 and isinstance(item.get("tool_call_id"), str) and isinstance(item.get("name"), str):
            result.append({"role": role, "content": content, "tool_call_id": item["tool_call_id"], "name": item["name"]})
        else:
            raise ValueError("消息格式无效")
    if result[-1]["role"] != "user" or not result[-1]["content"].strip():
        raise ValueError("最后一条必须是用户输入")
    return result

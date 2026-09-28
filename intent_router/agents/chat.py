import httpx

from ..config import Config
from ..exchange_log import log_trace
from ..providers import completion
from .base import AgentInfo, Send


class ChatAgent(AgentInfo):
    def context(self, messages: list[dict]) -> list[dict]:
        natural = [m for m in messages if m["role"] == "user" or m["role"] == "assistant" and isinstance(m["content"], str) and not m.get("tool_calls")]
        return natural[-16:]

    async def run(self, messages: list[dict], config: Config, client: httpx.AsyncClient, trace_id: str, send: Send) -> str:
        send(type="status", text=f"{self.name} 正在回答")
        system = "你是自然、简洁的中文聊天助手Mimi。根据对话上下文回答，不要声称执行了设备命令或查询了实时天气。"
        history = self.context(messages)
        log_trace(trace_id, f"{self.name} 上下文", {"route": self.route, "policy": "最近 16 条自然语言 user/assistant 消息", "source_message_count": len(messages), "selected_messages": history})
        answer = await completion(self.provider_name, self.provider(config), [{"role": "system", "content": system}, *history], "Qwen 聊天", client, trace_id, lambda text: send(type="delta", text=text))
        send(type="timing", timing=answer.timing)
        if not answer.content.strip():
            raise ValueError("聊天 Agent 未返回回答")
        return answer.content

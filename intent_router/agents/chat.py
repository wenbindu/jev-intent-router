import httpx

from ..config import Config
from ..conversation import dialogue_history, runtime_context
from ..exchange_log import log_trace
from ..providers import completion
from .base import HandlerInfo, Send
from .prompts import AGENT_PROMPTS


class ChatAgent(HandlerInfo):
    context_policy = "会话主列表中的全部对话及实际工具记录；过滤私有字段，不按 Agent 拆分历史，不做语义摘要"
    max_tokens = 4096

    @property
    def system_prompt(self) -> str:
        return AGENT_PROMPTS[self.route]

    @property
    def stage(self) -> str:
        return f"Qwen · {self.name}"

    def context(self, messages: list[dict]) -> list[dict]:
        return dialogue_history(messages)

    async def run(self, messages: list[dict], config: Config, client: httpx.AsyncClient, trace_id: str, send: Send, context: dict | None = None) -> str:
        send(type="status", text=f"{self.name} 正在回答")
        history = self.context(messages)
        log_trace(trace_id, f"{self.name} 上下文", {"route": self.route, "policy": self.context_policy, "source_message_count": len(messages), "selected_messages": history})
        answer = await completion(self.provider_name, self.provider(config), [{"role": "system", "content": self.system_prompt}, *runtime_context(context), *history], self.stage, client, trace_id, lambda text: send(type="delta", text=text), max_tokens=self.max_tokens)
        send(type="timing", timing=answer.timing)
        if not answer.content.strip() or answer.tool_calls:
            raise ValueError(f"{self.name} 未返回自然语言回答")
        return answer.content

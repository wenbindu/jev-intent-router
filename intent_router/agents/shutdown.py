from .tool import ToolHandler, parse_args, text_arg, tool_schema


class ShutdownTool(ToolHandler):
    prior_turns = 1

    def tool_spec(self) -> dict:
        return {"type": "function", "function": {"name": self.route, "description": "模拟关闭虚拟设备，不关闭当前电脑", "parameters": tool_schema({"reason": {"type": "string", "description": "用户要求关机的简短原因；不明确时为空字符串"}})}}

    def parameter_instructions(self, messages: list[dict]) -> str:
        return super().parameter_instructions(messages) + " 只根据当前用户明确的关机请求生成本轮调用；历史关机记录不构成新的关机授权。"

    def execute(self, raw_args: str, messages: list[dict]) -> dict:
        return {"ok": True, "device": "virtual", "dispatch": self.route, "status": "accepted", "simulated": True, "reason": text_arg(parse_args(raw_args).get("reason"), "reason"), "message": "已下发到虚拟设备；宿主机没有执行关机。"}

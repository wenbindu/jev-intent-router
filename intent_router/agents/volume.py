"""Two intent routes sharing one virtual device volume state."""

from ..conversation import last_tool_result_any, tool_history_for_routes
from .tool import ToolAgent, parse_args, tool_schema

VOLUME_ROUTES = ("set_volume", "adjust_volume", "volume_control")


class VolumeAgent(ToolAgent):
    prior_turns = 3

    def context(self, messages: list[dict]) -> list[dict]:
        return tool_history_for_routes(messages, VOLUME_ROUTES, self.prior_turns)

    def context_policy(self) -> str:
        return "最近 3 个设置或调节音量的完整工具轮次 + 当前用户输入；状态取最近一次音量工具结果"

    def state(self, messages: list[dict]) -> tuple[int | float, bool]:
        previous = last_tool_result_any(messages, VOLUME_ROUTES) or {}
        volume = previous.get("volume", 50)
        muted = previous.get("muted", False)
        if isinstance(volume, bool) or not isinstance(volume, (int, float)) or not 0 <= volume <= 100:
            volume = 50
        return volume, muted if isinstance(muted, bool) else False

    def parameter_instructions(self, messages: list[dict]) -> str:
        volume, muted = self.state(messages)
        return super().parameter_instructions(messages) + f" 当前虚拟设备音量为 {volume}，静音状态为 {muted}。先前设置和调节工具的结果都是历史状态，不是本轮要重复下发的命令。"


class SetVolumeAgent(VolumeAgent):
    def tool_spec(self) -> dict:
        return {"type": "function", "function": {"name": self.route, "description": "当用户明确指定目标音量值时设置虚拟设备音量；超出 0–100 时压缩到区间内", "parameters": tool_schema({"value": {"type": "integer", "description": "用户指定的目标音量值；执行时压缩到 0–100"}})}}

    def parameter_instructions(self, messages: list[dict]) -> str:
        return super().parameter_instructions(messages) + " 只提取当前用户明确指定的目标数值；相对的‘大点/小点’不是设置音量。对于‘调到160’，value 填 160，由执行器压缩到 100。"

    def execute(self, raw_args: str, messages: list[dict]) -> dict:
        value = parse_args(raw_args).get("value")
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("value 必须是整数")
        volume = max(0, min(100, value))
        return {"ok": True, "device": "virtual", "dispatch": self.route, "status": "accepted", "requested_value": value, "volume": volume, "muted": False}


class AdjustVolumeAgent(VolumeAgent):
    def tool_spec(self) -> dict:
        return {"type": "function", "function": {"name": self.route, "description": "在当前虚拟音量基础上调大、调小、静音或取消静音；指定具体数值时应使用 set_volume", "parameters": tool_schema({"action": {"type": "string", "enum": ["raise", "lower", "mute", "unmute"], "description": "raise=调大，lower=调小，mute=静音，unmute=取消静音"}})}}

    def parameter_instructions(self, messages: list[dict]) -> str:
        return super().parameter_instructions(messages) + " ‘再大点/再小点’表示本轮 raise/lower，执行器在当前值上增减 10；不要重新设置为上一轮的目标音量。"

    def execute(self, raw_args: str, messages: list[dict]) -> dict:
        action = parse_args(raw_args).get("action")
        if action not in ("raise", "lower", "mute", "unmute"):
            raise ValueError("action 参数无效")
        prior_volume, prior_muted = self.state(messages)
        volume = min(100, prior_volume + 10) if action == "raise" else max(0, prior_volume - 10) if action == "lower" else prior_volume
        muted = True if action == "mute" else False if action in ("raise", "lower", "unmute") else prior_muted
        return {"ok": True, "device": "virtual", "dispatch": self.route, "status": "accepted", "action": action, "volume": volume, "muted": muted}

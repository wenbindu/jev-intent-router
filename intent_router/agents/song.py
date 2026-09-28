from ..conversation import last_tool_result_any, tool_history_for_routes
from .tool import ToolAgent, parse_args, text_arg, tool_schema

SONG_ROUTES = ("play_song", "song_control")


class SongAgent(ToolAgent):
    prior_turns = 2

    def tool_spec(self) -> dict:
        return {"type": "function", "function": {"name": self.route, "description": "用户明确要求播放歌曲或唱歌时，在虚拟播放器中按给定条件选歌；各条件仅在用户明确指定时填写", "parameters": tool_schema({
            "song_name": {"type": "string", "description": "明确指定的歌曲名"},
            "artist": {"type": "string", "description": "明确指定的歌手"},
            "emotion": {"type": "string", "enum": ["happy", "sad", "calm", "warm", "excited"]},
            "language": {"type": "string", "enum": ["en", "zh_cn"]},
            "character": {"type": "string", "enum": ["mimi", "bo", "raingo"]},
        }, required=[])}}

    def parameter_instructions(self, messages: list[dict]) -> str:
        return super().parameter_instructions(messages) + " 歌名、歌手、情绪、语言、角色都是可选的；只填写当前用户明确指定的条件，未知时省略键。当前用户若明确要求再播放一次，才复用上一轮歌曲；否则不要重复上一轮播放命令。"

    def execute(self, raw_args: str, messages: list[dict]) -> dict:
        args = parse_args(raw_args)
        allowed = {"song_name", "artist", "emotion", "language", "character"}
        if set(args) - allowed:
            raise ValueError("歌曲参数含未知字段")
        selection = {}
        for field in ("song_name", "artist"):
            if field in args:
                selection[field] = text_arg(args[field], field)
        for field, options in (("emotion", {"happy", "sad", "calm", "warm", "excited"}), ("language", {"en", "zh_cn"}), ("character", {"mimi", "bo", "raingo"})):
            if field in args:
                if args[field] not in options:
                    raise ValueError(f"{field} 参数无效")
                selection[field] = args[field]
        return {"ok": True, "player": "virtual", "dispatch": self.route, "status": "accepted", "selection": selection, "simulated": True}


class SongControlAgent(ToolAgent):
    prior_turns = 2

    def context(self, messages: list[dict]) -> list[dict]:
        return tool_history_for_routes(messages, SONG_ROUTES, self.prior_turns)

    def context_policy(self) -> str:
        return "最近 2 个播放或歌曲控制的完整工具轮次 + 当前用户输入"

    def tool_spec(self) -> dict:
        return {"type": "function", "function": {"name": self.route, "description": "控制虚拟播放器当前歌曲；明确要求下一首、重播、停止或退出歌曲模式时调用", "parameters": tool_schema({"action": {"type": "string", "enum": ["next", "replay", "stop", "exit"]}})}}

    def execute(self, raw_args: str, messages: list[dict]) -> dict:
        action = parse_args(raw_args).get("action")
        if action not in ("next", "replay", "stop", "exit"):
            raise ValueError("action 参数无效")
        previous = last_tool_result_any(messages, SONG_ROUTES) or {}
        playing = previous.get("ok") is True and (previous.get("dispatch") == "play_song" or previous.get("dispatch") == "song_control" and previous.get("action") in ("next", "replay"))
        if not playing and action != "exit":
            return {"ok": False, "error": "当前没有正在播放的虚拟歌曲。", "action": action}
        return {"ok": True, "player": "virtual", "dispatch": self.route, "status": "accepted", "action": action, "simulated": True}

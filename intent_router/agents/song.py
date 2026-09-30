from ..conversation import last_tool_result_any, model_messages, tool_history_for_routes
from .tool import ToolHandler, parse_args, text_arg, tool_schema

SONG_ROUTES = ("tool_song_play", "tool_song_control")


class SongTool(ToolHandler):
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
        return {"ok": True, "player": "virtual", "dispatch": self.route, "status": "accepted", "selection": selection, "playback_state": "playing", "simulated": True}


class SongControlTool(ToolHandler):
    prior_turns = 2

    def context(self, messages: list[dict]) -> list[dict]:
        return model_messages(tool_history_for_routes(messages, SONG_ROUTES, self.prior_turns))

    def context_policy(self) -> str:
        return "最近 2 个播放或歌曲控制的完整工具轮次 + 当前用户输入"

    def parameter_instructions(self, messages: list[dict]) -> str:
        return super().parameter_instructions(messages) + " pause=暂停，resume=从暂停处继续，stop=停止；next/previous/replay 在暂停时也会开始播放。停止后需要重新点歌。"

    def tool_spec(self) -> dict:
        return {"type": "function", "function": {"name": self.route, "description": "控制虚拟播放器：上一首、下一首、重播、暂停、继续或停止", "parameters": tool_schema({"action": {"type": "string", "enum": ["previous", "next", "replay", "pause", "resume", "stop"], "description": "previous=上一首，next=下一首，replay=重播，pause=暂停，resume=继续，stop=停止"}})}}

    def execute(self, raw_args: str, messages: list[dict]) -> dict:
        action = parse_args(raw_args).get("action")
        if action not in ("previous", "next", "replay", "pause", "resume", "stop"):
            raise ValueError("action 参数无效")
        previous = last_tool_result_any(messages, SONG_ROUTES, successful_only=True) or {}
        state = previous.get("playback_state")
        if state not in ("idle", "playing", "paused", "stopped"):
            if previous.get("ok") is True and previous.get("dispatch") == "tool_song_play":
                state = "playing"
            elif previous.get("ok") is True and previous.get("dispatch") == "tool_song_control":
                state = {"pause": "paused", "stop": "stopped", "previous": "playing", "next": "playing", "replay": "playing", "resume": "playing"}.get(previous.get("action"), "idle")
            else:
                state = "idle"
        result = {"player": "virtual", "dispatch": self.route, "action": action, "playback_state": state, "simulated": True}
        if state in ("idle", "stopped"):
            return {"ok": False, **result, "error": "当前没有可控制的虚拟歌曲，请先播放一首歌。"}
        if action == "pause" and state == "paused":
            return {"ok": False, **result, "error": "虚拟歌曲已经暂停。"}
        if action == "resume" and state == "playing":
            return {"ok": False, **result, "error": "虚拟歌曲正在播放。"}
        next_state = "paused" if action == "pause" else "stopped" if action == "stop" else "playing"
        return {"ok": True, **result, "status": "accepted", "playback_state": next_state, **({"ends_task": "tool_song_play"} if action == "stop" else {})}

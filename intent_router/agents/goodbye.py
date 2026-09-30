from .tool import ToolHandler, parse_args, text_arg, tool_schema


class GoodbyeTool(ToolHandler):
    prior_turns = 0
    ends_session = True

    def tool_spec(self) -> dict:
        return {"type": "function", "function": {"name": self.route, "description": "用户单独或主要表达结束对话时生成简短告别语；询问、翻译、引用或同轮继续提问时不调用", "parameters": tool_schema({"farewell_reply": {"type": "string", "description": "简短角色回应"}})}}

    def answer_instructions(self) -> str:
        return "你是简洁的中文助手。直接使用本轮工具结果中的 farewell_reply 与用户告别，不要引入新的问题。"

    def execute(self, raw_args: str, messages: list[dict]) -> dict:
        reply = text_arg(parse_args(raw_args).get("farewell_reply"), "farewell_reply")
        if not reply:
            raise ValueError("farewell_reply 不能为空")
        return {"ok": True, "dispatch": self.route, "ends_session": True, "farewell_reply": reply}

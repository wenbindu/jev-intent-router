from .tool import ToolAgent, parse_args, text_arg, tool_schema


class WeatherAgent(ToolAgent):
    prior_turns = 2

    def tool_spec(self) -> dict:
        return {"type": "function", "function": {"name": self.route, "description": "查询指定城市的当前天气", "parameters": tool_schema({"location": {"type": "string", "description": "城市名；仅用户明确给出或可由当前天气上下文确定时填写"}, "lang": {"type": "string", "description": "语言代码，默认 zh_CN"}}, required=[])}}

    def parameter_instructions(self, messages: list[dict]) -> str:
        return super().parameter_instructions(messages) + " 当前用户若说‘那上海呢’之类，只提取本轮的新地点；不要把上一轮地点当作本轮地点。"

    def execute(self, raw_args: str, messages: list[dict]) -> dict:
        args = parse_args(raw_args)
        location = text_arg(args["location"], "location") if "location" in args else ""
        if not location:
            return {"ok": False, "error": "缺少城市，请向用户询问地点。"}
        lang = text_arg(args["lang"], "lang") if "lang" in args else "zh_CN"
        return {"ok": True, "source": "mock", "sample": True, "location": location, "lang": lang, "current": {"temperature_2m": 27, "relative_humidity_2m": 50, "apparent_temperature": 28, "wind_speed_10m": 8, "weather_code": 1}, "units": {"temperature_2m": "°C", "relative_humidity_2m": "%", "apparent_temperature": "°C", "wind_speed_10m": "km/h"}}

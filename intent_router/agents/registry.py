from ..routes import ROUTES
from .chat import ChatAgent
from .goodbye import GoodbyeTool
from .shutdown import ShutdownTool
from .song import SongTool, SongControlTool
from .volume import AdjustVolumeTool, SetVolumeTool
from .weather import WeatherTool


HANDLERS = {
    "tool_volume_set": SetVolumeTool("tool_volume_set", "音量设置工具", "deepseek"),
    "tool_volume_adjust": AdjustVolumeTool("tool_volume_adjust", "音量调节工具", "deepseek"),
    "tool_shutdown": ShutdownTool("tool_shutdown", "关机工具", "deepseek"),
    "tool_weather": WeatherTool("tool_weather", "天气查询工具", "deepseek"),
    "tool_song_play": SongTool("tool_song_play", "歌曲播放工具", "deepseek"),
    "tool_song_control": SongControlTool("tool_song_control", "歌曲控制工具", "deepseek"),
    "tool_goodbye": GoodbyeTool("tool_goodbye", "告别工具", "deepseek"),
    "agent_roleplay": ChatAgent("agent_roleplay", "扮演游戏 Agent", "qwen"),
    "agent_english": ChatAgent("agent_english", "英语教师 Agent", "qwen"),
    "agent_fitness": ChatAgent("agent_fitness", "健身教练 Agent", "qwen"),
    "agent_nutrition": ChatAgent("agent_nutrition", "营养师 Agent", "qwen"),
    "agent_story": ChatAgent("agent_story", "讲故事 Agent", "qwen"),
    "agent_chat": ChatAgent("agent_chat", "闲聊 Agent", "qwen"),
}

if tuple(HANDLERS) != ROUTES:
    raise ValueError("执行器注册表与 Jev 路由不一致")

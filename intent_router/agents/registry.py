from ..catalog import CATALOG, ROUTES
from .chat import ChatAgent
from .goodbye import GoodbyeAgent
from .shutdown import ShutdownAgent
from .song import SongAgent, SongControlAgent
from .volume import AdjustVolumeAgent, SetVolumeAgent
from .weather import WeatherAgent


AGENTS = {
    "set_volume": SetVolumeAgent("set_volume", "音量设置 Agent", "deepseek"),
    "adjust_volume": AdjustVolumeAgent("adjust_volume", "音量调节 Agent", "deepseek"),
    "shutdown": ShutdownAgent("shutdown", "关机 Agent", "deepseek"),
    "get_weather": WeatherAgent("get_weather", "天气查询 Agent", "deepseek"),
    "play_song": SongAgent("play_song", "歌曲播放 Agent", "deepseek"),
    "song_control": SongControlAgent("song_control", "歌曲控制 Agent", "deepseek"),
    "handle_user_goodbye": GoodbyeAgent("handle_user_goodbye", "告别 Agent", "deepseek"),
    "chat": ChatAgent("chat", "聊天 Agent", "qwen"),
}

if tuple(AGENTS) != ROUTES or set(AGENTS) != set(CATALOG):
    raise ValueError("Agent 注册表与 Jev 路由不一致")

from .config import ROOT, _yaml

ROUTES = ("set_volume", "adjust_volume", "shutdown", "get_weather", "play_song", "song_control", "handle_user_goodbye", "chat")
TOOL_ROUTES = ROUTES[:-1]
CATALOG = _yaml(ROOT / "tools.yaml")
if set(CATALOG) != set(ROUTES):
    raise ValueError("tools.yaml 路由与程序路由不一致")

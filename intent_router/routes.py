"""Public route IDs and migration of existing local threshold settings."""

AGENT_ROUTES = ("agent_roleplay", "agent_english", "agent_fitness", "agent_nutrition", "agent_story", "agent_chat")
TOOL_ROUTES = ("tool_volume_set", "tool_volume_adjust", "tool_shutdown", "tool_weather", "tool_song_play", "tool_song_control", "tool_goodbye")
ROUTES = (*TOOL_ROUTES, *AGENT_ROUTES)

LEGACY_ROUTE_NAMES = {
    "chat": "agent_chat",
    "story": "agent_story",
    "set_volume": "tool_volume_set",
    "adjust_volume": "tool_volume_adjust",
    "shutdown": "tool_shutdown",
    "get_weather": "tool_weather",
    "play_song": "tool_song_play",
    "song_control": "tool_song_control",
    "handle_user_goodbye": "tool_goodbye",
}

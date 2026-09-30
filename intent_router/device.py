"""Device properties are independent of the task currently occupying the device."""

import json


def apply_device_result(state: dict, result: dict) -> dict:
    patch = result.get("device_state")
    if result.get("ok") is not True or not isinstance(patch, dict):
        return state
    return {**state, **patch}


def device_state(messages: list[dict]) -> dict:
    state = {"volume": 50, "muted": False}
    for message in messages:
        if message["role"] != "tool":
            continue
        try:
            result = json.loads(message["content"])
        except ValueError:
            continue
        if isinstance(result, dict):
            # Older volume receipts predate device_state; normalize them once here.
            if "device_state" not in result and message.get("name") in ("tool_volume_set", "tool_volume_adjust", "volume_control"):
                result = {**result, "device_state": {key: result[key] for key in ("volume", "muted") if key in result}}
            state = apply_device_result(state, result)
    return state

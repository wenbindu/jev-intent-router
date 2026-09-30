from dataclasses import dataclass
from typing import Callable, Protocol

import httpx

from ..config import Config, Provider
from ..catalog import CATALOG


Send = Callable[..., None]


class Handler(Protocol):
    route: str
    name: str
    provider_name: str

    def provider(self, config: Config) -> Provider: ...
    def public(self, config: Config) -> dict: ...
    async def run(self, messages: list[dict], config: Config, client: httpx.AsyncClient, trace_id: str, send: Send, context: dict | None = None) -> str: ...


@dataclass(frozen=True)
class HandlerInfo:
    route: str
    name: str
    provider_name: str

    def provider(self, config: Config) -> Provider:
        return getattr(config, self.provider_name)

    def public(self, config: Config) -> dict:
        return {"name": self.name, "kind": "agent" if self.route.startswith("agent_") else "tool", "persistent_task": CATALOG[self.route]["persistent_task"], "model": self.provider(config).model, "ends_session": bool(getattr(self, "ends_session", False))}

from dataclasses import dataclass
from typing import Callable, Protocol

import httpx

from ..config import Config, Provider


Send = Callable[..., None]


class Agent(Protocol):
    route: str
    name: str
    provider_name: str

    def provider(self, config: Config) -> Provider: ...
    def public(self, config: Config) -> dict: ...
    async def run(self, messages: list[dict], config: Config, client: httpx.AsyncClient, trace_id: str, send: Send) -> str: ...


@dataclass(frozen=True)
class AgentInfo:
    route: str
    name: str
    provider_name: str

    def provider(self, config: Config) -> Provider:
        return getattr(config, self.provider_name)

    def public(self, config: Config) -> dict:
        return {"name": self.name, "model": self.provider(config).model, "ends_session": bool(getattr(self, "ends_session", False))}

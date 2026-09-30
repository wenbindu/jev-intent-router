"""A session has one persistent task; transient handlers leave it unchanged."""

from dataclasses import asdict, dataclass

from .catalog import CATALOG
from .routes import AGENT_ROUTES


@dataclass(frozen=True)
class TaskState:
    current_task: str | None = "agent_chat"

    @classmethod
    def parse(cls, value: object) -> "TaskState":
        if value is None:
            return cls()
        if not isinstance(value, dict) or set(value) != {"current_task"}:
            raise ValueError("task_state 必须只包含 current_task")
        current = value["current_task"]
        if current is not None and (not isinstance(current, str) or current not in CATALOG or not CATALOG[current]["persistent_task"]):
            raise ValueError("current_task 必须是持久任务或 null")
        return cls(current)

    @property
    def fallback_route(self) -> str:
        # A fallback must never repeat an operation just because it owns the device.
        return self.current_task if self.current_task in AGENT_ROUTES else "agent_chat"

    def transition(self, route: str) -> "TaskState":
        if route not in CATALOG:
            raise ValueError("未知路由")
        return TaskState(route) if CATALOG[route]["persistent_task"] else self

    def after_tool(self, route: str, result: dict) -> "TaskState":
        if result.get("ok") is not True:
            return self
        if result.get("ends_session") is True or (self.current_task is not None and result.get("ends_task") == self.current_task):
            return TaskState(None)
        return self.transition(route)

    def public(self) -> dict:
        return asdict(self)

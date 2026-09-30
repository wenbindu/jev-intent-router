from .config import ROOT, _yaml
from .routes import ROUTES

CATALOG = _yaml(ROOT / "tools.yaml")
if set(CATALOG) != set(ROUTES):
    raise ValueError("tools.yaml 路由与程序路由不一致")
if any(type(value.get("persistent_task")) is not bool for value in CATALOG.values()):
    raise ValueError("每条路由必须配置布尔字段 persistent_task")
if set(_yaml(ROOT / "config.example.yaml").get("route_thresholds", {})) != set(ROUTES):
    raise ValueError("config.example.yaml 路由阈值与程序路由不一致")

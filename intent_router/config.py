from dataclasses import dataclass
from math import isfinite
import os
from pathlib import Path
from tempfile import mkstemp
from threading import Lock
from urllib.parse import urlsplit

import yaml

from .routes import LEGACY_ROUTE_NAMES

ROOT = Path(__file__).resolve().parent.parent
_config_lock = Lock()


@dataclass(frozen=True)
class Provider:
    base_url: str
    api_key: str
    model: str
    timeout_ms: int


@dataclass(frozen=True)
class Config:
    hostname: str
    port: int
    jev: Provider
    qwen: Provider
    deepseek: Provider
    route_thresholds: dict[str, float]


def _yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    value = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} 必须是 YAML 对象")
    return value


def _provider(name: str, value: dict) -> Provider:
    try:
        result = Provider(**value)
        url = urlsplit(result.base_url)
        if url.scheme not in ("http", "https") or not url.netloc or url.username or url.password or url.query or url.fragment:
            raise ValueError("base_url 无效")
        if not isinstance(result.api_key, str) or not isinstance(result.model, str) or not result.model.strip():
            raise ValueError("api_key 或 model 无效")
        if not isinstance(result.timeout_ms, int) or not 1000 <= result.timeout_ms <= 120000:
            raise ValueError("timeout_ms 无效")
        return result
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} 配置无效: {exc}") from exc


def validate_threshold(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value) or not 0 <= value <= 1:
        raise ValueError("路由置信度阈值必须是 0 到 1 之间的数字")
    return float(value)


def _threshold_names(values: dict) -> dict:
    renamed = {LEGACY_ROUTE_NAMES.get(key, key): value for key, value in values.items()}
    # If a local file contains both names, the explicit new name wins.
    renamed.update({key: value for key, value in values.items() if key not in LEGACY_ROUTE_NAMES})
    return renamed


def load_config(root: Path = ROOT) -> Config:
    defaults = _yaml(root / "config.example.yaml")
    local = _yaml(root / "config.local.yaml")
    merged = {name: {**defaults.get(name, {}), **local.get(name, {})} for name in ("server", "jev", "qwen", "deepseek")}
    server = merged["server"]
    hostname = server.get("hostname")
    port = int(os.environ.get("PORT", server.get("port", 3000)))
    if not isinstance(hostname, str) or not hostname or not 1 <= port <= 65535:
        raise ValueError("server 配置无效")
    threshold_defaults = defaults.get("route_thresholds")
    threshold_overrides = local.get("route_thresholds", {})
    if not isinstance(threshold_defaults, dict) or not threshold_defaults or not isinstance(threshold_overrides, dict):
        raise ValueError("route_thresholds 配置必须是路由到阈值的映射")
    threshold_overrides = _threshold_names(threshold_overrides)
    if unknown := set(threshold_overrides) - set(threshold_defaults):
        raise ValueError(f"未知路由阈值：{', '.join(sorted(unknown))}")
    thresholds = {route: validate_threshold(threshold_overrides.get(route, value)) for route, value in threshold_defaults.items()}
    return Config(hostname, port, *(_provider(name, merged[name]) for name in ("jev", "qwen", "deepseek")), thresholds)


def save_route_threshold(route: str, value: object, root: Path = ROOT) -> float:
    threshold = validate_threshold(value)
    with _config_lock:
        config = load_config(root)
        if route not in config.route_thresholds:
            raise ValueError("未知路由")
        path = root / "config.local.yaml"
        local = _yaml(path)
        overrides = local.setdefault("route_thresholds", {})
        if not isinstance(overrides, dict):
            raise ValueError("route_thresholds 配置必须是映射")
        overrides = _threshold_names(overrides)
        local["route_thresholds"] = overrides
        overrides[route] = threshold
        fd, temporary = mkstemp(prefix=".config.local.", suffix=".tmp", dir=root)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                yaml.safe_dump(local, stream, allow_unicode=True, sort_keys=False)
            os.replace(temporary, path)
        except BaseException:
            os.unlink(temporary)
            raise
    return threshold

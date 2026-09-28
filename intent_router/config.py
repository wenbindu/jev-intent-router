from dataclasses import dataclass
import os
from pathlib import Path
from urllib.parse import urlsplit

import yaml

ROOT = Path(__file__).resolve().parent.parent


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


def load_config(root: Path = ROOT) -> Config:
    defaults = _yaml(root / "config.example.yaml")
    local = _yaml(root / "config.local.yaml")
    merged = {name: {**defaults.get(name, {}), **local.get(name, {})} for name in ("server", "jev", "qwen", "deepseek")}
    server = merged["server"]
    hostname = server.get("hostname")
    port = int(os.environ.get("PORT", server.get("port", 3000)))
    if not isinstance(hostname, str) or not hostname or not 1 <= port <= 65535:
        raise ValueError("server 配置无效")
    return Config(hostname, port, *(_provider(name, merged[name]) for name in ("jev", "qwen", "deepseek")))

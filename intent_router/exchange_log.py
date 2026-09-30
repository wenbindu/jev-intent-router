import json
import os
import sys
from pathlib import Path

from loguru import logger

from .config import ROOT

_configured = False


def _compact(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _single_line(value: object) -> str:
    return str(value).replace("\r", "\\r").replace("\n", "\\n")


def configure_logging(root: Path = ROOT) -> None:
    global _configured
    if _configured:
        return
    logger.remove()
    logger.add(sys.stdout, format="<green>{time:HH:mm:ss.SSS}</green> | <level>{level: <7}</level> | {message}", level="INFO")
    folder = root / ".logs"
    folder.mkdir(mode=0o700, exist_ok=True)
    logger.add(str(folder / "exchanges-{time:YYYY-MM-DD}.log"), format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <7} | {message}", rotation="00:00", retention="14 days", enqueue=True, opener=lambda path, flags: os.open(path, flags, 0o600))
    _configured = True


def log_request(trace_id: str, provider: str, stage: str, url: str, request_body: object) -> None:
    """Show the outgoing request before the network call begins."""
    configure_logging()
    logger.info("[{}] {} | {} | REQUEST {} | request body: {}", trace_id, provider.upper(), stage, url, _compact(request_body))


def log_exchange(**exchange: object) -> None:
    configure_logging()
    status = exchange.get("response_status")
    assembled = exchange.get("response_assembled")
    response = assembled if assembled is not None else exchange.get("response_body")
    response_label = "response body (stream assembled)" if assembled is not None else "response body"
    logger.info(
        "[{}] {} | {} | RESPONSE HTTP {} | {} ms{} | {}: {}",
        exchange.get("trace_id"), str(exchange.get("provider")).upper(), exchange.get("stage"),
        status if status is not None else "—", exchange.get("elapsed_ms"),
        f" | {_single_line(exchange['error'])}" if exchange.get("error") else "",
        response_label, _compact(response),
    )


def log_trace(trace_id: str, stage: str, payload: dict) -> None:
    """Record the exact context or tool data selected inside one routed turn."""
    configure_logging()
    logger.info("[{}] {} | {}", trace_id, stage, _compact(payload))

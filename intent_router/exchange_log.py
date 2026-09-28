import json
import os
import sys
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from loguru import logger

from .config import ROOT

_configured = False


def configure_logging(root: Path = ROOT) -> None:
    global _configured
    if _configured:
        return
    logger.remove()
    logger.add(sys.stdout, format="<green>{time:HH:mm:ss.SSS}</green> | <level>{level: <7}</level> | {message}", level="INFO", filter=lambda record: "exchange" not in record["extra"])
    folder = root / ".logs"
    folder.mkdir(mode=0o700, exist_ok=True)
    logger.add(str(folder / "exchanges-{time:YYYY-MM-DD}.jsonl"), format="{extra[exchange]}", filter=lambda record: "exchange" in record["extra"], rotation="00:00", retention="14 days", enqueue=True, opener=lambda path, flags: os.open(path, flags, 0o600))
    _configured = True


def log_request(trace_id: str, provider: str, stage: str, url: str, request_body: object) -> None:
    """Show the outgoing request before the network call begins."""
    configure_logging()
    logger.info("[{}] {} | {} | REQUEST {}\nrequest body:\n{}", trace_id, provider.upper(), stage, url, json.dumps(request_body, ensure_ascii=False, indent=2))


def log_exchange(**exchange: object) -> None:
    configure_logging()
    record = {"kind": "provider_exchange", "at": datetime.now().astimezone().isoformat(), **exchange}
    logger.bind(exchange=json.dumps(record, ensure_ascii=False, separators=(",", ":"))).info("exchange")
    status = record.get("response_status")
    assembled = record.get("response_assembled")
    response = assembled if assembled is not None else record.get("response_body")
    rendered_response = response if isinstance(response, str) else json.dumps(response, ensure_ascii=False, indent=2)
    response_label = "response body (stream assembled)" if assembled is not None else "response body"
    logger.info(
        "[{}] {} | {} | RESPONSE HTTP {} | {} ms{}\n{}:\n{}",
        record.get("trace_id"), str(record.get("provider")).upper(), record.get("stage"),
        status if status is not None else "—", record.get("elapsed_ms"),
        f" | {record['error']}" if record.get("error") else "",
        response_label, rendered_response,
    )


def log_trace(trace_id: str, stage: str, payload: dict) -> None:
    """Record the exact context or tool data selected inside one routed turn."""
    configure_logging()
    record = {"kind": "agent_trace", "id": str(uuid4()), "at": datetime.now().astimezone().isoformat(), "trace_id": trace_id, "stage": stage, "payload": payload}
    logger.bind(exchange=json.dumps(record, ensure_ascii=False, separators=(",", ":"))).info("exchange")
    logger.info("[{}] {}\n{}", trace_id, stage, json.dumps(payload, ensure_ascii=False, indent=2))

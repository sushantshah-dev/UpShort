from __future__ import annotations

import json
import logging
import os
import socket
from collections import deque
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from flask import has_request_context, request


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "hostname": socket.gethostname(),
            "message": record.getMessage(),
        }

        if has_request_context():
            payload["method"] = request.method
            payload["path"] = request.path
            payload["remote_addr"] = request.headers.get(
                "X-Forwarded-For", request.remote_addr
            )

        if hasattr(record, "status_code"):
            payload["status_code"] = record.status_code
        if hasattr(record, "duration_ms"):
            payload["duration_ms"] = round(record.duration_ms, 2)
        if hasattr(record, "location"):
            payload["location"] = record.location

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        elif record.exc_text:
            payload["exception"] = record.exc_text

        return json.dumps(payload, ensure_ascii=True)


def _resolve_log_file_path() -> Path:
    configured_path = os.environ.get("LOG_FILE_PATH", "logs/app.log")
    return Path(configured_path)


def configure_logging(app) -> Path:
    if app.extensions.get("upshort_logging_configured"):
        return Path(app.config["LOG_FILE_PATH"])

    log_level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, log_level_name, logging.INFO)
    log_file_path = _resolve_log_file_path()
    log_file_path.parent.mkdir(parents=True, exist_ok=True)

    formatter = JsonFormatter()
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    if not any(
        getattr(handler, "_upshort_handler", False) for handler in root_logger.handlers
    ):
        stream_handler = logging.StreamHandler()
        stream_handler.setLevel(log_level)
        stream_handler.setFormatter(formatter)
        stream_handler._upshort_handler = True
        root_logger.addHandler(stream_handler)

        file_handler = RotatingFileHandler(
            log_file_path,
            maxBytes=int(os.environ.get("LOG_FILE_MAX_BYTES", 1_048_576)),
            backupCount=int(os.environ.get("LOG_FILE_BACKUP_COUNT", 5)),
        )
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter)
        file_handler._upshort_handler = True
        root_logger.addHandler(file_handler)

    app.logger.handlers.clear()
    app.logger.propagate = True
    logging.getLogger("werkzeug").handlers.clear()
    logging.getLogger("werkzeug").propagate = True
    logging.captureWarnings(True)

    app.config["LOG_FILE_PATH"] = str(log_file_path)
    app.config["LOG_VIEWER_TAIL_LINES"] = int(
        os.environ.get("LOG_VIEWER_TAIL_LINES", 200)
    )
    app.extensions["upshort_logging_configured"] = True
    return log_file_path


def log_exception(logger: logging.Logger, exc: BaseException, *, message: str) -> None:
    logger.error(
        message,
        exc_info=(type(exc), exc, exc.__traceback__),
    )


def read_recent_logs(
    log_file_path: str | os.PathLike[str], limit: int
) -> list[dict[str, Any]]:
    path = Path(log_file_path)
    if not path.exists():
        return []

    entries: deque[dict[str, Any]] = deque(maxlen=max(limit, 1))
    with path.open("r", encoding="utf-8") as log_file:
        for line in log_file:
            line = line.strip()
            if not line:
                continue
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                parsed = {
                    "timestamp": None,
                    "level": "INFO",
                    "logger": "raw",
                    "message": line,
                }
            entries.append(parsed)

    return list(reversed(entries))

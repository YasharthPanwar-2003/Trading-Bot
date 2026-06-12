"""Logging setup for console output and JSON log files."""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Optional

EXTRA_FIELDS = (
    "symbol",
    "side",
    "order_type",
    "order_id",
    "error_code",
    "data",
    "attempt",
    "max_retries",
    "quantity",
    "price",
    "status",
)

CONSOLE_FIELDS = ("symbol", "side", "order_type", "order_id", "error_code")


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        payload.update(
            {
                field: getattr(record, field)
                for field in EXTRA_FIELDS
                if hasattr(record, field)
            }
        )

        if record.exc_info and record.exc_info[0]:
            payload["exception"] = self.formatException(record.exc_info)
            payload["exception_type"] = record.exc_info[0].__name__

        return json.dumps(payload, default=str)


class ConsoleFormatter(logging.Formatter):
    COLORS = {
        "DEBUG": "\033[36m",
        "INFO": "\033[32m",
        "WARNING": "\033[33m",
        "ERROR": "\033[31m",
        "CRITICAL": "\033[1;31m",
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        context = self._context(record)
        color = self.COLORS.get(record.levelname, "")
        line = f"{color}{timestamp} [{record.levelname}]{context} {record.getMessage()}{self.RESET}"

        if record.exc_info and record.exc_info[0]:
            line += "\n" + self.formatException(record.exc_info)

        return line

    def _context(self, record: logging.LogRecord) -> str:
        parts = [
            f"{field}={getattr(record, field)}"
            for field in CONSOLE_FIELDS
            if hasattr(record, field) and getattr(record, field) is not None
        ]
        return f" [{', '.join(parts)}]" if parts else ""


def setup_logger(
    name: str = "trading_bot",
    log_file: Optional[str] = None,
    log_level: str = "INFO",
    console_output: bool = True,
    force: bool = False,
) -> logging.Logger:
    logger = logging.getLogger(name)
    level = getattr(logging, log_level.upper(), logging.INFO)
    logger.setLevel(level)

    if force:
        for handler in list(logger.handlers):
            logger.removeHandler(handler)
            handler.close()

    if logger.handlers:
        return logger

    if console_output:
        logger.addHandler(_handler(logging.StreamHandler(sys.stdout), ConsoleFormatter(), level))

    logger.addHandler(
        _handler(
            logging.FileHandler(_log_file_path(log_file), encoding="utf-8"),
            JSONFormatter(),
            logging.DEBUG,
        )
    )
    return logger


def get_logger(name: str = "trading_bot") -> logging.Logger:
    return logging.getLogger(name)


def _handler(
    handler: logging.Handler,
    formatter: logging.Formatter,
    level: int,
) -> logging.Handler:
    handler.setFormatter(formatter)
    handler.setLevel(level)
    return handler


def _log_file_path(log_file: Optional[str]) -> str:
    path = log_file or os.path.join(_project_root(), "logs", "trading_bot.log")
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    return path


def _project_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

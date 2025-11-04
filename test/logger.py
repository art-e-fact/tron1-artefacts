import copy
import json
import logging.config
import os
from datetime import datetime
from typing import Optional

import colorama
from colorama import Fore, Style, init


class JsonLineFormatter(logging.Formatter):
    """Outputs log records as JSON lines."""

    def format(self, record: logging.LogRecord):
        log_record = {
            "time": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "funcName": record.funcName,
            "line": record.lineno,
        }
        data = getattr(record, "data", None)
        if data is not None:
            log_record["data"] = data
        if record.exc_info:
            log_record["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(log_record)


class CsvXYFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord):
        x = getattr(record, "x", None)
        y = getattr(record, "y", None)
        if x is None or y is None:
            return ""
        return f"{float(x):.6f},{float(y):.6f}"


class CsvXYFileHandler(logging.FileHandler):
    def __init__(self, filename, mode="w", encoding="utf-8", delay=False):
        super().__init__(filename, mode=mode, encoding=encoding, delay=delay)
        if not delay:
            self.stream.write("x,y\n")
            self.stream.flush()
        self.setFormatter(CsvXYFormatter())


LEVEL_COLORS = {
    "DEBUG": Fore.BLUE,
    "INFO": Fore.CYAN,
    "WARNING": Fore.YELLOW,
    "ERROR": Fore.RED,
    "CRITICAL": Fore.BLACK + Style.BRIGHT + colorama.Back.RED,
}


class OnlyLevelFilter(logging.Filter):
    """Only allow a single level through this handler."""

    def __init__(self, level):
        self.level = level

    def filter(self, record):
        return record.levelno == self.level


class ColoredFormatter(logging.Formatter):
    """Adds colors to levelname in logs."""

    def format(self, record: logging.LogRecord):
        record = copy.deepcopy(record)
        levelname = record.levelname
        if levelname in LEVEL_COLORS:
            record.levelname = (
                f"{LEVEL_COLORS[levelname]}{record.levelname[0]}{Style.RESET_ALL}"
            )
            record.msg = f"{LEVEL_COLORS[levelname]}{record.msg}{Style.RESET_ALL}"
        return super().format(record)


def setup_logger(debug_path: Optional[str] = None):
    handlers = ["stdout", "stderr"]
    if debug_path:
        handlers.append("json")
        handlers.append("userlog")

    cfg = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "user": {
                "()": ColoredFormatter,
                "format": "%(levelname)s| %(message)s",
                "datefmt": "%Y-%m-%dT%H:%M:%S",
            },
            "json": {
                "()": JsonLineFormatter,
            },
            "csv_xy": {
                "()": CsvXYFormatter,
            },
        },
        "filters": {"only_info": {"()": OnlyLevelFilter, "level": logging.INFO}},
        "handlers": {
            "stdout": {
                "class": "logging.StreamHandler",
                "level": "INFO",
                "formatter": "user",
                "filters": ["only_info"],
                "stream": "ext://sys.stdout",
            },
            "stderr": {
                "class": "logging.StreamHandler",
                "level": "WARNING",
                "formatter": "user",
                "stream": "ext://sys.stderr",
            },
            "json": {
                "class": "logging.FileHandler",
                "level": "DEBUG",
                "formatter": "json",
                "filename": (
                    os.path.expanduser(debug_path) + "/debug.log.jsonl"
                    if debug_path is not None
                    else "log.jsonl"
                ),
                "mode": "w",
            },
            "userlog": {
                "class": "logging.FileHandler",
                "level": "DEBUG",
                "formatter": "user",
                "filename": (
                    os.path.expanduser(debug_path) + "/debug.log.txt"
                    if debug_path is not None
                    else "log"
                ),
                "mode": "w",
            },
        },
        "loggers": {
            "artefacts": {"level": "DEBUG", "handlers": handlers, "propagate": False},
            "asyncio_for_robotics": {
                "level": "DEBUG",
                "handlers": handlers,
                "propagate": False,
            },
            "data": {"level": "INFO", "handlers": [], "propagate": False},
            "graph": {"level": "INFO", "handlers": [], "propagate": False},
        },
    }
    logging.config.dictConfig(cfg)

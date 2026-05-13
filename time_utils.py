"""
Time helpers shared by UI and logging.
"""

from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo


APP_TIMEZONE_NAME = "Asia/Shanghai"
APP_TIMEZONE = ZoneInfo(APP_TIMEZONE_NAME)


def now_local() -> datetime:
    return datetime.now(APP_TIMEZONE)


def now_local_str(fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    return now_local().strftime(fmt)


def configure_logging_timezone() -> None:
    """Force logging %(asctime)s to use the app timezone."""

    def converter(timestamp: float):
        return datetime.fromtimestamp(timestamp, APP_TIMEZONE).timetuple()

    logging.Formatter.converter = staticmethod(converter)

    loggers = [logging.getLogger()]
    loggers.extend(
        logger
        for logger in logging.root.manager.loggerDict.values()
        if isinstance(logger, logging.Logger)
    )
    for logger in loggers:
        for handler in logger.handlers:
            if handler.formatter is not None:
                handler.formatter.converter = converter

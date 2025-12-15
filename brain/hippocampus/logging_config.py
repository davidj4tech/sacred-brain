"""Simple logging helpers."""
from __future__ import annotations

import logging
from logging.config import dictConfig
from .config import HippocampusSettings


def configure_logging(settings: HippocampusSettings) -> None:
    level = getattr(logging, settings.app.log_level.upper(), logging.INFO)
    dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {
                    "format": "%(asctime)s [%(levelname)s] %(name)s :: %(message)s",
                }
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "default",
                    "level": level,
                }
            },
            "root": {"handlers": ["console"], "level": level},
        }
    )


__all__ = ["configure_logging"]

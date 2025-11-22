"""Configuration loading utilities for the hippocampus service."""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
import os
import tomllib
from typing import List


@dataclass
class AppSettings:
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "INFO"
    allow_origins: List[str] = field(default_factory=lambda: ["*"])


@dataclass
class Mem0Settings:
    enabled: bool = True
    api_key: str | None = None
    backend: str = "memory"
    backend_url: str = "http://localhost:7700"
    summary_max_length: int = 480
    query_limit: int = 5
    persistence_path: str | None = None


@dataclass
class HippocampusSettings:
    app: AppSettings = field(default_factory=AppSettings)
    mem0: Mem0Settings = field(default_factory=Mem0Settings)


def load_settings(config_path: str | Path | None = None) -> HippocampusSettings:
    """Load settings from TOML + environment overrides."""
    config_file = _resolve_config_path(config_path)
    file_data: dict[str, object] = {}
    if config_file and config_file.exists():
        with config_file.open("rb") as fh:
            file_data = tomllib.load(fh)

    app_data = file_data.get("app", {}) if isinstance(file_data, dict) else {}
    mem0_data = file_data.get("mem0", {}) if isinstance(file_data, dict) else {}

    settings = HippocampusSettings(
        app=_load_app_settings(app_data),
        mem0=_load_mem0_settings(mem0_data),
    )
    return _apply_env_overrides(settings)


def _resolve_config_path(config_path: str | Path | None) -> Path | None:
    if config_path:
        return Path(config_path).expanduser().resolve()
    env_config = os.getenv("HIPPOCAMPUS_CONFIG")
    if env_config:
        return Path(env_config).expanduser().resolve()
    default = Path(__file__).resolve().parents[2] / "config" / "hippocampus.toml"
    return default if default.exists() else None


def _load_app_settings(raw: object) -> AppSettings:
    if not isinstance(raw, dict):
        return AppSettings()
    allow_origins = raw.get("allow_origins", ["*"])
    if isinstance(allow_origins, str):
        allow_origins = [origin.strip() for origin in allow_origins.split(",") if origin.strip()]
    return AppSettings(
        host=str(raw.get("host", "0.0.0.0")),
        port=int(raw.get("port", 8000)),
        log_level=str(raw.get("log_level", "INFO")),
        allow_origins=list(allow_origins),
    )


def _load_mem0_settings(raw: object) -> Mem0Settings:
    if not isinstance(raw, dict):
        return Mem0Settings()
    api_key = raw.get("api_key")
    if isinstance(api_key, str) and not api_key.strip():
        api_key = None
    return Mem0Settings(
        enabled=bool(raw.get("enabled", True)),
        api_key=api_key,
        backend=str(raw.get("backend", "memory")),
        backend_url=str(raw.get("backend_url", "http://localhost:7700")),
        summary_max_length=int(raw.get("summary_max_length", 480)),
        query_limit=int(raw.get("query_limit", 5)),
        persistence_path=str(raw.get("persistence_path")) if raw.get("persistence_path") else None,
    )


def _apply_env_overrides(settings: HippocampusSettings) -> HippocampusSettings:
    env_map: dict[str, tuple[str, callable]] = {
        "app.host": ("HIPPOCAMPUS_APP_HOST", str),
        "app.port": ("HIPPOCAMPUS_APP_PORT", int),
        "app.log_level": ("HIPPOCAMPUS_APP_LOG_LEVEL", str),
        "app.allow_origins": ("HIPPOCAMPUS_APP_ALLOW_ORIGINS", _csv_to_list),
        "mem0.enabled": ("HIPPOCAMPUS_MEM0_ENABLED", _to_bool),
        "mem0.api_key": ("HIPPOCAMPUS_MEM0_API_KEY", _empty_to_none),
        "mem0.backend": ("HIPPOCAMPUS_MEM0_BACKEND", str),
        "mem0.backend_url": ("HIPPOCAMPUS_MEM0_BACKEND_URL", str),
        "mem0.summary_max_length": ("HIPPOCAMPUS_SUMMARY_MAX_LENGTH", int),
        "mem0.query_limit": ("HIPPOCAMPUS_QUERY_LIMIT", int),
        "mem0.persistence_path": ("HIPPOCAMPUS_MEM0_PERSISTENCE_PATH", str),
    }

    updated = settings
    for path, (env_var, caster) in env_map.items():
        raw_value = os.getenv(env_var)
        if raw_value is None:
            continue
        value = caster(raw_value)
        updated = _assign_path(updated, path, value)
    return updated


def _assign_path(settings: HippocampusSettings, path: str, value: object) -> HippocampusSettings:
    top, _, attr = path.partition(".")
    if top == "app":
        return replace(settings, app=replace(settings.app, **{attr: value}))
    if top == "mem0":
        return replace(settings, mem0=replace(settings.mem0, **{attr: value}))
    return settings


def _csv_to_list(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _empty_to_none(value: str) -> str | None:
    value = value.strip()
    return value or None


def _to_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


__all__ = ["AppSettings", "Mem0Settings", "HippocampusSettings", "load_settings"]

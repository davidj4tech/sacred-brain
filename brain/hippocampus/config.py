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
    port: int = 54321
    log_level: str = "INFO"
    allow_origins: List[str] = field(default_factory=lambda: ["*"])


@dataclass
class AuthSettings:
    enabled: bool = False
    header_name: str = "X-API-Key"
    api_keys: List[str] = field(default_factory=list)


@dataclass
class SummarizerSettings:
    enabled: bool = False
    provider: str = "litellm"
    model: str = "ollama:llama3"
    base_url: str | None = None
    api_key: str | None = None
    max_tokens: int = 512


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
class AgnoSettings:
    enabled: bool = False
    model: str = "openai:gpt-4o-mini"
    base_url: str | None = None
    api_key: str | None = None
    system_prompt: str | None = None


@dataclass
class NotesSettings:
    notes_dir: str = "data/memories-denote"
    default_user: str = "default"


@dataclass
class HippocampusSettings:
    app: AppSettings = field(default_factory=AppSettings)
    auth: AuthSettings = field(default_factory=AuthSettings)
    summarizer: SummarizerSettings = field(default_factory=SummarizerSettings)
    mem0: Mem0Settings = field(default_factory=Mem0Settings)
    agno: AgnoSettings = field(default_factory=AgnoSettings)
    notes: NotesSettings = field(default_factory=NotesSettings)


def load_settings(config_path: str | Path | None = None) -> HippocampusSettings:
    """Load settings from TOML + environment overrides."""
    config_file = _resolve_config_path(config_path)
    file_data: dict[str, object] = {}
    if config_file and config_file.exists():
        with config_file.open("rb") as fh:
            file_data = tomllib.load(fh)

    app_data = file_data.get("app", {}) if isinstance(file_data, dict) else {}
    auth_data = file_data.get("auth", {}) if isinstance(file_data, dict) else {}
    summarizer_data = file_data.get("summarizer", {}) if isinstance(file_data, dict) else {}
    mem0_data = file_data.get("mem0", {}) if isinstance(file_data, dict) else {}
    agno_data = file_data.get("agno", {}) if isinstance(file_data, dict) else {}
    notes_data = file_data.get("notes", {}) if isinstance(file_data, dict) else {}

    settings = HippocampusSettings(
        app=_load_app_settings(app_data),
        auth=_load_auth_settings(auth_data),
        summarizer=_load_summarizer_settings(summarizer_data),
        mem0=_load_mem0_settings(mem0_data),
        agno=_load_agno_settings(agno_data),
        notes=_load_notes_settings(notes_data),
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
        port=int(raw.get("port", 54321)),
        log_level=str(raw.get("log_level", "INFO")),
        allow_origins=list(allow_origins),
    )


def _load_auth_settings(raw: object) -> AuthSettings:
    if not isinstance(raw, dict):
        return AuthSettings()
    header_name = str(raw.get("header_name", "X-API-Key")) or "X-API-Key"
    api_keys_raw = raw.get("api_keys", [])
    if isinstance(api_keys_raw, str):
        api_keys = _csv_to_list(api_keys_raw)
    elif isinstance(api_keys_raw, list):
        api_keys = [str(item).strip() for item in api_keys_raw if str(item).strip()]
    else:
        api_keys = []
    return AuthSettings(
        enabled=bool(raw.get("enabled", False)),
        header_name=header_name,
        api_keys=api_keys,
    )


def _load_summarizer_settings(raw: object) -> SummarizerSettings:
    if not isinstance(raw, dict):
        return SummarizerSettings()
    api_key = raw.get("api_key")
    if isinstance(api_key, str) and not api_key.strip():
        api_key = None
    base_url = raw.get("base_url")
    if isinstance(base_url, str) and not base_url.strip():
        base_url = None
    return SummarizerSettings(
        enabled=bool(raw.get("enabled", False)),
        provider=str(raw.get("provider", "litellm")),
        model=str(raw.get("model", "ollama:llama3")),
        base_url=base_url,
        api_key=api_key,
        max_tokens=int(raw.get("max_tokens", 512)),
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


def _load_agno_settings(raw: object) -> AgnoSettings:
    if not isinstance(raw, dict):
        return AgnoSettings()
    api_key = raw.get("api_key")
    if isinstance(api_key, str) and not api_key.strip():
        api_key = None
    base_url = raw.get("base_url")
    if isinstance(base_url, str) and not base_url.strip():
        base_url = None
    prompt = raw.get("system_prompt")
    if isinstance(prompt, str) and not prompt.strip():
        prompt = None
    return AgnoSettings(
        enabled=bool(raw.get("enabled", False)),
        model=str(raw.get("model", "openai:gpt-4o-mini")),
        base_url=base_url,
        api_key=api_key,
        system_prompt=prompt,
    )


def _load_notes_settings(raw: object) -> NotesSettings:
    if not isinstance(raw, dict):
        return NotesSettings()
    notes_dir = raw.get("notes_dir", "data/memories-denote")
    default_user = raw.get("default_user", "default")
    return NotesSettings(
        notes_dir=str(notes_dir),
        default_user=str(default_user),
    )


def _apply_env_overrides(settings: HippocampusSettings) -> HippocampusSettings:
    env_map: dict[str, tuple[str, callable]] = {
        "app.host": ("HIPPOCAMPUS_APP_HOST", str),
        "app.port": ("HIPPOCAMPUS_APP_PORT", int),
        "app.log_level": ("HIPPOCAMPUS_APP_LOG_LEVEL", str),
        "app.allow_origins": ("HIPPOCAMPUS_APP_ALLOW_ORIGINS", _csv_to_list),
        "auth.enabled": ("HIPPOCAMPUS_AUTH_ENABLED", _to_bool),
        "auth.header_name": ("HIPPOCAMPUS_AUTH_HEADER", str),
        "auth.api_keys": ("HIPPOCAMPUS_AUTH_API_KEYS", _csv_to_list),
        "summarizer.enabled": ("HIPPOCAMPUS_SUMMARIZER_ENABLED", _to_bool),
        "summarizer.provider": ("HIPPOCAMPUS_SUMMARIZER_PROVIDER", str),
        "summarizer.model": ("HIPPOCAMPUS_SUMMARIZER_MODEL", str),
        "summarizer.base_url": ("HIPPOCAMPUS_SUMMARIZER_BASE_URL", str),
        "summarizer.api_key": ("HIPPOCAMPUS_SUMMARIZER_API_KEY", _empty_to_none),
        "summarizer.max_tokens": ("HIPPOCAMPUS_SUMMARIZER_MAX_TOKENS", int),
        "mem0.enabled": ("HIPPOCAMPUS_MEM0_ENABLED", _to_bool),
        "mem0.api_key": ("HIPPOCAMPUS_MEM0_API_KEY", _empty_to_none),
        "mem0.backend": ("HIPPOCAMPUS_MEM0_BACKEND", str),
        "mem0.backend_url": ("HIPPOCAMPUS_MEM0_BACKEND_URL", str),
        "mem0.summary_max_length": ("HIPPOCAMPUS_SUMMARY_MAX_LENGTH", int),
        "mem0.query_limit": ("HIPPOCAMPUS_QUERY_LIMIT", int),
        "mem0.persistence_path": ("HIPPOCAMPUS_MEM0_PERSISTENCE_PATH", str),
        "agno.enabled": ("HIPPOCAMPUS_AGNO_ENABLED", _to_bool),
        "agno.model": ("HIPPOCAMPUS_AGNO_MODEL", str),
        "agno.base_url": ("HIPPOCAMPUS_AGNO_BASE_URL", str),
        "agno.api_key": ("HIPPOCAMPUS_AGNO_API_KEY", _empty_to_none),
        "agno.system_prompt": ("HIPPOCAMPUS_AGNO_SYSTEM_PROMPT", str),
        "notes.notes_dir": ("HIPPOCAMPUS_NOTES_DIR", str),
        "notes.default_user": ("HIPPOCAMPUS_NOTES_DEFAULT_USER", str),
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
    if top == "auth":
        if attr == "api_keys" and isinstance(value, list):
            value = [str(item).strip() for item in value if str(item).strip()]
        return replace(settings, auth=replace(settings.auth, **{attr: value}))
    if top == "summarizer":
        return replace(settings, summarizer=replace(settings.summarizer, **{attr: value}))
    if top == "mem0":
        return replace(settings, mem0=replace(settings.mem0, **{attr: value}))
    if top == "agno":
        return replace(settings, agno=replace(settings.agno, **{attr: value}))
    if top == "notes":
        return replace(settings, notes=replace(settings.notes, **{attr: value}))
    return settings


def _csv_to_list(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _empty_to_none(value: str) -> str | None:
    value = value.strip()
    return value or None


def _to_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


__all__ = [
    "AppSettings",
    "AuthSettings",
    "SummarizerSettings",
    "Mem0Settings",
    "HippocampusSettings",
    "load_settings",
]

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


def _as_bool(val: Optional[str], default: bool = False) -> bool:
    if val is None:
        return default
    return val.lower() in {"1", "true", "yes", "on"}


def _split_csv(val: Optional[str]) -> List[str]:
    if not val:
        return []
    return [item.strip() for item in val.split(",") if item.strip()]


@dataclass
class GovernorConfig:
    bind_host: str = "127.0.0.1"
    port: int = 54323
    ingest_url: str = "http://127.0.0.1:54322/ingest"
    hippocampus_url: str = "http://127.0.0.1:54321"
    hippocampus_api_key: Optional[str] = None
    litellm_base_url: str = "http://127.0.0.1:4000"
    litellm_api_key: Optional[str] = None
    stream_enable: bool = False
    stream_ttl_days: int = 14
    working_ttl_hours: int = 24
    rooms_scope: str = "room"
    log_assistant: bool = False
    mem0_env_prefix: str = "MEM0_"
    consolidate_scopes: List[str] = field(default_factory=list)
    state_dir: Path = field(
        default_factory=lambda: Path(
            os.environ.get(
                "MG_STATE_DIR",
                Path(__file__).resolve().parents[1] / "var" / "memory-governor",
            )
        )
    )

    @property
    def db_path(self) -> Path:
        return self.state_dir / "state.db"

    @property
    def stream_log_path(self) -> Path:
        return self.state_dir / "stream.log"

    @property
    def spool_path(self) -> Path:
        return self.state_dir / "durable.spool"


def load_config() -> GovernorConfig:
    cfg = GovernorConfig(
        bind_host=os.environ.get("MG_BIND_HOST", "127.0.0.1"),
        port=int(os.environ.get("MG_PORT", "54323")),
        ingest_url=os.environ.get("INGEST_URL", "http://127.0.0.1:54322/ingest"),
        hippocampus_url=os.environ.get("HIPPOCAMPUS_URL", "http://127.0.0.1:54321"),
        hippocampus_api_key=os.environ.get("HIPPOCAMPUS_API_KEY"),
        litellm_base_url=os.environ.get("LITELLM_BASE_URL", "http://127.0.0.1:4000"),
        litellm_api_key=os.environ.get("LITELLM_API_KEY"),
        stream_enable=_as_bool(os.environ.get("MG_STREAM_ENABLE"), False),
        stream_ttl_days=int(os.environ.get("MG_STREAM_TTL_DAYS", "14")),
        working_ttl_hours=int(os.environ.get("MG_WORKING_TTL_HOURS", "24")),
        rooms_scope=os.environ.get("MG_ROOMS_SCOPE", "room"),
        log_assistant=_as_bool(os.environ.get("MG_LOG_ASSISTANT"), False),
        consolidate_scopes=_split_csv(os.environ.get("MG_CONSOLIDATE_SCOPES")),
    )

    cfg.state_dir.mkdir(parents=True, exist_ok=True)
    return cfg

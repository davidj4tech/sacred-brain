import os
from dataclasses import dataclass, field
from pathlib import Path


def _as_bool(val: str | None, default: bool = False) -> bool:
    if val is None:
        return default
    return val.lower() in {"1", "true", "yes", "on"}


def _split_csv(val: str | None) -> list[str]:
    if not val:
        return []
    return [item.strip() for item in val.split(",") if item.strip()]


def _parse_consolidate_scopes(val: str | None) -> list[str]:
    """Parse MG_CONSOLIDATE_SCOPES into a list of canonical scope path strings.

    Accepts:
      - flat `kind:id`                     → `kind:id`
      - @-chained `kind:id@kind2:id2`      → `kind:id/kind2:id2` (leftmost = most specific)
    Raises ValueError for unknown kinds at startup.
    """
    from memory_governor.scopes import parse_scope_path

    paths: list[str] = []
    for raw in _split_csv(val):
        segments = raw.split("@")
        path = "/".join(seg.strip() for seg in segments if seg.strip())
        parse_scope_path(path)  # validates kinds; raises on unknown
        paths.append(path)
    return paths


@dataclass
class GovernorConfig:
    bind_host: str = "127.0.0.1"
    port: int = 54323
    hippocampus_url: str = "http://127.0.0.1:54321"
    hippocampus_api_key: str | None = None
    litellm_base_url: str = "http://127.0.0.1:4000"
    litellm_api_key: str | None = None
    stream_enable: bool = False
    stream_ttl_days: int = 14
    working_ttl_hours: int = 24
    rooms_scope: str = "room"
    log_assistant: bool = False
    mem0_env_prefix: str = "MEM0_"
    consolidate_scopes: list[str] = field(default_factory=list)
    rerank_enabled: bool = False
    rerank_model: str = "gpt-4o-mini"
    rerank_max: int = 10
    recall_protect_days: int = 30
    outcome_delete_threshold: float = 0.2
    prune_confidence_floor: float = 0.15
    outcome_grace_days: int = 7
    dream_protect_days: int = 14
    dream_boost_weight: float = 0.05
    dream_boost_window_days: int = 7
    oracle_enabled: bool = True
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
        hippocampus_url=os.environ.get("HIPPOCAMPUS_URL", "http://127.0.0.1:54321"),
        hippocampus_api_key=os.environ.get("HIPPOCAMPUS_API_KEY"),
        litellm_base_url=os.environ.get("LITELLM_BASE_URL", "http://127.0.0.1:4000"),
        litellm_api_key=os.environ.get("LITELLM_API_KEY"),
        stream_enable=_as_bool(os.environ.get("MG_STREAM_ENABLE"), False),
        stream_ttl_days=int(os.environ.get("MG_STREAM_TTL_DAYS", "14")),
        working_ttl_hours=int(os.environ.get("MG_WORKING_TTL_HOURS", "24")),
        rooms_scope=os.environ.get("MG_ROOMS_SCOPE", "room"),
        log_assistant=_as_bool(os.environ.get("MG_LOG_ASSISTANT"), False),
        consolidate_scopes=_parse_consolidate_scopes(os.environ.get("MG_CONSOLIDATE_SCOPES")),
        rerank_enabled=_as_bool(os.environ.get("MG_RERANK_ENABLE"), False),
        rerank_model=os.environ.get("MG_RERANK_MODEL", "gpt-4o-mini"),
        rerank_max=int(os.environ.get("MG_RERANK_MAX", "10")),
        recall_protect_days=int(os.environ.get("MG_RECALL_PROTECT_DAYS", "30")),
        outcome_delete_threshold=float(os.environ.get("MG_OUTCOME_DELETE_THRESHOLD", "0.2")),
        prune_confidence_floor=float(os.environ.get("MG_PRUNE_CONFIDENCE_FLOOR", "0.15")),
        outcome_grace_days=int(os.environ.get("MG_OUTCOME_GRACE_DAYS", "7")),
        dream_protect_days=int(os.environ.get("MG_DREAM_PROTECT_DAYS", "14")),
        dream_boost_weight=float(os.environ.get("MG_DREAM_BOOST_WEIGHT", "0.05")),
        dream_boost_window_days=int(os.environ.get("MG_DREAM_BOOST_WINDOW_DAYS", "7")),
        oracle_enabled=_as_bool(os.environ.get("MG_ORACLE_ENABLED"), True),
    )

    cfg.state_dir.mkdir(parents=True, exist_ok=True)
    return cfg

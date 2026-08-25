from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./genomeos.db")
    environment: str = os.getenv("GENOMEOS_ENV", "development")
    region_query_enabled: bool = os.getenv(
        "PANUKB_REGION_QUERY_ENABLED", "false"
    ).lower() in {"1", "true", "yes"}
    region_max_rows: int = int(os.getenv("PANUKB_REGION_MAX_ROWS", "10000"))
    atlas_artifact_root: Path = Path(os.getenv("ATLAS_ARTIFACT_ROOT", "demo/artifacts"))
    log_level: str = os.getenv("LOG_LEVEL", "INFO")


settings = Settings()

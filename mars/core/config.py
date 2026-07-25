"""
Platform configuration.
 
Paths are relative to the repository root by default.
Environment variables may override secrets (MT5 credentials, etc.)
but research paths should remain explicit for reproducibility.
"""
 
from __future__ import annotations
 
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
 
from dotenv import load_dotenv
 
load_dotenv()
 
 
def _repo_root() -> Path:
    """Resolve repository root (parent of the mars package)."""
    return Path(__file__).resolve().parents[2]
 
 
@dataclass(frozen=True)
class PathConfig:
    """Filesystem layout for the research platform."""
 
    root: Path = field(default_factory=_repo_root)
 
    @property
    def data_root(self) -> Path:
        return self.root / "data"
 
    @property
    def raw(self) -> Path:
        return self.data_root / "raw"
 
    @property
    def processed(self) -> Path:
        return self.data_root / "processed"
 
    @property
    def research_data(self) -> Path:
        return self.data_root / "research"
 
    @property
    def feature_store(self) -> Path:
        return self.data_root / "feature_store"
 
    @property
    def research_root(self) -> Path:
        return self.root / "research"
 
    @property
    def hypotheses(self) -> Path:
        return self.research_root / "hypotheses"
 
    @property
    def experiments(self) -> Path:
        return self.research_root / "experiments"
 
    @property
    def experiment_logs(self) -> Path:
        return self.research_root / "experiment_logs"
 
    @property
    def legacy(self) -> Path:
        return self.root / "legacy"
 
    def ensure_layout(self) -> None:
        """Create expected directories if missing."""
        for p in (
            self.raw,
            self.processed,
            self.research_data,
            self.feature_store,
            self.hypotheses,
            self.experiments,
            self.experiment_logs,
            self.research_root / "mathematics",
            self.research_root / "literature",
            self.research_root / "notebooks",
            self.research_root / "datasets",
            self.research_root / "validation",
        ):
            p.mkdir(parents=True, exist_ok=True)
 
 
@dataclass(frozen=True)
class MT5Config:
    """Optional MetaTrader 5 credentials for data ingestion only."""
 
    account_number: Optional[str] = field(
        default_factory=lambda: os.getenv("DEMO_ACCOUNT_NUMBER")
    )
    password: Optional[str] = field(default_factory=lambda: os.getenv("PASSWORD"))
    server: Optional[str] = field(default_factory=lambda: os.getenv("SERVER"))
 
    def is_configured(self) -> bool:
        return bool(self.account_number and self.password and self.server)
 
 
@dataclass(frozen=True)
class PlatformConfig:
    """Top-level M.A.R.S. configuration object."""
 
    paths: PathConfig = field(default_factory=PathConfig)
    mt5: MT5Config = field(default_factory=MT5Config)
    default_timezone: str = "UTC"
    default_symbol: str = "XAUUSD"
 
 
# Singleton-style default used by CLI entry points
DEFAULT_CONFIG = PlatformConfig()
"""
Liquidity density clustering via DBSCAN and KDE.
 
Research modules — expose density scores and pool levels with confidence.
"""
 
from __future__ import annotations
 
from dataclasses import dataclass
from typing import Literal, Optional
 
import numpy as np
import pandas as pd
 
from mars.features.market_structure.swings import BaseSwingDetector, FractalSwingDetector
 
 
@dataclass(frozen=True)
class LiquidityPool:
    price: float
    density: float
    confidence: float
    method: Literal["dbscan", "kde"]
    n_points: int
 
 
class DensityLiquidityDetector:
    """
    Estimate liquidity pools from swing prices using:
        1. DBSCAN clustering (if sklearn available)
        2. Kernel Density Estimation (SciPy)
    """
 
    name = "density_liquidity"
    version = "1.0.0"
 
    def __init__(
        self,
        swing_detector: Optional[BaseSwingDetector] = None,
        dbscan_eps_pct: float = 0.001,
        dbscan_min_samples: int = 2,
        kde_bandwidth: Optional[float] = None,
    ) -> None:
        self.swing_detector = swing_detector or FractalSwingDetector()
        self.dbscan_eps_pct = dbscan_eps_pct
        self.dbscan_min_samples = dbscan_min_samples
        self.kde_bandwidth = kde_bandwidth
 
    def _swing_prices(self, df: pd.DataFrame) -> np.ndarray:
        swings = self.swing_detector.detect(df)
        if not swings:
            return np.array([], dtype=float)
        return np.array([s.price for s in swings], dtype=float)
 
    def detect_dbscan(self, df: pd.DataFrame) -> list[LiquidityPool]:
        prices = self._swing_prices(df)
        if len(prices) < self.dbscan_min_samples:
            return []
        try:
            from sklearn.cluster import DBSCAN
        except ImportError:
            return []
 
        # Scale eps in price units using median price
        med = float(np.median(prices))
        eps = med * self.dbscan_eps_pct
        X = prices.reshape(-1, 1)
        labels = DBSCAN(eps=eps, min_samples=self.dbscan_min_samples).fit_predict(X)
 
        pools: list[LiquidityPool] = []
        for lab in sorted(set(labels)):
            if lab < 0:
                continue
            cluster = prices[labels == lab]
            density = float(len(cluster) / len(prices))
            conf = float(np.clip(density * 2.0, 0.0, 1.0))
            pools.append(
                LiquidityPool(
                    price=float(cluster.mean()),
                    density=density,
                    confidence=conf,
                    method="dbscan",
                    n_points=int(len(cluster)),
                )
            )
        return pools
 
    def detect_kde(self, df: pd.DataFrame, n_peaks: int = 5) -> list[LiquidityPool]:
        prices = self._swing_prices(df)
        if len(prices) < 3:
            return []
        try:
            from scipy.signal import find_peaks
            from scipy.stats import gaussian_kde
        except ImportError:
            return []
 
        try:
            kde = gaussian_kde(prices, bw_method=self.kde_bandwidth)
        except Exception:
            return []
 
        grid = np.linspace(prices.min(), prices.max(), 200)
        dens = kde(grid)
        dens_norm = dens / dens.max() if dens.max() > 0 else dens
        peaks, props = find_peaks(dens_norm, height=0.2)
        if len(peaks) == 0:
            return []
 
        # Take top peaks by density
        order = np.argsort(dens_norm[peaks])[::-1][:n_peaks]
        pools: list[LiquidityPool] = []
        for idx in order:
            p = peaks[idx]
            pools.append(
                LiquidityPool(
                    price=float(grid[p]),
                    density=float(dens_norm[p]),
                    confidence=float(dens_norm[p]),
                    method="kde",
                    n_points=int(len(prices)),
                )
            )
        return pools
 
    def detect(self, df: pd.DataFrame) -> list[LiquidityPool]:
        """Prefer DBSCAN; fall back to KDE."""
        pools = self.detect_dbscan(df)
        if not pools:
            pools = self.detect_kde(df)
        return pools
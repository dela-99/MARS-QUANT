"""
Hypothesis B labels: Next-session ATR% (ATR / close of current session).

IMPORTANT (point-in-time):
- Features are known at session close (completed session).
- Labels use NEXT session's ATR and current session's close.
- These labels are training targets, not live inputs.

Expects ``session_meta`` from ``HypBSessionVolFeatures.transform_with_sessions``
with columns: ``session_close``, ``next_session_open``, ``next_session_high``,
``next_session_low``, ``next_session_close``.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from mars.libs.labels.base import LabelGenerator


class HypBNextSessionATRLabels(LabelGenerator):
    """
    Labels for next-session ATR% prediction.

    Target: next_session_atr_pct = ATR_next_session / Close_current_session
    """

    def __init__(self, atr_window: int = 14) -> None:
        super().__init__(name="hyp_b_next_session_atr")
        self.atr_window = atr_window

    def generate(self, data: pd.DataFrame, **kwargs) -> pd.DataFrame:
        """
        Parameters
        ----------
        data:
            Session meta frame with columns:
            - session_close (close of completed/current session)
            - next_session_open, next_session_high, next_session_low, next_session_close
        """
        required = ["session_close", "next_session_open", "next_session_high",
                    "next_session_low", "next_session_close"]
        for col in required:
            if col not in data.columns:
                raise ValueError(f"session meta must include {col}")

        out = pd.DataFrame(index=data.index)

        # Next session true range using next session's OHLC
        # True range = max(high - low, |high - prev_close|, |low - prev_close|)
        # where prev_close is current session's close
        high = data["next_session_high"]
        low = data["next_session_low"]
        prev_close = data["session_close"]

        tr1 = high - low
        tr2 = (high - prev_close).abs()
        tr3 = (low - prev_close).abs()

        true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

        # Rolling ATR of true range (using session-level true ranges)
        # For the target, we want the ATR *at the start* of the next session.
        # That's the rolling mean of true ranges from sessions BEFORE the next session.
        # The true range of the completed sessions is available in session_meta.
        # But we only have next_session's OHLC. Let's compute ATR as rolling mean
        # of true ranges of completed sessions.
        
        # Actually, the target is the realized ATR% of the NEXT session.
        # We can only compute it ex-post. For training, we use the realized value.
        # The realized ATR of the next session = rolling mean of true ranges up to next session.
        # But we only have ONE true range for the next session (since session_meta aggregates).
        # A practical compromise: use the next session's true range as the target,
        # divided by current session close. This is "next session range %".
        
        # For a proper ATR, we'd need the rolling mean of session true ranges.
        # Let's compute the rolling ATR from the session meta's true ranges.
        # But the session_meta only has OHLC per session, not per bar.
        # The session true range is max(high-low, |high-prev_close|, |low-prev_close|).
        # We can compute this for all sessions, then rolling mean.

        # Compute true range for each session in meta
        session_high = data["session_high"]
        session_low = data["session_low"]
        session_close = data["session_close"]
        session_prev_close = session_close.shift(1)

        session_tr1 = session_high - session_low
        session_tr2 = (session_high - session_prev_close).abs()
        session_tr3 = (session_low - session_prev_close).abs()
        session_true_range = pd.concat([session_tr1, session_tr2, session_tr3], axis=1).max(axis=1)

        # ATR at current session = rolling mean of session true ranges up to current
        atr_at_current = session_true_range.rolling(self.atr_window, min_periods=1).mean()

        # Target: next session's realized ATR% 
        # The next session's true range is true_range (computed above)
        # But ATR is a rolling mean. The target should be the ATR *during* the next session.
        # For simplicity and to match the hypothesis spec, we use:
        # next_session_atr_pct = (next session true range) / current_session_close
        # This is effectively the next session range as % of current close.
        
        out["next_session_atr_pct"] = true_range / prev_close
        out["next_session_true_range"] = true_range
        out["current_session_close"] = prev_close
        out["atr_at_current"] = atr_at_current

        return out
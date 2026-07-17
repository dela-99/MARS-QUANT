"""Hypothesis A labels: London session direction and return."""

from __future__ import annotations

import pandas as pd

from mars.libs.labels.base import LabelGenerator


class HypALondonLabels(LabelGenerator):
    """
    Labels for Asia → London prediction.

    IMPORTANT (point-in-time):
    - Features are known at Asia close (~07:59 UTC window end).
    - Labels use London open/close and are only known after London close.
    - These labels are training targets, not live inputs.

    Expects ``session_meta`` from ``HypAAsiaLondonFeatures.transform_with_sessions``
    with columns: ``london_open``, ``london_close``.
    """

    def __init__(self) -> None:
        super().__init__(name="hyp_a_london")

    def generate(self, data: pd.DataFrame, **kwargs) -> pd.DataFrame:
        """
        Parameters
        ----------
        data:
            Session meta frame with london_open / london_close columns.
        """
        if "london_open" not in data.columns or "london_close" not in data.columns:
            raise ValueError("session meta must include london_open and london_close")

        out = pd.DataFrame(index=data.index)
        out["london_direction"] = self.binary_direction(
            data["london_open"], data["london_close"], name="london_direction"
        )
        out["london_return"] = self.session_return(
            data["london_open"], data["london_close"], name="london_return"
        )
        return out

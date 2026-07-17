"""
PyTorch model definitions (LSTM / Transformer) ported from legacy research.

NOTE: Training scripts in legacy used random train/test splits — do not treat
saved DL metrics as production-grade until re-trained with time-aware splits.
These classes provide architecture + BaseModel-compatible save/load of state_dict.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Optional

import numpy as np

from mars.libs.models.base import ArrayLike, BaseModel

try:
    import torch
    import torch.nn as nn
    from torch.utils.data import DataLoader, Dataset

    TORCH_AVAILABLE = True
except ImportError:  # pragma: no cover
    TORCH_AVAILABLE = False
    torch = None  # type: ignore
    nn = None  # type: ignore


if TORCH_AVAILABLE:

    class TimeSeriesDataset(Dataset):
        def __init__(self, X: np.ndarray, y: np.ndarray) -> None:
            self.X = torch.tensor(X, dtype=torch.float32)
            self.y = torch.tensor(y, dtype=torch.float32)

        def __len__(self) -> int:
            return len(self.X)

        def __getitem__(self, idx: int):
            return self.X[idx], self.y[idx]

    class LSTMNet(nn.Module):
        def __init__(self, input_size: int, hidden_size: int = 50, output_size: int = 1) -> None:
            super().__init__()
            self.lstm = nn.LSTM(input_size, hidden_size, batch_first=True)
            self.linear = nn.Linear(hidden_size, output_size)

        def forward(self, x):
            lstm_out, _ = self.lstm(x)
            return self.linear(lstm_out[:, -1, :])

    class PositionalEncoding(nn.Module):
        def __init__(self, d_model: int, max_len: int = 5000) -> None:
            super().__init__()
            pe = torch.zeros(max_len, d_model)
            position = torch.arange(0, max_len, dtype=torch.float).unsqueeze(1)
            div_term = torch.exp(
                torch.arange(0, d_model, 2).float() * (-math.log(10000.0) / d_model)
            )
            pe[:, 0::2] = torch.sin(position * div_term)
            pe[:, 1::2] = torch.cos(position * div_term)
            pe = pe.unsqueeze(0).transpose(0, 1)
            self.register_buffer("pe", pe)

        def forward(self, x):
            return x + self.pe[: x.size(0), :]

    class TransformerNet(nn.Module):
        def __init__(
            self,
            input_size: int,
            hidden_size: int = 64,
            nhead: int = 4,
            nlayers: int = 2,
            output_size: int = 1,
        ) -> None:
            super().__init__()
            self.d_model = hidden_size
            self.embedding = nn.Linear(input_size, hidden_size)
            self.pos_encoder = PositionalEncoding(hidden_size)
            encoder_layers = nn.TransformerEncoderLayer(
                d_model=hidden_size, nhead=nhead, batch_first=True
            )
            self.transformer_encoder = nn.TransformerEncoder(encoder_layers, num_layers=nlayers)
            self.decoder = nn.Linear(hidden_size, output_size)

        def forward(self, src):
            src = self.embedding(src) * math.sqrt(self.d_model)
            src = self.pos_encoder(src)
            output = self.transformer_encoder(src)
            return self.decoder(output[:, -1, :])


class _TorchClassifierBase(BaseModel):
    """Shared fit/predict for sequence classifiers (time-aware split expected upstream)."""

    net_cls = None  # set by subclass

    def __init__(
        self,
        name: str,
        input_size: int,
        hidden_size: int = 50,
        lr: float = 1e-3,
        epochs: int = 20,
        batch_size: int = 64,
        **net_kwargs: Any,
    ) -> None:
        if not TORCH_AVAILABLE:
            raise ImportError("PyTorch is required for deep learning models.")
        super().__init__(name=name)
        self.input_size = input_size
        self.hidden_size = hidden_size
        self.lr = lr
        self.epochs = epochs
        self.batch_size = batch_size
        self.net_kwargs = net_kwargs
        self.net = self._build_net()

    def _build_net(self):
        return self.net_cls(  # type: ignore[misc]
            input_size=self.input_size,
            hidden_size=self.hidden_size,
            **self.net_kwargs,
        )

    def fit(self, X: ArrayLike, y: ArrayLike, **kwargs: Any) -> "_TorchClassifierBase":
        X_arr = np.asarray(X, dtype=np.float32)
        y_arr = np.asarray(y, dtype=np.float32)
        dataset = TimeSeriesDataset(X_arr, y_arr)
        loader = DataLoader(dataset, batch_size=self.batch_size, shuffle=True)
        criterion = nn.BCEWithLogitsLoss()
        optimizer = torch.optim.Adam(self.net.parameters(), lr=self.lr)
        self.net.train()
        for _ in range(self.epochs):
            for batch_X, batch_y in loader:
                outputs = self.net(batch_X).squeeze(-1)
                loss = criterion(outputs, batch_y.float())
                optimizer.zero_grad()
                loss.backward()
                optimizer.step()
        self.is_fitted = True
        return self

    def predict(self, X: ArrayLike) -> np.ndarray:
        proba = self.predict_proba(X)
        return (proba >= 0.5).astype(int)

    def predict_proba(self, X: ArrayLike) -> np.ndarray:
        if not self.is_fitted:
            raise RuntimeError("Model not fitted.")
        X_arr = np.asarray(X, dtype=np.float32)
        self.net.eval()
        with torch.inference_mode():
            t = torch.tensor(X_arr, dtype=torch.float32)
            logits = self.net(t).squeeze(-1)
            probs = torch.sigmoid(logits).cpu().numpy()
        return np.asarray(probs)

    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        torch.save(
            {
                "state_dict": self.net.state_dict(),
                "input_size": self.input_size,
                "hidden_size": self.hidden_size,
                "net_kwargs": self.net_kwargs,
                "name": self.name,
            },
            path,
        )

    @classmethod
    def load(cls, path: str | Path) -> "_TorchClassifierBase":
        payload = torch.load(path, map_location="cpu", weights_only=False)
        # Legacy pure state_dict files
        if isinstance(payload, dict) and "state_dict" in payload:
            obj = cls(
                name=payload.get("name", cls.__name__),
                input_size=payload["input_size"],
                hidden_size=payload.get("hidden_size", 50),
                **payload.get("net_kwargs", {}),
            )
            obj.net.load_state_dict(payload["state_dict"])
            obj.is_fitted = True
            return obj
        # Raw state_dict — caller must construct architecture first
        raise ValueError(
            "Legacy .pth files that are raw state_dicts must be loaded via "
            "architecture.load_state_dict(). Prefer re-saving through M.A.R.S. wrappers."
        )


class LSTMClassifier(_TorchClassifierBase):
    net_cls = LSTMNet if TORCH_AVAILABLE else None

    def __init__(self, input_size: int, **kwargs: Any) -> None:
        super().__init__(name="lstm_classifier", input_size=input_size, **kwargs)


class TransformerClassifier(_TorchClassifierBase):
    net_cls = TransformerNet if TORCH_AVAILABLE else None

    def __init__(self, input_size: int, nhead: int = 4, nlayers: int = 2, **kwargs: Any) -> None:
        super().__init__(
            name="transformer_classifier",
            input_size=input_size,
            nhead=nhead,
            nlayers=nlayers,
            **kwargs,
        )

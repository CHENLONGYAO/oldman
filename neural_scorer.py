"""
神經網路動作品質評分（LSTM 與 ST-GCN）。

兩種架構可選：
  - LSTM ：輸入關節角度時間序列 (T, F)，雙向 LSTM → 分數
  - STGCN：輸入 3D 關鍵點時間序列 (3, T, V)，圖卷積 → 分數

若 torch 未安裝或無預訓練權重，`NeuralScorer.available` 為 False，
`predict()` 回傳 None；呼叫端（scoring.py）會以 DTW 為主、神經網路為輔。

權重路徑：
  weights/lstm_quality.pth
  weights/stgcn_quality.pth
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional
import numpy as np

try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    TORCH_OK = True
except Exception:  # pragma: no cover
    TORCH_OK = False


_WEIGHTS_DIR = Path(__file__).parent / "weights"


# ---------------- LSTM ----------------
if TORCH_OK:

    class LSTMQualityHead(nn.Module):
        def __init__(self, in_dim: int = 8, hidden: int = 128, layers: int = 2, dropout: float = 0.2):
            super().__init__()
            self.lstm = nn.LSTM(
                in_dim, hidden, layers,
                batch_first=True, bidirectional=True, dropout=dropout if layers > 1 else 0.0,
            )
            self.head = nn.Sequential(
                nn.Linear(hidden * 2, 64), nn.ReLU(),
                nn.Dropout(dropout),
                nn.Linear(64, 1), nn.Sigmoid(),
            )

        def forward(self, x: torch.Tensor) -> torch.Tensor:
            h, _ = self.lstm(x)
            pooled = h.mean(dim=1)
            return self.head(pooled).squeeze(-1) * 100.0


# ---------------- STGCN ----------------
# MediaPipe Pose 33-點骨架連線
_MP_EDGES = [
    (11, 13), (13, 15), (12, 14), (14, 16),
    (11, 12),
    (11, 23), (12, 24), (23, 24),
    (23, 25), (25, 27), (24, 26), (26, 28),
    (15, 17), (15, 19), (15, 21), (17, 19),
    (16, 18), (16, 20), (16, 22), (18, 20),
    (27, 29), (27, 31), (29, 31),
    (28, 30), (28, 32), (30, 32),
    (0, 11), (0, 12),
]


def _symmetric_normalized_adjacency(num_joints: int = 33) -> np.ndarray:
    A = np.zeros((num_joints, num_joints), dtype=np.float32)
    for i, j in _MP_EDGES:
        A[i, j] = 1.0
        A[j, i] = 1.0
    A += np.eye(num_joints, dtype=np.float32)
    d = A.sum(axis=1)
    d_inv_sqrt = np.diag(1.0 / np.sqrt(np.maximum(d, 1e-9)))
    return d_inv_sqrt @ A @ d_inv_sqrt


if TORCH_OK:

    class STGCNBlock(nn.Module):
        def __init__(self, in_c: int, out_c: int, A: np.ndarray, t_kernel: int = 9):
            super().__init__()
            self.register_buffer("A", torch.from_numpy(A))
            self.gconv = nn.Conv2d(in_c, out_c, kernel_size=1)
            pad = (t_kernel - 1) // 2
            self.tconv = nn.Conv2d(out_c, out_c, kernel_size=(t_kernel, 1), padding=(pad, 0))
            self.bn = nn.BatchNorm2d(out_c)
            self.residual = (
                nn.Identity() if in_c == out_c else nn.Conv2d(in_c, out_c, kernel_size=1)
            )

        def forward(self, x: torch.Tensor) -> torch.Tensor:
            # x: (B, C, T, V)
            res = self.residual(x)
            x = torch.einsum("bctv,vw->bctw", x, self.A)
            x = self.gconv(x)
            x = self.tconv(x)
            x = self.bn(x)
            return F.relu(x + res)


    class STGCNQuality(nn.Module):
        def __init__(self, in_c: int = 3, num_joints: int = 33):
            super().__init__()
            A = _symmetric_normalized_adjacency(num_joints)
            self.blocks = nn.ModuleList([
                STGCNBlock(in_c, 64, A),
                STGCNBlock(64, 128, A),
                STGCNBlock(128, 256, A),
            ])
            self.pool = nn.AdaptiveAvgPool2d(1)
            self.head = nn.Sequential(
                nn.Flatten(),
                nn.Linear(256, 64), nn.ReLU(),
                nn.Dropout(0.2),
                nn.Linear(64, 1), nn.Sigmoid(),
            )

        def forward(self, x: torch.Tensor) -> torch.Tensor:
            for blk in self.blocks:
                x = blk(x)
            x = self.pool(x)
            return self.head(x).squeeze(-1) * 100.0


class NeuralScorer:
    """載入 LSTM 或 STGCN 的外觀類別。"""

    def __init__(self, arch: str = "lstm", weights: Optional[str] = None,
                 in_dim: int = 8, num_joints: int = 33):
        if arch not in ("lstm", "stgcn"):
            raise ValueError(f"Unsupported arch: {arch}")
        self.arch = arch
        self.available = False
        self.model = None
        self._last_error: Optional[str] = None
        self.in_dim = in_dim
        self.num_joints = num_joints

        if not TORCH_OK:
            self._last_error = "PyTorch 未安裝"
            return

        path = Path(weights) if weights else _WEIGHTS_DIR / f"{arch}_quality.pth"
        if not path.exists():
            self._last_error = "找不到權重檔"
            return

        try:
            if arch == "lstm":
                model = LSTMQualityHead(in_dim=in_dim)
            else:
                model = STGCNQuality(in_c=3, num_joints=num_joints)
            state = torch.load(path, map_location="cpu")
            if isinstance(state, dict) and "model" in state:
                state = state["model"]
            model.load_state_dict(state, strict=False)
            model.eval()
            self.model = model
            self.available = True
        except Exception as exc:  # pragma: no cover
            self._last_error = f"載入失敗：{exc}"
            self.available = False

    @property
    def status(self) -> str:
        if self.available:
            return f"{self.arch.upper()} scorer 已啟用"
        return f"{self.arch.upper()} scorer 未啟用（{self._last_error or '未知'}）"

    def predict(
        self,
        seq_world: Optional[np.ndarray] = None,
        angle_feats: Optional[np.ndarray] = None,
    ) -> Optional[float]:
        """LSTM 使用 angle_feats (T, F)；STGCN 使用 seq_world (T, J, 3)。"""
        if not self.available or self.model is None:
            return None
        import torch
        with torch.no_grad():
            if self.arch == "lstm":
                if angle_feats is None:
                    return None
                x = torch.from_numpy(angle_feats.astype(np.float32)).unsqueeze(0)
                score = float(self.model(x).item())
            else:
                if seq_world is None:
                    return None
                # (T, J, 3) → (B=1, C=3, T, V=J)
                arr = seq_world.astype(np.float32).transpose(2, 0, 1)[None]
                x = torch.from_numpy(arr)
                score = float(self.model(x).item())
        return max(0.0, min(100.0, score))

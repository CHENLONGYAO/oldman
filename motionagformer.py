"""
MotionAGFormer 3D 姿態提升器（選用）。

真實 MotionAGFormer（Mehraban et al., CVPR 2024）將 2D 關鍵點序列提升為 3D，
使用 attention-graph transformer，需要在 Human3.6M 等資料集上訓練的權重。

本模組提供可插拔介面：
  * 若 `torch` 已安裝且找得到權重檔，啟用神經網路 2D→3D 提升
  * 否則 `available` 為 False，呼叫端回落到 MediaPipe 內建 3D

權重位置（依序嘗試）：
  1. 建構子 weights 參數
  2. 環境變數 MOTIONAGFORMER_WEIGHTS
  3. 專案內 weights/motionagformer.pth
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, Union

import numpy as np

try:
    import torch
    import torch.nn as nn
    TORCH_OK = True
except Exception:  # pragma: no cover
    TORCH_OK = False


_WEIGHT_ENV = "MOTIONAGFORMER_WEIGHTS"
_DEFAULT_WEIGHT = Path(__file__).parent / "weights" / "motionagformer.pth"


if TORCH_OK:

    class AGFormerBlock(nn.Module):
        """AG-Transformer block：關節注意力 + 時序注意力。

        實際論文實作較複雜，此為簡化版，保留訓練/推論可用性。
        """
        def __init__(self, dim: int = 128, heads: int = 4, ff: int = 256, dropout: float = 0.1):
            super().__init__()
            self.spatial = nn.MultiheadAttention(dim, heads, batch_first=True)
            self.temporal = nn.MultiheadAttention(dim, heads, batch_first=True)
            self.norm1 = nn.LayerNorm(dim)
            self.norm2 = nn.LayerNorm(dim)
            self.norm3 = nn.LayerNorm(dim)
            self.ff = nn.Sequential(
                nn.Linear(dim, ff), nn.GELU(), nn.Dropout(dropout),
                nn.Linear(ff, dim), nn.Dropout(dropout),
            )

        def forward(self, x: torch.Tensor) -> torch.Tensor:
            # x: (B, T, J, D)
            B, T, J, D = x.shape
            # spatial attention across joints
            s = x.reshape(B * T, J, D)
            s = self.norm1(s + self.spatial(s, s, s)[0])
            # temporal attention across frames
            t = s.reshape(B, T, J, D).transpose(1, 2).reshape(B * J, T, D)
            t = self.norm2(t + self.temporal(t, t, t)[0])
            t = t.reshape(B, J, T, D).transpose(1, 2)
            # feed-forward
            return self.norm3(t + self.ff(t))


    class MotionAGFormerNet(nn.Module):
        """MotionAGFormer 骨架。輸入 (B, T, J, 2) → 輸出 (B, T, J, 3)。"""
        def __init__(self, num_joints: int = 17, dim: int = 128, num_layers: int = 6):
            super().__init__()
            self.num_joints = num_joints
            self.input_proj = nn.Linear(2, dim)
            self.joint_embed = nn.Parameter(torch.randn(1, 1, num_joints, dim) * 0.02)
            self.blocks = nn.ModuleList([AGFormerBlock(dim) for _ in range(num_layers)])
            self.head = nn.Linear(dim, 3)

        def forward(self, x: torch.Tensor) -> torch.Tensor:
            h = self.input_proj(x) + self.joint_embed
            for blk in self.blocks:
                h = blk(h)
            return self.head(h)

else:  # Torch 不可用時的型別佔位
    class MotionAGFormerNet:  # type: ignore[no-redef]
        pass


class MotionAGFormer:
    """可插拔的 2D→3D 提升器外觀類別。"""

    def __init__(self, weights: Optional[Union[str, Path]] = None, num_joints: int = 17):
        self.available: bool = False
        self.model: Optional["MotionAGFormerNet"] = None
        self.num_joints = num_joints
        self._last_error: Optional[str] = None

        if not TORCH_OK:
            self._last_error = "PyTorch 未安裝"
            return

        candidates = [weights, os.environ.get(_WEIGHT_ENV), _DEFAULT_WEIGHT]
        path = next((Path(p) for p in candidates if p and Path(p).exists()), None)
        if path is None:
            self._last_error = "找不到 MotionAGFormer 權重"
            return

        try:
            self.model = MotionAGFormerNet(num_joints=num_joints)
            state = torch.load(path, map_location="cpu")
            if isinstance(state, dict) and "model" in state:
                state = state["model"]
            self.model.load_state_dict(state, strict=False)
            self.model.eval()
            self.available = True
        except Exception as exc:  # pragma: no cover
            self._last_error = f"載入失敗：{exc}"
            self.model = None
            self.available = False

    @property
    def status(self) -> str:
        if self.available:
            return "MotionAGFormer 已啟用"
        return f"MotionAGFormer 未啟用（{self._last_error or '未知原因'}）"

    def lift(self, kp_2d: np.ndarray) -> Optional[np.ndarray]:
        """將 2D 關鍵點序列提升為 3D。

        kp_2d : (T, J, 2)  normalized 影像座標
        return: (T, J, 3) 或 None（未啟用時）
        """
        if not self.available or self.model is None:
            return None
        import torch
        x = torch.from_numpy(kp_2d.astype(np.float32)).unsqueeze(0)
        with torch.no_grad():
            y = self.model(x)
        return y.squeeze(0).numpy()

"""
Multi-model embedding service for text, pose sequences, and video.

Backends (auto-selected by what's installed, in order of preference):

Text embeddings:
1. Voyage AI (`voyage-3-large`) — best multilingual, requires VOYAGE_API_KEY
2. sentence-transformers `all-MiniLM-L6-v2` (384d) or `multilingual-e5-large`
3. Hash-based bag-of-words fallback (always available, lower quality)

Pose embeddings:
- Custom: angle-feature aggregation across frames (statistical embedding)
- Lightweight: works without external models

Video embeddings:
- CLIP-like image embeddings averaged over keyframes (if torch+transformers)

All embedders return np.ndarray; default dim is 384.
"""
from __future__ import annotations
import hashlib
import math
import os
import re
from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence
import numpy as np


DEFAULT_TEXT_DIM = 384


# ============================================================
# Text embedding backends
# ============================================================
class _BackendBase:
    name = "base"
    dim = 0

    def embed(self, texts: Sequence[str]) -> np.ndarray:
        raise NotImplementedError


class VoyageBackend(_BackendBase):
    """Voyage AI embeddings — best quality multilingual."""
    name = "voyage"
    dim = 1024

    def __init__(self):
        try:
            import voyageai  # type: ignore
        except ImportError as e:
            raise RuntimeError("voyageai not installed") from e
        if not os.environ.get("VOYAGE_API_KEY"):
            raise RuntimeError("VOYAGE_API_KEY not set")
        self._client = voyageai.Client()
        self.dim = 1024

    def embed(self, texts: Sequence[str]) -> np.ndarray:
        result = self._client.embed(
            list(texts), model="voyage-3-large", input_type="document"
        )
        return np.array(result.embeddings, dtype=np.float32)


class SentenceTransformersBackend(_BackendBase):
    """SBERT MiniLM or multilingual-e5."""
    name = "sentence_transformers"

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as e:
            raise RuntimeError("sentence-transformers not installed") from e
        self._model = SentenceTransformer(model_name)
        self.dim = self._model.get_sentence_embedding_dimension()
        self.name = f"st:{model_name}"

    def embed(self, texts: Sequence[str]) -> np.ndarray:
        out = self._model.encode(list(texts), normalize_embeddings=True,
                                  show_progress_bar=False)
        return np.array(out, dtype=np.float32)


class HashBackend(_BackendBase):
    """Always-available fallback. Uses character n-grams + hashing.

    Lower quality but acceptable for keyword-style retrieval. NOT semantic.
    """
    name = "hash"

    def __init__(self, dim: int = DEFAULT_TEXT_DIM):
        self.dim = dim

    def embed(self, texts: Sequence[str]) -> np.ndarray:
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for i, t in enumerate(texts):
            out[i] = self._embed_one(t)
        return out

    def _embed_one(self, text: str) -> np.ndarray:
        v = np.zeros(self.dim, dtype=np.float32)
        if not text:
            return v
        text = text.lower().strip()

        tokens = re.findall(r"\w+", text)
        for token in tokens:
            for n in (2, 3):
                for i in range(len(token) - n + 1):
                    ng = token[i:i + n]
                    h = int(hashlib.sha256(ng.encode()).hexdigest()[:8], 16)
                    sign = 1 if h & 1 else -1
                    v[h % self.dim] += sign

        norm = np.linalg.norm(v)
        if norm > 1e-9:
            v = v / norm
        return v


# ============================================================
# Pose embedding (custom statistical)
# ============================================================
def embed_pose_sequence(world_seq: np.ndarray,
                        target_dim: int = 384) -> np.ndarray:
    """Embed a (T, 33, 3) pose sequence into a fixed-size vector.

    Strategy: per-joint angle statistics + motion features.
    Output is L2-normalized.
    """
    if len(world_seq) == 0:
        return np.zeros(target_dim, dtype=np.float32)

    try:
        from biomechanics import compute_anatomical_angles
    except ImportError:
        return _embed_pose_fallback(world_seq, target_dim)

    angles_per_frame = []
    for frame in world_seq:
        try:
            a = compute_anatomical_angles(frame)
            angles_per_frame.append(a)
        except Exception:
            continue

    if not angles_per_frame:
        return _embed_pose_fallback(world_seq, target_dim)

    keys = sorted({k for d in angles_per_frame for k in d})
    feats = []
    for k in keys:
        vals = np.array([d.get(k, 0.0) for d in angles_per_frame])
        feats.extend([
            float(vals.mean()),
            float(vals.std()),
            float(vals.max()),
            float(vals.min()),
            float(vals.max() - vals.min()),
            float(np.median(vals)),
        ])

    motion = np.linalg.norm(np.diff(world_seq, axis=0), axis=2)
    feats.extend([
        float(motion.mean()),
        float(motion.max()),
        float(motion.std()),
        float(len(world_seq)),
    ])

    arr = np.array(feats, dtype=np.float32)

    if len(arr) >= target_dim:
        out = arr[:target_dim]
    else:
        out = np.zeros(target_dim, dtype=np.float32)
        out[:len(arr)] = arr

    norm = np.linalg.norm(out)
    if norm > 1e-9:
        out = out / norm
    return out


def _embed_pose_fallback(seq: np.ndarray, target_dim: int) -> np.ndarray:
    """Pure-stats fallback when biomechanics module not available."""
    flat = seq.reshape(seq.shape[0], -1)
    if flat.size == 0:
        return np.zeros(target_dim, dtype=np.float32)

    feats = np.concatenate([
        flat.mean(axis=0), flat.std(axis=0),
        flat.max(axis=0), flat.min(axis=0),
    ])

    if len(feats) >= target_dim:
        out = feats[:target_dim]
    else:
        out = np.zeros(target_dim, dtype=np.float32)
        out[:len(feats)] = feats
    out = out.astype(np.float32)
    norm = np.linalg.norm(out)
    if norm > 1e-9:
        out = out / norm
    return out


# ============================================================
# Video embedding (keyframes via CLIP if available)
# ============================================================
def embed_video_keyframes(frames: List[np.ndarray]) -> Optional[np.ndarray]:
    """Embed video as average of CLIP embeddings of keyframes.

    Returns None if CLIP unavailable.
    """
    try:
        import torch
        from transformers import CLIPModel, CLIPProcessor
    except ImportError:
        return None

    if not frames:
        return None

    try:
        model_id = "openai/clip-vit-base-patch32"
        model = CLIPModel.from_pretrained(model_id)
        processor = CLIPProcessor.from_pretrained(model_id)
        model.eval()
    except Exception:
        return None

    try:
        import cv2
        from PIL import Image

        pil_frames = []
        for f in frames[:8]:
            rgb = cv2.cvtColor(f, cv2.COLOR_BGR2RGB)
            pil_frames.append(Image.fromarray(rgb))

        inputs = processor(images=pil_frames, return_tensors="pt")
        with torch.no_grad():
            features = model.get_image_features(**inputs)
            features = features / features.norm(dim=-1, keepdim=True)
            avg = features.mean(dim=0)
            avg = avg / avg.norm()
        return avg.cpu().numpy().astype(np.float32)
    except Exception:
        return None


# ============================================================
# Public service singleton
# ============================================================
class EmbeddingService:
    """Unified embedding service. Auto-picks best backend."""

    def __init__(self, prefer: Optional[str] = None):
        self._text_backend = self._build_text_backend(prefer)

    def _build_text_backend(self, prefer: Optional[str]) -> _BackendBase:
        if prefer == "voyage" or prefer is None:
            try:
                return VoyageBackend()
            except Exception:
                pass
        if prefer in (None, "sbert", "sentence_transformers"):
            try:
                return SentenceTransformersBackend()
            except Exception:
                pass
            try:
                return SentenceTransformersBackend(
                    "intfloat/multilingual-e5-small"
                )
            except Exception:
                pass
        return HashBackend()

    @property
    def text_backend_name(self) -> str:
        return self._text_backend.name

    @property
    def text_dim(self) -> int:
        return self._text_backend.dim

    def embed_text(self, text: str) -> np.ndarray:
        return self._text_backend.embed([text])[0]

    def embed_texts(self, texts: Sequence[str]) -> np.ndarray:
        return self._text_backend.embed(list(texts))

    def embed_pose(self, seq: np.ndarray, dim: Optional[int] = None) -> np.ndarray:
        return embed_pose_sequence(seq, target_dim=dim or self.text_dim)

    def embed_video(self, frames: List[np.ndarray]) -> Optional[np.ndarray]:
        return embed_video_keyframes(frames)


_SERVICE: Optional[EmbeddingService] = None


def get_service() -> EmbeddingService:
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = EmbeddingService()
    return _SERVICE


def embed_text(text: str) -> np.ndarray:
    return get_service().embed_text(text)


def embed_pose(seq: np.ndarray, dim: int = 384) -> np.ndarray:
    return embed_pose_sequence(seq, target_dim=dim)

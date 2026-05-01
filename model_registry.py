"""
Model registry: track model versions, weights, and route requests.

Manages multiple variants of the same model so you can:
- Pin a specific version per user (A/B testing, treatment cohorts)
- Roll back to a previous version if a new one regresses
- Inspect performance metrics per variant
- Lazily load weights on demand (don't load every model at startup)

Stored configurations include the model file path, framework
(pytorch/onnx/huggingface), input shape, dim, and metadata.
"""
from __future__ import annotations
import hashlib
import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from db import execute_query, execute_update


@dataclass
class ModelConfig:
    """Configuration for one model version."""
    model_id: str             # canonical name (e.g., "pose_estimator")
    version: str              # semver-ish: "v1.0", "v1.1-onnx-int8"
    framework: str            # pytorch / onnx / huggingface / mediapipe
    weights_path: Optional[str] = None  # local path or HF repo
    description: str = ""
    metrics: Dict[str, float] = field(default_factory=dict)
    config: Dict[str, Any] = field(default_factory=dict)
    is_default: bool = False
    is_active: bool = True
    tags: List[str] = field(default_factory=list)


# ============================================================
# Built-in registry
# ============================================================
BUILTIN_MODELS: List[ModelConfig] = [
    # Pose estimation
    ModelConfig(
        model_id="pose_estimator",
        version="mediapipe-heavy-v1",
        framework="mediapipe",
        description="MediaPipe Pose, complexity=2 (heavy). Default.",
        metrics={"avg_inference_ms": 35, "pck_0.5": 0.88},
        config={"complexity": 2, "smooth_landmarks": True},
        is_default=True,
        tags=["pose", "default"],
    ),
    ModelConfig(
        model_id="pose_estimator",
        version="mediapipe-full-v1",
        framework="mediapipe",
        description="MediaPipe Pose, complexity=1. Faster, slightly less accurate.",
        metrics={"avg_inference_ms": 18, "pck_0.5": 0.83},
        config={"complexity": 1},
        tags=["pose", "fast"],
    ),
    ModelConfig(
        model_id="pose_estimator",
        version="rtmpose-x-v1",
        framework="onnx",
        weights_path="weights/rtmpose-x.onnx",
        description="RTMPose-X — SOTA accuracy, requires ONNX runtime.",
        metrics={"avg_inference_ms": 50, "pck_0.5": 0.92},
        config={"input_size": [288, 384]},
        tags=["pose", "sota"],
    ),
    ModelConfig(
        model_id="pose_estimator",
        version="sapiens-1b-v1",
        framework="huggingface",
        weights_path="facebook/sapiens-pose-1b",
        description="Meta Sapiens 1B — best accuracy, GPU recommended.",
        metrics={"pck_0.5": 0.95},
        config={"input_size": [768, 1024]},
        tags=["pose", "sota", "gpu_only"],
    ),

    # Quality scoring
    ModelConfig(
        model_id="quality_scorer",
        version="lstm-v1",
        framework="pytorch",
        weights_path="weights/lstm_quality.pth",
        description="Bidirectional LSTM, 128 hidden, 2 layers.",
        is_default=True,
        config={"hidden": 128, "layers": 2},
        tags=["scoring"],
    ),
    ModelConfig(
        model_id="quality_scorer",
        version="stgcn-v1",
        framework="pytorch",
        weights_path="weights/stgcn_quality.pth",
        description="ST-GCN on skeleton graph.",
        config={},
        tags=["scoring"],
    ),
    ModelConfig(
        model_id="quality_scorer",
        version="lstm-onnx-int8",
        framework="onnx",
        weights_path="weights/lstm_quality_int8.onnx",
        description="LSTM ONNX INT8 — 3-4x faster on CPU.",
        metrics={"speedup_vs_pytorch": 3.2},
        tags=["scoring", "fast"],
    ),

    # 3D lifting
    ModelConfig(
        model_id="pose_lifter",
        version="motionagformer-v1",
        framework="pytorch",
        weights_path="weights/motionagformer.pth",
        description="MotionAGFormer — 2D→3D pose lifting, 27 frames context.",
        is_default=True,
        config={"context_frames": 27},
        tags=["lifter"],
    ),
    ModelConfig(
        model_id="pose_lifter",
        version="motionbert-v1",
        framework="huggingface",
        weights_path="walterzhu/MotionBERT-Lite",
        description="MotionBERT — SOTA 3D pose lifting from 2D.",
        metrics={"mpjpe_h36m": 39.2},
        config={"context_frames": 243},
        tags=["lifter", "sota"],
    ),

    # Embedding models
    ModelConfig(
        model_id="text_embedder",
        version="hash-fallback",
        framework="custom",
        description="Always-available hash-based fallback.",
        is_default=True,
        config={"dim": 384},
        tags=["embedding"],
    ),
    ModelConfig(
        model_id="text_embedder",
        version="minilm-l6-v2",
        framework="sentence_transformers",
        weights_path="all-MiniLM-L6-v2",
        description="Compact SBERT, 384d, English.",
        config={"dim": 384},
        tags=["embedding"],
    ),
    ModelConfig(
        model_id="text_embedder",
        version="multilingual-e5-large",
        framework="sentence_transformers",
        weights_path="intfloat/multilingual-e5-large",
        description="Multilingual E5 — best for zh+en, 1024d.",
        config={"dim": 1024},
        tags=["embedding", "multilingual"],
    ),
    ModelConfig(
        model_id="text_embedder",
        version="voyage-3-large",
        framework="api",
        description="Voyage AI — SOTA multilingual, requires API key.",
        config={"dim": 1024},
        tags=["embedding", "api", "sota"],
    ),

    # LLMs
    ModelConfig(
        model_id="llm",
        version="claude-haiku-4-5",
        framework="api",
        description="Claude Haiku 4.5 — fast, supports vision + tool use.",
        is_default=True,
        config={"model": "claude-haiku-4-5-20251001",
                "max_tokens": 1024},
        tags=["llm", "api", "vision"],
    ),
    ModelConfig(
        model_id="llm",
        version="claude-sonnet-4-6",
        framework="api",
        description="Claude Sonnet 4.6 — for complex reasoning.",
        config={"model": "claude-sonnet-4-6", "max_tokens": 2048},
        tags=["llm", "api", "smart"],
    ),
    ModelConfig(
        model_id="llm",
        version="claude-opus-4-7",
        framework="api",
        description="Claude Opus 4.7 — best reasoning, highest cost.",
        config={"model": "claude-opus-4-7", "max_tokens": 4096},
        tags=["llm", "api", "best"],
    ),
    ModelConfig(
        model_id="llm",
        version="openai-gpt-5.1",
        framework="api",
        description="OpenAI GPT-5.1 — strong reasoning via Responses API.",
        config={"model": "gpt-5.1", "max_output_tokens": 2048},
        tags=["llm", "api", "smart"],
    ),
    ModelConfig(
        model_id="llm",
        version="openai-gpt-5-mini",
        framework="api",
        description="OpenAI GPT-5 mini — faster and cost-efficient.",
        config={"model": "gpt-5-mini", "max_output_tokens": 1024},
        tags=["llm", "api", "fast"],
    ),
    ModelConfig(
        model_id="llm",
        version="ollama-llama3.3",
        framework="ollama",
        weights_path="llama3.3",
        description="Local Llama 3.3 via Ollama — privacy, no API cost.",
        config={"endpoint": "http://localhost:11434"},
        tags=["llm", "local"],
    ),
]


# ============================================================
# Registry
# ============================================================
class ModelRegistry:
    """Holds all configs + tracks active version per model_id."""

    def __init__(self):
        self._configs: Dict[str, List[ModelConfig]] = {}
        self._active: Dict[str, str] = {}  # model_id -> version
        self._load_builtin()
        self._load_overrides()

    def _load_builtin(self) -> None:
        for cfg in BUILTIN_MODELS:
            self._configs.setdefault(cfg.model_id, []).append(cfg)
            if cfg.is_default and cfg.model_id not in self._active:
                self._active[cfg.model_id] = cfg.version

    def _load_overrides(self) -> None:
        try:
            rows = execute_query(
                """
                SELECT data_json FROM offline_cache
                WHERE user_id = '_models'
                  AND cache_type = 'active_versions'
                ORDER BY created_at DESC LIMIT 1
                """,
                (),
            )
            if rows:
                data = json.loads(rows[0]["data_json"])
                self._active.update(data)
        except Exception:
            pass

    def list_versions(self, model_id: str) -> List[ModelConfig]:
        return self._configs.get(model_id, [])

    def get(self, model_id: str,
            version: Optional[str] = None) -> Optional[ModelConfig]:
        v = version or self._active.get(model_id)
        if not v:
            return None
        for cfg in self._configs.get(model_id, []):
            if cfg.version == v:
                return cfg
        return None

    def get_active(self, model_id: str) -> Optional[ModelConfig]:
        return self.get(model_id)

    def set_active(self, model_id: str, version: str,
                   persist: bool = True) -> bool:
        if not self.get(model_id, version):
            return False
        self._active[model_id] = version
        if persist:
            self._save_active()
        return True

    def _save_active(self) -> None:
        try:
            execute_update(
                """
                DELETE FROM offline_cache
                WHERE user_id = '_models'
                  AND cache_type = 'active_versions'
                """,
                (),
            )
            execute_update(
                """
                INSERT INTO offline_cache
                (user_id, cache_type, data_json, expires_at)
                VALUES ('_models', 'active_versions', ?,
                        datetime('now', '+10 years'))
                """,
                (json.dumps(self._active),),
            )
        except Exception:
            pass

    def get_for_user(self, model_id: str, user_id: str) -> Optional[ModelConfig]:
        """A/B test routing — same user always gets the same variant."""
        configs = self._configs.get(model_id, [])
        active_versions = [c for c in configs if c.is_active]
        if not active_versions:
            return self.get_active(model_id)

        bucket = int(hashlib.md5(
            f"{user_id}:{model_id}".encode()
        ).hexdigest()[:8], 16) % 100

        ab_versions = [c for c in active_versions if "ab_test" in c.tags]
        if ab_versions:
            return ab_versions[bucket % len(ab_versions)]

        return self.get_active(model_id)

    def record_metric(self, model_id: str, version: str,
                       metric: str, value: float) -> None:
        """Update runtime metric for a config."""
        for cfg in self._configs.get(model_id, []):
            if cfg.version == version:
                cfg.metrics[metric] = value
                self._persist_metrics(cfg)
                return

    def _persist_metrics(self, cfg: ModelConfig) -> None:
        try:
            execute_update(
                """
                INSERT INTO offline_cache
                (user_id, cache_type, data_json, expires_at)
                VALUES ('_models', ?, ?, datetime('now', '+1 year'))
                """,
                (
                    f"metrics_{cfg.model_id}_{cfg.version}",
                    json.dumps({
                        "model_id": cfg.model_id,
                        "version": cfg.version,
                        "metrics": cfg.metrics,
                        "ts": time.time(),
                    }),
                ),
            )
        except Exception:
            pass

    def all_models(self) -> Dict[str, List[ModelConfig]]:
        return dict(self._configs)


_REGISTRY: Optional[ModelRegistry] = None


def get_registry() -> ModelRegistry:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = ModelRegistry()
    return _REGISTRY


# ============================================================
# Convenience helpers
# ============================================================
def active(model_id: str) -> Optional[ModelConfig]:
    return get_registry().get_active(model_id)


def list_versions(model_id: str) -> List[ModelConfig]:
    return get_registry().list_versions(model_id)


def set_active(model_id: str, version: str) -> bool:
    return get_registry().set_active(model_id, version)


def for_user(model_id: str, user_id: str) -> Optional[ModelConfig]:
    return get_registry().get_for_user(model_id, user_id)

"""
ONNX runtime acceleration for the neural scorer + lightweight pose models.

Falls back to PyTorch if ONNX runtime missing.
Provides 2-3x speedup on CPU and supports CoreML / DirectML / CUDA providers.

Convert a PyTorch model:
    onnx_accel.convert_torch_to_onnx(model, dummy, "out.onnx")

Run inference:
    sess = onnx_accel.OnnxSession("model.onnx")
    out = sess.run({"input": np.ndarray(...)})
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import numpy as np


@dataclass
class OnnxCapabilities:
    available: bool
    providers: List[str]
    has_cuda: bool
    has_coreml: bool
    has_directml: bool


def detect_capabilities() -> OnnxCapabilities:
    """Detect ONNX runtime + available execution providers."""
    try:
        import onnxruntime as ort
    except ImportError:
        return OnnxCapabilities(False, [], False, False, False)

    providers = ort.get_available_providers()
    return OnnxCapabilities(
        available=True,
        providers=providers,
        has_cuda="CUDAExecutionProvider" in providers,
        has_coreml="CoreMLExecutionProvider" in providers,
        has_directml="DmlExecutionProvider" in providers,
    )


def best_providers() -> List[str]:
    """Return ordered list of best providers for current platform."""
    cap = detect_capabilities()
    if not cap.available:
        return []

    preferred = []
    if cap.has_cuda:
        preferred.append("CUDAExecutionProvider")
    if cap.has_coreml:
        preferred.append("CoreMLExecutionProvider")
    if cap.has_directml:
        preferred.append("DmlExecutionProvider")
    preferred.append("CPUExecutionProvider")
    return preferred


class OnnxSession:
    """Thin wrapper over onnxruntime.InferenceSession."""

    def __init__(self, model_path: str,
                 providers: Optional[List[str]] = None):
        try:
            import onnxruntime as ort
        except ImportError as e:
            raise RuntimeError("onnxruntime not installed") from e

        if not Path(model_path).exists():
            raise FileNotFoundError(model_path)

        sess_opts = ort.SessionOptions()
        sess_opts.graph_optimization_level = (
            ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        )
        sess_opts.enable_cpu_mem_arena = True
        sess_opts.intra_op_num_threads = 0  # use all

        provs = providers or best_providers()
        self.session = ort.InferenceSession(
            model_path, sess_options=sess_opts, providers=provs
        )
        self.input_names = [i.name for i in self.session.get_inputs()]
        self.output_names = [o.name for o in self.session.get_outputs()]
        self.input_shapes = {
            i.name: i.shape for i in self.session.get_inputs()
        }

    def run(self, inputs: Dict[str, np.ndarray]) -> List[np.ndarray]:
        """Run inference. inputs: {input_name: ndarray}."""
        return self.session.run(self.output_names, inputs)

    def run_single(self, x: np.ndarray) -> np.ndarray:
        """Convenience for single-input single-output models."""
        out = self.run({self.input_names[0]: x})
        return out[0]


def convert_torch_to_onnx(model, dummy_input,
                            output_path: str,
                            input_names: Optional[List[str]] = None,
                            output_names: Optional[List[str]] = None,
                            dynamic_axes: Optional[Dict] = None,
                            opset_version: int = 17) -> bool:
    """Export PyTorch model to ONNX format."""
    try:
        import torch
    except ImportError:
        return False

    model.eval()
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    try:
        torch.onnx.export(
            model,
            dummy_input,
            output_path,
            input_names=input_names or ["input"],
            output_names=output_names or ["output"],
            dynamic_axes=dynamic_axes,
            opset_version=opset_version,
            do_constant_folding=True,
        )
        return True
    except Exception:
        return False


def benchmark(session: OnnxSession,
              dummy_input: np.ndarray,
              warmup: int = 5,
              runs: int = 50) -> Dict[str, float]:
    """Benchmark inference latency."""
    import time

    for _ in range(warmup):
        session.run_single(dummy_input)

    durations = []
    for _ in range(runs):
        t0 = time.perf_counter()
        session.run_single(dummy_input)
        durations.append((time.perf_counter() - t0) * 1000)

    arr = np.array(durations)
    return {
        "mean_ms": float(arr.mean()),
        "median_ms": float(np.median(arr)),
        "p95_ms": float(np.percentile(arr, 95)),
        "p99_ms": float(np.percentile(arr, 99)),
        "min_ms": float(arr.min()),
        "max_ms": float(arr.max()),
        "throughput_qps": float(1000.0 / arr.mean()) if arr.mean() > 0 else 0,
    }


def quantize_int8(input_path: str, output_path: str) -> bool:
    """Quantize ONNX model to INT8 for ~3-4x speedup on CPU."""
    try:
        from onnxruntime.quantization import quantize_dynamic, QuantType
    except ImportError:
        return False

    try:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        quantize_dynamic(
            input_path,
            output_path,
            weight_type=QuantType.QInt8,
        )
        return True
    except Exception:
        return False


# ============================================================
# Drop-in accelerator for the existing neural_scorer
# ============================================================
class AcceleratedNeuralScorer:
    """ONNX-accelerated wrapper for LSTM/STGCN quality scorers.

    Looks for `weights/lstm_quality.onnx` and `weights/stgcn_quality.onnx`.
    If absent, falls back to the original PyTorch implementation.
    """

    def __init__(self, weights_dir: str = "weights"):
        self.weights_dir = Path(weights_dir)
        self.lstm_session: Optional[OnnxSession] = None
        self.stgcn_session: Optional[OnnxSession] = None
        self._fallback = None

        self._load_or_fallback()

    def _load_or_fallback(self) -> None:
        if not detect_capabilities().available:
            self._init_fallback()
            return

        lstm_path = self.weights_dir / "lstm_quality.onnx"
        stgcn_path = self.weights_dir / "stgcn_quality.onnx"

        try:
            if lstm_path.exists():
                self.lstm_session = OnnxSession(str(lstm_path))
        except Exception:
            self.lstm_session = None

        try:
            if stgcn_path.exists():
                self.stgcn_session = OnnxSession(str(stgcn_path))
        except Exception:
            self.stgcn_session = None

        if not (self.lstm_session or self.stgcn_session):
            self._init_fallback()

    def _init_fallback(self) -> None:
        try:
            import neural_scorer
            self._fallback = neural_scorer
        except ImportError:
            self._fallback = None

    def score(self, seq: np.ndarray) -> Dict[str, float]:
        """Score a (T, J, 3) sequence. Returns {LSTM: float, STGCN: float}."""
        results: Dict[str, float] = {}

        if self.lstm_session is not None:
            try:
                x = seq.astype(np.float32).reshape(1, *seq.shape)
                out = self.lstm_session.run_single(x)
                results["LSTM"] = float(out.flatten()[0])
            except Exception:
                pass

        if self.stgcn_session is not None:
            try:
                x = seq.astype(np.float32).reshape(1, *seq.shape)
                out = self.stgcn_session.run_single(x)
                results["STGCN"] = float(out.flatten()[0])
            except Exception:
                pass

        if not results and self._fallback is not None:
            try:
                results = self._fallback.score(seq)
            except Exception:
                pass

        return results

    def is_accelerated(self) -> bool:
        """True if at least one ONNX model is loaded."""
        return self.lstm_session is not None or self.stgcn_session is not None

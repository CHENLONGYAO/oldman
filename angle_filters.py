"""
Advanced signal filters for joint angle smoothing.

Implementations:
- One-Euro Filter: low-lag adaptive low-pass (ideal for real-time)
- Kalman Filter: optimal under linear-Gaussian assumption
- Savitzky-Golay: polynomial smoothing for offline batch
- Adaptive EMA: time-step aware exponential moving average
- Compound filter: chains multiple filters for best results
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Sequence
import math
import numpy as np


# ============================================================
# One-Euro Filter (Casiez, Roussel, Vogel 2012)
# Adaptive low-pass: low cutoff at slow motion (smooth),
# high cutoff at fast motion (responsive). Ideal for real-time
# pose tracking — used by MediaPipe internally and in many AR apps.
# ============================================================
@dataclass
class OneEuroFilter:
    """
    One-Euro filter for a scalar signal.

    Parameters:
        min_cutoff: minimum cutoff frequency (Hz). Lower = smoother.
        beta: speed coefficient. Higher = more responsive to fast motion.
        d_cutoff: derivative cutoff frequency.

    Defaults work well for 30-60 Hz input.
    """
    min_cutoff: float = 1.0
    beta: float = 0.05
    d_cutoff: float = 1.0

    _x_prev: Optional[float] = None
    _dx_prev: float = 0.0
    _t_prev: Optional[float] = None

    def filter(self, x: float, t: float) -> float:
        """Apply filter. t is current timestamp in seconds."""
        if self._t_prev is None:
            self._t_prev = t
            self._x_prev = x
            return x

        dt = max(1e-6, t - self._t_prev)

        dx = (x - self._x_prev) / dt
        a_d = self._alpha(dt, self.d_cutoff)
        dx_hat = a_d * dx + (1 - a_d) * self._dx_prev

        cutoff = self.min_cutoff + self.beta * abs(dx_hat)
        a = self._alpha(dt, cutoff)
        x_hat = a * x + (1 - a) * self._x_prev

        self._x_prev = x_hat
        self._dx_prev = dx_hat
        self._t_prev = t
        return x_hat

    @staticmethod
    def _alpha(dt: float, cutoff: float) -> float:
        tau = 1.0 / (2 * math.pi * cutoff)
        return 1.0 / (1.0 + tau / dt)

    def reset(self) -> None:
        self._x_prev = None
        self._dx_prev = 0.0
        self._t_prev = None


class OneEuroVectorFilter:
    """One-Euro filter applied independently to each component of a vector."""

    def __init__(self, dim: int, min_cutoff: float = 1.0,
                 beta: float = 0.05, d_cutoff: float = 1.0):
        self._filters = [
            OneEuroFilter(min_cutoff=min_cutoff, beta=beta, d_cutoff=d_cutoff)
            for _ in range(dim)
        ]

    def filter(self, x: Sequence[float], t: float) -> np.ndarray:
        return np.array([f.filter(float(x[i]), t)
                        for i, f in enumerate(self._filters)])

    def reset(self) -> None:
        for f in self._filters:
            f.reset()


# ============================================================
# Kalman Filter (constant-velocity model)
# Optimal smoother under linear-Gaussian assumptions. Slightly heavier
# than One-Euro but tracks acceleration better for ballistic motion.
# ============================================================
class KalmanScalar:
    """1D Kalman filter with constant-velocity model.

    State: [position, velocity]
    """

    def __init__(self, q: float = 1e-3, r: float = 1e-2):
        self.q = q  # process noise covariance
        self.r = r  # measurement noise covariance

        self.x = np.zeros(2)  # [position, velocity]
        self.P = np.eye(2) * 1.0
        self._initialized = False

    def filter(self, z: float, dt: float = 1.0 / 30.0) -> float:
        if not self._initialized:
            self.x[0] = z
            self._initialized = True
            return z

        F = np.array([[1, dt], [0, 1]], dtype=np.float64)
        Q = np.array([[dt**4 / 4, dt**3 / 2],
                      [dt**3 / 2, dt**2]], dtype=np.float64) * self.q
        H = np.array([[1, 0]], dtype=np.float64)

        x_pred = F @ self.x
        P_pred = F @ self.P @ F.T + Q

        y = z - H @ x_pred
        S = H @ P_pred @ H.T + self.r
        K = P_pred @ H.T / S

        self.x = x_pred + (K.flatten() * y[0])
        self.P = (np.eye(2) - np.outer(K.flatten(), H.flatten())) @ P_pred

        return float(self.x[0])

    def reset(self) -> None:
        self.x = np.zeros(2)
        self.P = np.eye(2) * 1.0
        self._initialized = False


# ============================================================
# Savitzky-Golay smoothing (offline / batch)
# Best for post-recording analysis: preserves peak shape better
# than EMA or simple moving average.
# ============================================================
def savitzky_golay(y: np.ndarray, window: int = 11,
                   poly: int = 3) -> np.ndarray:
    """Apply Savitzky-Golay polynomial smoothing to 1D array."""
    try:
        from scipy.signal import savgol_filter
    except ImportError:
        return _savgol_fallback(y, window, poly)

    if window > len(y):
        window = max(3, len(y) | 1)
    if window % 2 == 0:
        window += 1
    if poly >= window:
        poly = max(1, window - 2)

    return savgol_filter(y, window, poly)


def _savgol_fallback(y: np.ndarray, window: int, poly: int) -> np.ndarray:
    """Pure-numpy Savitzky-Golay fallback if scipy not present."""
    if window % 2 == 0:
        window += 1
    half = window // 2

    if len(y) < window:
        return y.copy()

    A = np.array([[i**p for p in range(poly + 1)]
                  for i in range(-half, half + 1)], dtype=np.float64)
    coefs = np.linalg.pinv(A.T @ A) @ A.T
    kernel = coefs[0]

    padded = np.pad(y, half, mode="edge")
    out = np.convolve(padded, kernel[::-1], mode="valid")
    return out


# ============================================================
# Adaptive EMA (time-aware)
# ============================================================
class AdaptiveEMA:
    """EMA that respects irregular timestamps (frame drops)."""

    def __init__(self, tau: float = 0.1):
        self.tau = tau  # time constant in seconds
        self._y_prev: Optional[float] = None
        self._t_prev: Optional[float] = None

    def filter(self, x: float, t: float) -> float:
        if self._y_prev is None:
            self._y_prev = x
            self._t_prev = t
            return x

        dt = max(1e-6, t - self._t_prev)
        alpha = 1.0 - math.exp(-dt / self.tau)
        y = alpha * x + (1 - alpha) * self._y_prev
        self._y_prev = y
        self._t_prev = t
        return y

    def reset(self) -> None:
        self._y_prev = None
        self._t_prev = None


# ============================================================
# Compound filter: One-Euro followed by Kalman
# Production-quality combo for joint angles
# ============================================================
class CompoundAngleFilter:
    """One-Euro (anti-jitter) → Kalman (smooth) for high-quality angles."""

    def __init__(self,
                 min_cutoff: float = 1.5,
                 beta: float = 0.1,
                 q: float = 5e-4,
                 r: float = 1e-2):
        self.one_euro = OneEuroFilter(min_cutoff=min_cutoff, beta=beta)
        self.kalman = KalmanScalar(q=q, r=r)

    def filter(self, x: float, t: float, dt: float = 1.0 / 30.0) -> float:
        first = self.one_euro.filter(x, t)
        return self.kalman.filter(first, dt)

    def reset(self) -> None:
        self.one_euro.reset()
        self.kalman.reset()


# ============================================================
# Multi-joint filter manager
# ============================================================
class JointAngleFilters:
    """Holds a CompoundAngleFilter per joint name; thread-safe per-joint."""

    def __init__(self, joint_names: Sequence[str],
                 filter_factory=None):
        if filter_factory is None:
            filter_factory = lambda: CompoundAngleFilter()
        self._filters = {name: filter_factory() for name in joint_names}

    def filter(self, joint: str, value: float, t: float,
               dt: float = 1.0 / 30.0) -> float:
        f = self._filters.get(joint)
        if f is None:
            return value
        return f.filter(value, t, dt)

    def reset_all(self) -> None:
        for f in self._filters.values():
            f.reset()

    def filter_dict(self, angles: dict, t: float,
                    dt: float = 1.0 / 30.0) -> dict:
        return {k: self.filter(k, float(v), t, dt) for k, v in angles.items()}

"""
Performance telemetry: track app health metrics.

Captures:
- Page render times
- DB query latencies
- ML model inference times
- Cache hit rates
- Error counts by type
- User flow completion rates

Stored in-memory (rolling window) and optionally exported to file.
Read-only dashboard for admins/therapists.
"""
from __future__ import annotations
import json
import time
from collections import defaultdict, deque
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, List, Optional


@dataclass
class MetricPoint:
    name: str
    value: float
    tags: Dict[str, str] = field(default_factory=dict)
    ts: float = field(default_factory=time.time)


class Telemetry:
    """In-memory telemetry collector with rolling window."""

    def __init__(self, max_points: int = 5000):
        self._points: Deque[MetricPoint] = deque(maxlen=max_points)
        self._counters: Dict[str, int] = defaultdict(int)
        self._gauges: Dict[str, float] = {}
        self._timings: Dict[str, Deque[float]] = defaultdict(
            lambda: deque(maxlen=200)
        )

    def record(self, name: str, value: float,
               tags: Optional[Dict[str, str]] = None) -> None:
        self._points.append(MetricPoint(name, value, tags or {}))

    def counter(self, name: str, delta: int = 1) -> None:
        self._counters[name] += delta

    def gauge(self, name: str, value: float) -> None:
        self._gauges[name] = value

    def timing(self, name: str, duration_ms: float) -> None:
        self._timings[name].append(duration_ms)
        self.record(f"timing.{name}", duration_ms)

    @contextmanager
    def measure(self, name: str, tags: Optional[Dict[str, str]] = None):
        """Context manager that records elapsed ms."""
        t0 = time.perf_counter()
        try:
            yield
        finally:
            ms = (time.perf_counter() - t0) * 1000
            self.timing(name, ms)
            if tags:
                self.record(f"timing.{name}", ms, tags)

    def get_stats(self) -> Dict:
        """Snapshot of current metrics."""
        timings_summary = {}
        for name, durations in self._timings.items():
            if durations:
                arr = list(durations)
                arr_sorted = sorted(arr)
                n = len(arr_sorted)
                timings_summary[name] = {
                    "count": n,
                    "mean": sum(arr) / n,
                    "median": arr_sorted[n // 2],
                    "p95": arr_sorted[min(n - 1, int(n * 0.95))],
                    "min": arr_sorted[0],
                    "max": arr_sorted[-1],
                }

        return {
            "counters": dict(self._counters),
            "gauges": dict(self._gauges),
            "timings": timings_summary,
            "total_points": len(self._points),
        }

    def get_recent_errors(self, limit: int = 20) -> List[MetricPoint]:
        return [p for p in list(self._points)[-200:]
                if p.name.startswith("error.")][-limit:]

    def export_json(self) -> str:
        return json.dumps(self.get_stats(), indent=2, default=str)


_TELEMETRY = Telemetry()


def record(name: str, value: float, **tags) -> None:
    _TELEMETRY.record(name, value, tags)


def counter(name: str, delta: int = 1) -> None:
    _TELEMETRY.counter(name, delta)


def gauge(name: str, value: float) -> None:
    _TELEMETRY.gauge(name, value)


def timing(name: str, duration_ms: float) -> None:
    _TELEMETRY.timing(name, duration_ms)


def measure(name: str, **tags):
    return _TELEMETRY.measure(name, tags)


def record_error(error_type: str, message: str = "") -> None:
    _TELEMETRY.record(f"error.{error_type}", 1.0, {"msg": message[:200]})
    counter(f"error.{error_type}")


def get_stats() -> Dict:
    return _TELEMETRY.get_stats()


def get_recent_errors(limit: int = 20) -> List[MetricPoint]:
    return _TELEMETRY.get_recent_errors(limit)


def render_admin_panel(lang: str = "zh") -> None:
    """Render telemetry dashboard for admins."""
    import streamlit as st

    stats = get_stats()

    st.subheader("📊 " + ("效能指標" if lang == "zh" else "Performance"))
    cols = st.columns(4)

    with cols[0]:
        st.metric(
            "總資料點" if lang == "zh" else "Data Points",
            stats["total_points"],
        )
    with cols[1]:
        st.metric(
            "計數器" if lang == "zh" else "Counters",
            len(stats["counters"]),
        )
    with cols[2]:
        st.metric(
            "計時項" if lang == "zh" else "Timings",
            len(stats["timings"]),
        )
    with cols[3]:
        try:
            from cache_layer import get_cache_stats
            cache = get_cache_stats()
            st.metric(
                "快取命中率" if lang == "zh" else "Cache Hit Rate",
                f"{cache['hit_rate'] * 100:.1f}%",
            )
        except ImportError:
            st.metric("Cache", "—")

    if stats["timings"]:
        st.subheader("⏱️ " + ("回應時間" if lang == "zh"
                              else "Response Times (ms)"))
        import pandas as pd
        df = pd.DataFrame([
            {
                "name": n,
                "count": d["count"],
                "mean": round(d["mean"], 1),
                "median": round(d["median"], 1),
                "p95": round(d["p95"], 1),
                "max": round(d["max"], 1),
            }
            for n, d in stats["timings"].items()
        ])
        st.dataframe(df, use_container_width=True, hide_index=True)

    if stats["counters"]:
        with st.expander("🔢 " + ("計數器" if lang == "zh" else "Counters")):
            import pandas as pd
            df = pd.DataFrame([
                {"name": k, "value": v}
                for k, v in stats["counters"].items()
            ])
            st.dataframe(df, use_container_width=True, hide_index=True)

    errors = get_recent_errors(20)
    if errors:
        st.subheader("⚠️ " + ("最近錯誤" if lang == "zh"
                              else "Recent Errors"))
        for err in errors:
            st.markdown(
                f"- `{err.name}` — {err.tags.get('msg', '')} "
                f"({time.strftime('%H:%M:%S', time.localtime(err.ts))})"
            )

    if st.button("📋 " + ("匯出 JSON" if lang == "zh"
                          else "Export JSON")):
        st.code(_TELEMETRY.export_json(), language="json")

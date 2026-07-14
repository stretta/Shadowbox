from __future__ import annotations

import os
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from time import monotonic
from typing import Callable


@dataclass
class PerformanceProbe:
    """Low-overhead, opt-in aggregation for the UI hot path."""

    enabled: bool = field(default_factory=lambda: os.environ.get("SHADOWBOX_PERF_LOG", "").lower() in {"1", "true", "yes", "on"})
    clock: Callable[[], float] = monotonic
    summary_interval: float = 10.0
    logger: Callable[[str], None] = print

    def __post_init__(self) -> None:
        self._last_summary = self.clock()
        self._values: dict[str, list[float]] = defaultdict(list)
        self._counts: Counter[str] = Counter()

    def observe(self, name: str, seconds: float) -> None:
        if self.enabled:
            self._values[str(name)].append(max(0.0, float(seconds)))

    def increment(self, name: str, count: int = 1) -> None:
        if self.enabled:
            self._counts[str(name)] += int(count)

    def snapshot(self, *, reset: bool = False) -> dict:
        values = {
            name: {
                "count": len(items),
                "avg_ms": (sum(items) / len(items) * 1000.0) if items else 0.0,
                "max_ms": max(items, default=0.0) * 1000.0,
            }
            for name, items in sorted(self._values.items())
        }
        result = {"timings": values, "counts": dict(sorted(self._counts.items()))}
        if reset:
            self._values.clear()
            self._counts.clear()
            self._last_summary = self.clock()
        return result

    def maybe_log(self) -> dict | None:
        if not self.enabled or self.clock() - self._last_summary < self.summary_interval:
            return None
        summary = self.snapshot(reset=True)
        timing_text = " ".join(
            f"{name}={value['avg_ms']:.1f}/{value['max_ms']:.1f}ms({value['count']})"
            for name, value in summary["timings"].items()
        )
        count_text = " ".join(f"{name}={value}" for name, value in summary["counts"].items())
        self.logger("Shadowbox perf: " + " ".join(part for part in (timing_text, count_text) if part))
        return summary


class Timer:
    def __init__(self, probe: PerformanceProbe, name: str):
        self.probe = probe
        self.name = name
        self.started = probe.clock()

    def stop(self) -> float:
        elapsed = self.probe.clock() - self.started
        self.probe.observe(self.name, elapsed)
        return elapsed

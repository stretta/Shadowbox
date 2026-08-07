from __future__ import annotations

from dataclasses import dataclass
from queue import Empty, Queue, SimpleQueue
from threading import Event, Lock, Thread
from time import monotonic, sleep
from typing import Any, Callable


DISCOVERY_TYPES = {"runner", "network_status", "wifi_list", "wifi_rescan"}


@dataclass(frozen=True)
class DiscoveryResult:
    kind: str
    reason: str
    generation: int
    value: Any = None
    error: str = ""
    duration: float = 0.0


class DiscoveryCoordinator:
    """Serial background coordinator with typed coalescing and generations."""

    def __init__(self, rnbo, *, clock: Callable[[], float] = monotonic, metrics=None):
        self.rnbo = rnbo
        self.clock = clock
        self.metrics = metrics
        self._jobs: Queue[tuple[str, str, int, float] | None] = Queue()
        self._results: SimpleQueue[DiscoveryResult] = SimpleQueue()
        self._pending: set[str] = set()
        self._generations: dict[str, int] = {}
        self._latest_request: dict[str, tuple[str, float]] = {}
        self._lock = Lock()
        self._stop = Event()
        self._thread = Thread(target=self._run, name="shadowbox-discovery", daemon=True)

    def start(self) -> None:
        if not self._thread.is_alive():
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._jobs.put(None)
        if self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def request(self, kind: str, reason: str = "", *, delay: float = 0.0) -> int:
        if kind not in DISCOVERY_TYPES:
            raise ValueError(f"Unknown discovery type: {kind}")
        with self._lock:
            generation = self._generations.get(kind, 0) + 1
            self._generations[kind] = generation
            self._latest_request[kind] = (str(reason), max(0.0, float(delay)))
            if self.metrics:
                self.metrics.increment("discovery_requested")
            if kind in self._pending:
                if self.metrics:
                    self.metrics.increment("discovery_coalesced")
                return generation
            self._pending.add(kind)
            self._jobs.put((kind, str(reason), generation, max(0.0, float(delay))))
            return generation

    def current_generation(self, kind: str) -> int:
        with self._lock:
            return self._generations.get(kind, 0)

    def drain(self) -> list[DiscoveryResult]:
        results: list[DiscoveryResult] = []
        while True:
            try:
                results.append(self._results.get_nowait())
            except Empty:
                return results

    def is_stale(self, result: DiscoveryResult) -> bool:
        return result.generation < self.current_generation(result.kind)

    def _discover(self, kind: str):
        if kind == "runner":
            strict = getattr(self.rnbo, "discover_runner_strict", None)
            return strict() if callable(strict) else self.rnbo.discover_runner()
        if kind == "network_status":
            return self.rnbo.discover_network_status()
        return self.rnbo.discover_wifi_networks(active_scan=kind == "wifi_rescan")

    def _run(self) -> None:
        while not self._stop.is_set():
            job = self._jobs.get()
            if job is None:
                return
            kind, reason, queued_generation, delay = job
            with self._lock:
                generation = self._generations.get(kind, queued_generation)
                reason, delay = self._latest_request.get(kind, (reason, delay))
            started = self.clock()
            try:
                if delay:
                    sleep(delay)
                value = self._discover(kind)
                result = DiscoveryResult(kind, reason, generation, value=value, duration=self.clock() - started)
                if self.metrics:
                    self.metrics.increment("discovery_completed")
            except Exception as exc:
                result = DiscoveryResult(kind, reason, generation, error=str(exc), duration=self.clock() - started)
                if self.metrics:
                    self.metrics.increment("discovery_failed")
            self._results.put(result)
            with self._lock:
                self._pending.discard(kind)
                latest = self._generations.get(kind, generation)
                if latest > generation and not self._stop.is_set():
                    latest_reason, latest_delay = self._latest_request.get(kind, (reason, 0.0))
                    self._pending.add(kind)
                    self._jobs.put((kind, latest_reason, latest, latest_delay))


@dataclass(frozen=True)
class NetworkOperationResult:
    kind: str
    ok: bool
    error: str
    network: dict
    target: str = ""


class NetworkOperationCoordinator:
    """Runs privileged network mutations without blocking input/rendering."""

    def __init__(self, rnbo, direct_helper, wifi_helper):
        self.rnbo = rnbo
        self.direct_helper = direct_helper
        self.wifi_helper = wifi_helper
        self._jobs: Queue[tuple[str, tuple] | None] = Queue()
        self._results: SimpleQueue[NetworkOperationResult] = SimpleQueue()
        self._thread = Thread(target=self._run, name="shadowbox-network", daemon=True)

    def start(self) -> None:
        if not self._thread.is_alive():
            self._thread.start()

    def stop(self) -> None:
        self._jobs.put(None)
        if self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def request(self, kind: str, *args) -> None:
        self._jobs.put((kind, tuple(args)))

    def drain(self) -> list[NetworkOperationResult]:
        results: list[NetworkOperationResult] = []
        while True:
            try:
                results.append(self._results.get_nowait())
            except Empty:
                return results

    def _run(self) -> None:
        while True:
            job = self._jobs.get()
            if job is None:
                return
            kind, args = job
            try:
                if kind in {"enable_direct_ethernet", "disable_direct_ethernet"}:
                    ok, error = self.direct_helper("enable" if kind.startswith("enable") else "disable")
                elif kind == "connect_wifi":
                    ok, error = self.wifi_helper("connect", *args)
                elif kind == "connect_wifi_new":
                    ok, error = self.wifi_helper("connect-new", *args)
                else:
                    raise ValueError(f"Unknown network operation: {kind}")
                network = self.rnbo.discover_network_status()
            except Exception as exc:
                ok, error, network = False, str(exc), {}
            target = str(args[0] or "") if args else ""
            self._results.put(NetworkOperationResult(kind, ok, error, network, target))

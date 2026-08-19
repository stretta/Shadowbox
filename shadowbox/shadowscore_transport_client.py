from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from queue import Empty, Queue, SimpleQueue
from threading import Event, Lock, Thread
from time import sleep
from typing import Any, Callable, Iterator

from shadowbox.shadowscore_transport import shadowscore_transport_urls


TRANSPORT_OBJECT_PATH = "/api/v1/objects/transport"
TRANSPORT_EVENTS_PATH = f"{TRANSPORT_OBJECT_PATH}/events"


@dataclass(frozen=True)
class ShadowScoreTransportResult:
    kind: str
    snapshot: dict[str, Any] | None = None
    operation: str = ""
    base_url: str = ""
    error: str = ""


def parse_sse_events(lines: Iterator[bytes | str]) -> Iterator[tuple[str, Any]]:
    event_name = "message"
    data_lines: list[str] = []
    for raw_line in lines:
        line = raw_line.decode("utf-8", errors="replace") if isinstance(raw_line, bytes) else str(raw_line)
        line = line.rstrip("\r\n")
        if not line:
            if data_lines:
                payload = json.loads("\n".join(data_lines))
                yield event_name, payload
            event_name = "message"
            data_lines = []
            continue
        if line.startswith(":"):
            continue
        field, separator, value = line.partition(":")
        if separator and value.startswith(" "):
            value = value[1:]
        if field == "event":
            event_name = value or "message"
        elif field == "data":
            data_lines.append(value)
    if data_lines:
        yield event_name, json.loads("\n".join(data_lines))


class ShadowScoreTransportCoordinator:
    """Observe and command the canonical ShadowScore transport off the UI thread."""

    def __init__(
        self,
        *,
        urls: list[str] | None = None,
        unit_id: str | None = None,
        opener: Callable = urllib.request.urlopen,
        reconnect_delay: float = 1.0,
        command_timeout: float = 30.0,
    ) -> None:
        self.urls = list(urls or shadowscore_transport_urls())
        self.unit_id = str(unit_id or socket.gethostname()).strip() or "shadowbox"
        self.opener = opener
        self.reconnect_delay = max(0.05, float(reconnect_delay))
        self.command_timeout = max(0.1, float(command_timeout))
        self._jobs: Queue[tuple[str, dict[str, Any]] | None] = Queue()
        self._results: SimpleQueue[ShadowScoreTransportResult] = SimpleQueue()
        self._stop = Event()
        self._lock = Lock()
        self._active_base_url = ""
        self._observer_response = None
        self._observer = Thread(target=self._observe, name="shadowbox-shadowscore-transport-observer", daemon=True)
        self._commands = Thread(target=self._run_commands, name="shadowbox-shadowscore-transport-commands", daemon=True)

    def start(self) -> None:
        if not self._observer.is_alive():
            self._observer.start()
        if not self._commands.is_alive():
            self._commands.start()

    def stop(self) -> None:
        self._stop.set()
        self._jobs.put(None)
        with self._lock:
            response = self._observer_response
        if response is not None:
            try:
                response.close()
            except Exception:
                pass
        for thread in (self._observer, self._commands):
            if thread.is_alive():
                thread.join(timeout=2.0)

    def request(self, operation: str, args: dict[str, Any] | None = None) -> None:
        self._jobs.put((str(operation), dict(args or {})))

    def drain(self) -> list[ShadowScoreTransportResult]:
        results: list[ShadowScoreTransportResult] = []
        while True:
            try:
                results.append(self._results.get_nowait())
            except Empty:
                return results

    def _ordered_urls(self) -> list[str]:
        with self._lock:
            active = self._active_base_url
        return ([active] if active else []) + [url for url in self.urls if url != active]

    def _command_urls(self) -> list[str]:
        with self._lock:
            active = self._active_base_url
        return [active] if active else list(self.urls)

    def _set_active(self, base_url: str) -> None:
        with self._lock:
            self._active_base_url = base_url

    def _observe(self) -> None:
        last_error = ""
        while not self._stop.is_set():
            connected = False
            for base_url in self._ordered_urls():
                if self._stop.is_set():
                    return
                request = urllib.request.Request(
                    f"{base_url.rstrip('/')}{TRANSPORT_EVENTS_PATH}",
                    headers={"Accept": "text/event-stream"},
                    method="GET",
                )
                try:
                    response = self.opener(request, timeout=5.0)
                    with self._lock:
                        self._observer_response = response
                    self._set_active(base_url)
                    connected = True
                    last_error = ""
                    self._results.put(ShadowScoreTransportResult("connection", base_url=base_url))
                    with response:
                        for event_name, payload in parse_sse_events(response):
                            if self._stop.is_set():
                                return
                            if event_name == "snapshot" and isinstance(payload, dict):
                                self._results.put(ShadowScoreTransportResult("snapshot", snapshot=payload, base_url=base_url))
                            elif event_name == "error":
                                message = str(payload.get("error", "transport observer error")) if isinstance(payload, dict) else str(payload)
                                self._results.put(ShadowScoreTransportResult("error", base_url=base_url, error=message))
                    if self._stop.is_set():
                        return
                    raise OSError("transport event stream closed")
                except Exception as exc:
                    message = str(exc) or exc.__class__.__name__
                    if message != last_error:
                        self._results.put(ShadowScoreTransportResult("disconnected", base_url=base_url, error=message))
                        last_error = message
                finally:
                    with self._lock:
                        self._observer_response = None
                if connected:
                    break
            if not self._stop.is_set():
                sleep(self.reconnect_delay)

    def _run_commands(self) -> None:
        while not self._stop.is_set():
            job = self._jobs.get()
            if job is None:
                return
            operation, args = job
            error = "ShadowScore transport is unavailable"
            request_id = str(uuid.uuid4())
            succeeded = False
            for base_url in self._command_urls():
                try:
                    body = {
                        "request_id": request_id,
                        "client_id": f"shadowbox-{self.unit_id}",
                        "operation": operation,
                        "args": args,
                    }
                    payload = json.dumps(body, separators=(",", ":")).encode("utf-8")
                    request = urllib.request.Request(
                        f"{base_url.rstrip('/')}{TRANSPORT_OBJECT_PATH}",
                        data=payload,
                        headers={"Content-Type": "application/json"},
                        method="POST",
                    )
                    with self.opener(request, timeout=self.command_timeout) as response:
                        document = json.loads(response.read().decode("utf-8"))
                    snapshot = document.get("object") if isinstance(document, dict) else None
                    if not isinstance(snapshot, dict):
                        raise ValueError("transport command returned no authoritative object")
                    self._set_active(base_url)
                    self._results.put(ShadowScoreTransportResult(
                        "command",
                        snapshot=snapshot,
                        operation=operation,
                        base_url=base_url,
                    ))
                    succeeded = True
                    break
                except Exception as exc:
                    error = transport_error_message(exc, operation=operation)
                    snapshot = self._fetch_snapshot(base_url)
                    if snapshot is not None:
                        self._results.put(ShadowScoreTransportResult("snapshot", snapshot=snapshot, base_url=base_url))
                    # Once an observer has selected a coordinator, never replay
                    # an ambiguously timed-out operation against another URL.
                    with self._lock:
                        if self._active_base_url:
                            break
            if not succeeded:
                # Clear pending UI state after the read-only reconciliation.
                self._results.put(ShadowScoreTransportResult("command_error", operation=operation, error=error))

    def _fetch_snapshot(self, base_url: str) -> dict[str, Any] | None:
        try:
            request = urllib.request.Request(
                f"{base_url.rstrip('/')}{TRANSPORT_OBJECT_PATH}",
                headers={"Accept": "application/json"},
                method="GET",
            )
            with self.opener(request, timeout=5.0) as response:
                document = json.loads(response.read().decode("utf-8"))
            snapshot = document.get("object") if isinstance(document, dict) else None
            return snapshot if isinstance(snapshot, dict) else None
        except Exception:
            return None


def transport_error_message(error: Exception, *, operation: str = "") -> str:
    message = str(error) or error.__class__.__name__
    if isinstance(error, urllib.error.HTTPError):
        try:
            document = json.loads(error.read().decode("utf-8"))
            if isinstance(document, dict) and document.get("error"):
                message = str(document["error"])
        except Exception:
            pass
    if "RNBO playback is not ready:" in message:
        failures = [item for item in message.split(":", 1)[1].split(",") if item.strip()]
        count = len(failures)
        return f"{operation.upper() or 'TRANSPORT'} FAILED · {count} CLIENT{'S' if count != 1 else ''} NOT READY"
    if "did not reach ACTIVE on every required client" in message:
        return f"{operation.upper() or 'TRANSPORT'} FAILED · CLIENTS NOT ACTIVE"
    return message

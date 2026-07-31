from __future__ import annotations

import re
import select
import subprocess
import threading
from dataclasses import dataclass
from queue import Empty, SimpleQueue
from time import monotonic
from typing import Any, Callable


ROLE_NONE = "none"
ROLE_CHROMATIC = "chromatic"
ROLE_SCALAR = "scalar"
ROLE_LABELS = {
    ROLE_NONE: "None",
    ROLE_CHROMATIC: "Chromatic Transpose",
    ROLE_SCALAR: "Scalar Transpose",
}
ROLE_PARAMETERS = {
    ROLE_CHROMATIC: "ChromaticTranspose",
    ROLE_SCALAR: "ScalarTranspose",
}

MIDDLE_C_NOTE = 60


@dataclass(frozen=True)
class MidiInputPort:
    client_name: str
    port_name: str
    address: str

    @property
    def identity(self) -> str:
        return midi_port_identity(self.client_name, self.port_name)

    @property
    def display_name(self) -> str:
        if self.port_name and self.port_name != self.client_name:
            return f"{self.client_name}: {self.port_name}"
        return self.client_name or self.port_name


@dataclass(frozen=True)
class MidiNoteEvent:
    note: int
    velocity: int
    channel: int
    device_identity: str
    device_name: str


@dataclass(frozen=True)
class TransposeTarget:
    instance_id: str
    instance_name: str
    path: str
    value: Any
    minimum: float | None
    maximum: float | None

    def accepts(self, value: int) -> bool:
        return not (
            (self.minimum is not None and value < self.minimum)
            or (self.maximum is not None and value > self.maximum)
        )


@dataclass(frozen=True)
class TransposeTargetStatus:
    compatible: int
    matching: int
    mixed: bool
    unsupported: int


def midi_port_identity(client_name: str, port_name: str) -> str:
    return f"{str(client_name).strip()}\0{str(port_name).strip()}"


def split_midi_port_identity(identity: str) -> tuple[str, str]:
    client_name, separator, port_name = str(identity or "").partition("\0")
    return client_name, port_name if separator else ""


_CLIENT_RE = re.compile(r"^client\s+(\d+):\s+'([^']*)'")
_PORT_RE = re.compile(r"^\s+(\d+)\s+'([^']*)'")


def parse_aconnect_inputs(output: str) -> list[MidiInputPort]:
    ports: list[MidiInputPort] = []
    client_number = ""
    client_name = ""
    for line in str(output or "").splitlines():
        client_match = _CLIENT_RE.match(line)
        if client_match:
            client_number, client_name = client_match.groups()
            continue
        port_match = _PORT_RE.match(line)
        if not port_match or not client_number:
            continue
        port_number, port_name = port_match.groups()
        if client_number == "0" or client_name.strip().lower() in {"system", "midi through"}:
            continue
        ports.append(
            MidiInputPort(
                client_name=client_name.strip(),
                port_name=port_name.strip(),
                address=f"{client_number}:{port_number}",
            )
        )
    return ports


_NOTE_ON_RE = re.compile(
    r"Note\s+on\s+(?P<channel>\d+)\s*,\s*note\s+(?P<note>\d+)\s*,\s*velocity\s+(?P<velocity>\d+)",
    re.IGNORECASE,
)


def parse_aseqdump_note_on(line: str, port: MidiInputPort) -> MidiNoteEvent | None:
    match = _NOTE_ON_RE.search(str(line or ""))
    if not match:
        return None
    velocity = int(match.group("velocity"))
    if velocity <= 0:
        return None
    return MidiNoteEvent(
        note=int(match.group("note")),
        velocity=velocity,
        channel=int(match.group("channel")),
        device_identity=port.identity,
        device_name=port.display_name,
    )


def note_to_offset(note: int) -> int:
    return int(note) - MIDDLE_C_NOTE


def normalize_role(value: Any) -> str:
    role = str(value or "").strip().lower()
    return role if role in ROLE_LABELS else ROLE_NONE


def transpose_targets(instances: list[dict], role: str) -> list[TransposeTarget]:
    parameter_name = ROLE_PARAMETERS.get(normalize_role(role))
    if not parameter_name:
        return []
    targets: list[TransposeTarget] = []
    for instance in instances:
        if not isinstance(instance, dict):
            continue
        instance_id = str(instance.get("id", "") or "")
        instance_name = str(instance.get("label", "") or instance.get("name", "") or instance_id)
        for param in instance.get("params", []):
            if not isinstance(param, dict) or str(param.get("name", "")) != parameter_name:
                continue
            path = str(param.get("path", "") or "")
            if not path:
                continue
            minimum = param.get("min")
            maximum = param.get("max")
            targets.append(
                TransposeTarget(
                    instance_id=instance_id,
                    instance_name=instance_name,
                    path=path,
                    value=param.get("value"),
                    minimum=float(minimum) if isinstance(minimum, (int, float)) and not isinstance(minimum, bool) else None,
                    maximum=float(maximum) if isinstance(maximum, (int, float)) and not isinstance(maximum, bool) else None,
                )
            )
    return targets


def target_status(instances: list[dict], role: str, canonical_value: int) -> TransposeTargetStatus:
    targets = transpose_targets(instances, role)
    matching = 0
    unsupported = 0
    observed: list[float] = []
    for target in targets:
        if not target.accepts(canonical_value):
            unsupported += 1
        value = target.value
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            observed.append(float(value))
            if abs(float(value) - float(canonical_value)) < 1e-9:
                matching += 1
    mixed = bool(observed and any(abs(value - observed[0]) >= 1e-9 for value in observed[1:]))
    if targets and matching != len(targets):
        mixed = True
    return TransposeTargetStatus(len(targets), matching, mixed, unsupported)


def common_target_range(instances: list[dict], role: str) -> tuple[int, int]:
    targets = transpose_targets(instances, role)
    minima = [target.minimum for target in targets if target.minimum is not None]
    maxima = [target.maximum for target in targets if target.maximum is not None]
    minimum = max(minima) if minima else -60
    maximum = min(maxima) if maxima else 67
    if minimum > maximum:
        return 0, 0
    return int(minimum), int(maximum)


def discover_alsa_inputs(
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> list[MidiInputPort]:
    try:
        result = runner(
            ["aconnect", "-i", "-l"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (FileNotFoundError, subprocess.SubprocessError, OSError):
        return []
    if result.returncode != 0:
        return []
    return parse_aconnect_inputs(result.stdout)


class AlsaMidiControllerMonitor:
    """Reconnect a named ALSA input port to an aseqdump note reader.

    This is a sidecar observer for a designated control device. It never
    receives or retransmits ordinary performance MIDI.
    """

    def __init__(self, discovery_seconds: float = 2.0) -> None:
        self.discovery_seconds = max(0.25, float(discovery_seconds))
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._events: SimpleQueue[MidiNoteEvent] = SimpleQueue()
        self._configured_identity = ""
        self._devices: list[MidiInputPort] = []
        self._connected_identity = ""
        self._process: subprocess.Popen[str] | None = None
        self._process_port: MidiInputPort | None = None

    def start(self) -> None:
        if not self._thread.is_alive():
            self._thread.start()

    def configure(self, identity: str) -> None:
        with self._lock:
            self._configured_identity = str(identity or "")

    @property
    def devices(self) -> list[MidiInputPort]:
        with self._lock:
            return list(self._devices)

    @property
    def connected_identity(self) -> str:
        with self._lock:
            return self._connected_identity

    def drain(self) -> list[MidiNoteEvent]:
        events: list[MidiNoteEvent] = []
        while True:
            try:
                events.append(self._events.get_nowait())
            except Empty:
                return events

    def _set_devices(self, devices: list[MidiInputPort]) -> None:
        with self._lock:
            self._devices = list(devices)

    def _desired_port(self) -> MidiInputPort | None:
        with self._lock:
            identity = self._configured_identity
            devices = list(self._devices)
        return next((port for port in devices if port.identity == identity), None)

    def _start_reader(self, port: MidiInputPort) -> None:
        try:
            process = subprocess.Popen(
                ["aseqdump", "-p", port.address],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                bufsize=1,
            )
        except (FileNotFoundError, OSError):
            return
        self._process = process
        self._process_port = port
        with self._lock:
            self._connected_identity = port.identity
        print(f"Transpose MIDI controller connected: {port.display_name}")

    def _stop_reader(self) -> None:
        process = self._process
        port = self._process_port
        self._process = None
        self._process_port = None
        with self._lock:
            self._connected_identity = ""
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                process.kill()
        if port is not None:
            print(f"Transpose MIDI controller disconnected: {port.display_name}")

    def _read_available_line(self) -> None:
        process = self._process
        port = self._process_port
        if process is None or port is None or process.stdout is None:
            return
        try:
            ready, _, _ = select.select([process.stdout], [], [], 0.05)
        except (OSError, ValueError):
            self._stop_reader()
            return
        if not ready:
            return
        line = process.stdout.readline()
        if not line:
            if process.poll() is not None:
                self._stop_reader()
            return
        event = parse_aseqdump_note_on(line, port)
        if event is not None:
            self._events.put(event)

    def _run(self) -> None:
        next_discovery_at = 0.0
        while not self._stop.is_set():
            now = monotonic()
            if now >= next_discovery_at:
                self._set_devices(discover_alsa_inputs())
                next_discovery_at = now + self.discovery_seconds

            desired = self._desired_port()
            current = self._process_port
            if current is not None and (desired is None or desired.address != current.address):
                self._stop_reader()
            if desired is not None and self._process is None:
                self._start_reader(desired)

            if self._process is not None:
                self._read_available_line()
                if self._process is not None and self._process.poll() is not None:
                    self._stop_reader()
            else:
                self._stop.wait(0.1)

        self._stop_reader()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=2.0)


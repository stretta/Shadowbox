from __future__ import annotations

import fcntl
import os
import re
import select
import struct
from dataclasses import dataclass
from pathlib import Path


EV_SYN = 0x00
EV_KEY = 0x01
EV_ABS = 0x03

BTN_TOUCH = 0x14A
ABS_X = 0x00
ABS_Y = 0x01
ABS_MT_POSITION_X = 0x35
ABS_MT_POSITION_Y = 0x36

# Raspberry Pi OS exposes 32-bit timeval fields in evdev here even on aarch64.
# Use a standard-size format so event parsing does not depend on Python's native
# long size on the host running the code.
_EVENT_STRUCT = struct.Struct("=llHHi")
_ABSINFO_STRUCT = struct.Struct("iiiiii")


@dataclass
class TouchSample:
    x: int
    y: int
    normalized_x: float
    normalized_y: float
    pressed: bool
    zone: str
    action: str


@dataclass(frozen=True)
class TouchAction:
    kind: str
    index: int | None = None
    button_id: str = ""
    value: float | None = None
    pressed: bool = False


@dataclass(frozen=True)
class TouchHitTarget:
    kind: str
    x: int
    y: int
    w: int
    h: int
    action_kind: str = ""
    index: int | None = None
    button_id: str = ""
    label: str = ""
    page: int | None = None
    page_count: int | None = None


class TouchLayout:
    def __init__(self, width: int, height: int) -> None:
        self.width = max(1, int(width))
        self.height = max(1, int(height))
        self.screen = ""
        self.targets: list[TouchHitTarget] = []

    def reset(self, screen: str = "") -> None:
        self.screen = str(screen)
        self.targets.clear()

    def add_target(
        self,
        kind: str,
        x: int,
        y: int,
        w: int,
        h: int,
        *,
        action_kind: str = "",
        index: int | None = None,
        button_id: str = "",
        label: str = "",
        page: int | None = None,
        page_count: int | None = None,
    ) -> TouchHitTarget:
        target = TouchHitTarget(
            kind=str(kind),
            x=max(0, int(x)),
            y=max(0, int(y)),
            w=max(0, int(w)),
            h=max(0, int(h)),
            action_kind=str(action_kind or ""),
            index=index,
            button_id=str(button_id or ""),
            label=str(label or ""),
            page=page,
            page_count=page_count,
        )
        if target.w > 0 and target.h > 0:
            self.targets.append(target)
        return target

    def _point_to_pixels(self, normalized_x: float, normalized_y: float) -> tuple[int, int]:
        x = int(round(max(0.0, min(1.0, normalized_x)) * max(0, self.width - 1)))
        y = int(round(max(0.0, min(1.0, normalized_y)) * max(0, self.height - 1)))
        return x, y

    def hit_test(self, normalized_x: float, normalized_y: float) -> TouchHitTarget | None:
        x, y = self._point_to_pixels(normalized_x, normalized_y)
        for target in reversed(self.targets):
            if x < target.x or y < target.y:
                continue
            if x >= target.x + target.w or y >= target.y + target.h:
                continue
            return target
        return None

    def action_for_point(self, normalized_x: float, normalized_y: float) -> TouchAction | None:
        target = self.hit_test(normalized_x, normalized_y)
        if target is None or not target.action_kind:
            return None
        if target.action_kind == "set_edit_value":
            x, _y = self._point_to_pixels(normalized_x, normalized_y)
            value = (x - target.x) / max(1, target.w - 1)
            return TouchAction(kind=target.action_kind, index=target.index, button_id=target.button_id, value=max(0.0, min(1.0, value)))
        return TouchAction(kind=target.action_kind, index=target.index, button_id=target.button_id)


def _eviocgabs(abs_code: int) -> int:
    # Linux _IOR('E', 0x40 + abs_code, struct input_absinfo), 64-bit size.
    return 0x80184540 + abs_code


def _read_abs_range(fd: int, code: int) -> tuple[int, int] | None:
    buffer = bytearray(_ABSINFO_STRUCT.size)
    try:
        fcntl.ioctl(fd, _eviocgabs(code), buffer, True)
    except OSError:
        return None
    _value, minimum, maximum, _fuzz, _flat, _resolution = _ABSINFO_STRUCT.unpack(buffer)
    if maximum <= minimum:
        return None
    return minimum, maximum


def find_touch_device() -> str | None:
    devices = Path("/proc/bus/input/devices")
    try:
        text = devices.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    for block in re.split(r"\n\s*\n", text):
        lowered = block.lower()
        if not any(token in lowered for token in ("touchscreen", "touch screen", "goodix", "ft5x", "edt-ft5x")):
            continue
        match = re.search(r"\bevent\d+\b", block)
        if match:
            return f"/dev/input/{match.group(0)}"
    return None


def zone_for_point(normalized_x: float, normalized_y: float) -> tuple[str, str]:
    left = normalized_x < 0.5
    top = normalized_y < 0.5
    if top and left:
        return "back", "long_press"
    if top and not left:
        return "enter", "short_press"
    if left:
        return "left", "step:-1"
    return "right", "step:+1"


def direct_action_for_point(
    normalized_x: float,
    normalized_y: float,
    *,
    row_count: int = 6,
    layout: TouchLayout | None = None,
) -> TouchAction:
    if layout is not None:
        action = layout.action_for_point(normalized_x, normalized_y)
        if action is not None:
            return action

    x = max(0.0, min(1.0, normalized_x))
    y = max(0.0, min(1.0, normalized_y))

    if y < 0.14 and x < 0.2:
        return TouchAction("tap_back")

    if x >= 0.9:
        return TouchAction("page_up" if y < 0.5 else "page_down")

    if y >= 0.88:
        if x < 1.0 / 3.0:
            return TouchAction("tap_button", button_id="back")
        if x < 2.0 / 3.0:
            return TouchAction("tap_button", button_id="secondary")
        return TouchAction("tap_button", button_id="primary")

    row_count = max(1, row_count)
    row_y = (y - 0.14) / (0.88 - 0.14)
    row_index = min(row_count - 1, max(0, int(row_y * row_count)))
    return TouchAction("tap_row", index=row_index)


class TouchZoneReader:
    def __init__(
        self,
        *,
        device: str | None = None,
        width: int = 800,
        height: int = 480,
    ) -> None:
        self.device = device or find_touch_device()
        if not self.device:
            raise RuntimeError("Could not find a Linux touchscreen input device")

        self.fd = os.open(self.device, os.O_RDONLY | os.O_NONBLOCK)
        self.width = width
        self.height = height
        self.min_x = 0
        self.max_x = max(1, width - 1)
        self.min_y = 0
        self.max_y = max(1, height - 1)
        self.x = 0
        self.y = 0
        self.pressed = False

        x_range = _read_abs_range(self.fd, ABS_MT_POSITION_X) or _read_abs_range(self.fd, ABS_X)
        y_range = _read_abs_range(self.fd, ABS_MT_POSITION_Y) or _read_abs_range(self.fd, ABS_Y)
        if x_range is not None:
            self.min_x, self.max_x = x_range
        if y_range is not None:
            self.min_y, self.max_y = y_range

    def close(self) -> None:
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None

    def _normalized(self) -> tuple[float, float]:
        nx = (self.x - self.min_x) / max(1, self.max_x - self.min_x)
        ny = (self.y - self.min_y) / max(1, self.max_y - self.min_y)
        return max(0.0, min(1.0, nx)), max(0.0, min(1.0, ny))

    def _sample(self) -> TouchSample:
        nx, ny = self._normalized()
        zone, action = zone_for_point(nx, ny)
        return TouchSample(
            x=self.x,
            y=self.y,
            normalized_x=nx,
            normalized_y=ny,
            pressed=self.pressed,
            zone=zone,
            action=action,
        )

    def current_sample(self) -> TouchSample:
        return self._sample()

    def read_samples(self) -> list[TouchSample]:
        if self.fd is None:
            return []

        samples: list[TouchSample] = []
        while True:
            readable, _writable, _errors = select.select([self.fd], [], [], 0)
            if not readable:
                return samples
            try:
                data = os.read(self.fd, _EVENT_STRUCT.size * 32)
            except BlockingIOError:
                return samples
            if not data:
                return samples

            for offset in range(0, len(data) - (_EVENT_STRUCT.size - 1), _EVENT_STRUCT.size):
                _sec, _usec, event_type, code, value = _EVENT_STRUCT.unpack_from(data, offset)
                if event_type == EV_ABS:
                    if code in {ABS_X, ABS_MT_POSITION_X}:
                        self.x = value
                    elif code in {ABS_Y, ABS_MT_POSITION_Y}:
                        self.y = value
                elif event_type == EV_KEY and code == BTN_TOUCH:
                    was_pressed = self.pressed
                    self.pressed = value != 0
                    if was_pressed and not self.pressed:
                        samples.append(self._sample())
                elif event_type == EV_SYN:
                    if self.pressed:
                        samples.append(self._sample())
                    continue
        return samples

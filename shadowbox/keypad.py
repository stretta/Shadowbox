#!/usr/bin/env python3

from __future__ import annotations

import fcntl
import glob
import os
import select
import struct
import time
from dataclasses import dataclass


EV_KEY = 0x01
EVIOCGRAB = 0x40044590
_EVENT_STRUCT = struct.Struct("@llHHi")

KEY_BACKSPACE = 14
KEY_ENTER = 28
KEY_KPASTERISK = 55
KEY_SPACE = 57
KEY_KP7 = 71
KEY_KP8 = 72
KEY_KP9 = 73
KEY_KPMINUS = 74
KEY_KP4 = 75
KEY_KP5 = 76
KEY_KP6 = 77
KEY_KPPLUS = 78
KEY_KP1 = 79
KEY_KP2 = 80
KEY_KP3 = 81
KEY_KP0 = 82
KEY_KPDOT = 83
KEY_KPENTER = 96
KEY_KPSLASH = 98
KEY_DELETE = 111


@dataclass(frozen=True)
class KeypadEvent:
    kind: str
    delta: int = 0
    button_id: str = ""


_DIGIT_CODES = {
    2: "1",
    3: "2",
    4: "3",
    5: "4",
    6: "5",
    7: "6",
    8: "7",
    9: "8",
    10: "9",
    11: "0",
    KEY_KP0: "0",
    KEY_KP1: "1",
    KEY_KP2: "2",
    KEY_KP3: "3",
    KEY_KP4: "4",
    KEY_KP5: "5",
    KEY_KP6: "6",
    KEY_KP7: "7",
    KEY_KP8: "8",
    KEY_KP9: "9",
}


def keypad_event_for_key(code: int, value: int) -> KeypadEvent | None:
    if int(value) != 1:
        return None
    code = int(code)
    if code in _DIGIT_CODES:
        return KeypadEvent("edit_list_key", button_id=_DIGIT_CODES[code])
    if code in {KEY_KPENTER, KEY_ENTER}:
        return KeypadEvent("send_list_field")
    if code == KEY_KPMINUS:
        return KeypadEvent("toggle_list_sign")
    if code in {KEY_KPPLUS, KEY_SPACE}:
        return KeypadEvent("edit_list_key", button_id="space")
    if code in {KEY_KPDOT, KEY_BACKSPACE, KEY_DELETE}:
        return KeypadEvent("edit_list_key", button_id="backspace")
    if code == KEY_KPSLASH:
        return KeypadEvent("step_list_field", delta=-1)
    if code == KEY_KPASTERISK:
        return KeypadEvent("step_list_field", delta=1)
    return None


class NumericKeypadReader:
    def __init__(
        self,
        device: str | None = None,
        *,
        auto_detect: bool = False,
        exclusive: bool = True,
        retry_seconds: float = 2.0,
    ) -> None:
        self.device = str(device or "")
        self.auto_detect = bool(auto_detect)
        self.exclusive = bool(exclusive)
        self.retry_seconds = max(0.1, float(retry_seconds))
        self.fd: int | None = None
        self.connected_path = ""
        self._next_connect_at = 0.0

    def _candidate_paths(self) -> list[str]:
        if self.device:
            return [self.device]
        if not self.auto_detect:
            return []
        return sorted(glob.glob("/dev/input/by-id/*-event-kbd"))

    def _connect(self) -> bool:
        if self.fd is not None:
            return True
        now = time.monotonic()
        if now < self._next_connect_at:
            return False
        self._next_connect_at = now + self.retry_seconds
        for path in self._candidate_paths():
            try:
                fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
                if self.exclusive:
                    fcntl.ioctl(fd, EVIOCGRAB, 1)
            except OSError:
                try:
                    os.close(fd)
                except (OSError, UnboundLocalError):
                    pass
                continue
            self.fd = fd
            self.connected_path = path
            print(f"Numeric keypad connected: {path}")
            return True
        return False

    def _disconnect(self) -> None:
        fd = self.fd
        path = self.connected_path
        self.fd = None
        self.connected_path = ""
        if fd is None:
            return
        if self.exclusive:
            try:
                fcntl.ioctl(fd, EVIOCGRAB, 0)
            except OSError:
                pass
        try:
            os.close(fd)
        except OSError:
            pass
        if path:
            print(f"Numeric keypad disconnected: {path}")

    def read_events(self) -> list[KeypadEvent]:
        if not self._connect() or self.fd is None:
            return []
        events: list[KeypadEvent] = []
        try:
            while select.select([self.fd], [], [], 0)[0]:
                data = os.read(self.fd, _EVENT_STRUCT.size * 32)
                if not data:
                    self._disconnect()
                    break
                for offset in range(0, len(data) - (_EVENT_STRUCT.size - 1), _EVENT_STRUCT.size):
                    _sec, _usec, event_type, code, value = _EVENT_STRUCT.unpack_from(data, offset)
                    if event_type != EV_KEY:
                        continue
                    event = keypad_event_for_key(code, value)
                    if event is not None:
                        events.append(event)
        except (OSError, ValueError):
            self._disconnect()
        return events

    @property
    def is_connected(self) -> bool:
        return self.fd is not None

    def close(self) -> None:
        self._disconnect()

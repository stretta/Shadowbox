"""
Shadowbox
Hardware UI for RNBO Runner

https://github.com/stretta/shadowbox
"""

#!/usr/bin/env python3

from __future__ import annotations

import time
from dataclasses import dataclass

import pigpio


# ============================================================
# EVENTS
# ============================================================

@dataclass
class EncoderEvent:
    kind: str
    delta: int = 0


# ============================================================
# ENCODER INPUT
# ============================================================

class EncoderInput:
    """
    Rotary encoder + pushbutton input using pigpio.

    Emits events:
    - EncoderEvent(kind="rotate", delta=+1)
    - EncoderEvent(kind="rotate", delta=-1)
    - EncoderEvent(kind="short_press")
    - EncoderEvent(kind="long_press")
    """

    # Full-step quadrature decode table
    _TRANS = (
         0, -1, +1,  0,
        +1,  0,  0, -1,
        -1,  0,  0, +1,
         0, +1, -1,  0,
    )

    def __init__(
        self,
        clk_pin: int = 17,
        dt_pin: int = 27,
        sw_pin: int = 22,
        steps_per_detent: int = 4,
        ab_glitch_us: int = 200,
        sw_glitch_us: int = 8000,
        long_press_seconds: float = 0.6,
    ):
        self.clk_pin = clk_pin
        self.dt_pin = dt_pin
        self.sw_pin = sw_pin

        self.steps_per_detent = steps_per_detent
        self.long_press_seconds = long_press_seconds

        self._events: list[EncoderEvent] = []

        self._pi = pigpio.pi()
        if not self._pi.connected:
            raise RuntimeError("pigpio daemon not running")

        for pin in (self.clk_pin, self.dt_pin, self.sw_pin):
            self._pi.set_mode(pin, pigpio.INPUT)
            self._pi.set_pull_up_down(pin, pigpio.PUD_UP)

        self._pi.set_glitch_filter(self.clk_pin, ab_glitch_us)
        self._pi.set_glitch_filter(self.dt_pin, ab_glitch_us)
        self._pi.set_glitch_filter(self.sw_pin, sw_glitch_us)

        self._enc_state = self._read_ab()
        self._enc_accum = 0
        self._last_move_sign = 0

        self._press_started_at: float | None = None
        self._long_press_fired = False

        self._cb_a = self._pi.callback(self.clk_pin, pigpio.EITHER_EDGE, self._on_ab)
        self._cb_b = self._pi.callback(self.dt_pin, pigpio.EITHER_EDGE, self._on_ab)

    # --------------------------------------------------------
    # low-level reads
    # --------------------------------------------------------

    def _read_ab(self) -> int:
        a = self._pi.read(self.clk_pin)
        b = self._pi.read(self.dt_pin)
        return (a << 1) | b

    def _button_pressed(self) -> bool:
        return self._pi.read(self.sw_pin) == 0

    # --------------------------------------------------------
    # quadrature callback
    # --------------------------------------------------------

    def _on_ab(self, gpio: int, level: int, tick: int) -> None:
        if level == 2:
            return

        new = self._read_ab()
        move = self._TRANS[(self._enc_state << 2) | new]
        self._enc_state = new

        if move == 0:
            return

        move_sign = 1 if move > 0 else -1

        # Reversal fix:
        # discard any partial accumulation when direction changes
        if self._last_move_sign != 0 and move_sign != self._last_move_sign:
            self._enc_accum = 0

        self._last_move_sign = move_sign
        self._enc_accum += move

        if self._enc_accum >= self.steps_per_detent:
            self._enc_accum -= self.steps_per_detent
            self._events.append(EncoderEvent(kind="rotate", delta=+1))

        elif self._enc_accum <= -self.steps_per_detent:
            self._enc_accum += self.steps_per_detent
            self._events.append(EncoderEvent(kind="rotate", delta=-1))

    # --------------------------------------------------------
    # button polling
    # --------------------------------------------------------

    def _poll_button(self) -> None:
        now = time.monotonic()
        pressed = self._button_pressed()

        if pressed and self._press_started_at is None:
            self._press_started_at = now
            self._long_press_fired = False

        if self._press_started_at is None:
            return

        held = now - self._press_started_at

        if pressed and (not self._long_press_fired) and held >= self.long_press_seconds:
            self._long_press_fired = True
            self._events.append(EncoderEvent(kind="long_press"))

        if not pressed:
            if not self._long_press_fired:
                self._events.append(EncoderEvent(kind="short_press"))

            self._press_started_at = None
            self._long_press_fired = False

    # --------------------------------------------------------
    # public API
    # --------------------------------------------------------

    def get_events(self) -> list[EncoderEvent]:
        self._poll_button()
        events = self._events[:]
        self._events.clear()
        return events

    def close(self) -> None:
        if hasattr(self, "_cb_a") and self._cb_a is not None:
            self._cb_a.cancel()
        if hasattr(self, "_cb_b") and self._cb_b is not None:
            self._cb_b.cancel()
        if hasattr(self, "_pi") and self._pi is not None:
            self._pi.stop()

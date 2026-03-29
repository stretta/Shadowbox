"""
Shadowbox
Hardware UI for RNBO Runner

https://github.com/stretta/shadowbox
"""

#!/usr/bin/env python3

from __future__ import annotations

import os
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
        clk_pin: int | None = None,
        dt_pin: int | None = None,
        sw_pin: int | None = None,
        back_pin: int | None = None,
        steps_per_detent: int = 4,
        ab_glitch_us: int = 0,
        sw_glitch_us: int = 8000,
        back_glitch_us: int = 0,
        long_press_seconds: float = 0.6,
    ):
        self.clk_pin = _env_int("SHADOWBOX_ENCODER_CLK", 17 if clk_pin is None else clk_pin)
        self.dt_pin = _env_int("SHADOWBOX_ENCODER_DT", 27 if dt_pin is None else dt_pin)
        self.sw_pin = _env_int("SHADOWBOX_ENCODER_SW", 22 if sw_pin is None else sw_pin)
        self.back_pin = _env_optional_int("SHADOWBOX_BACK_BUTTON_PIN", back_pin)

        self.steps_per_detent = _env_int("SHADOWBOX_ENCODER_STEPS_PER_DETENT", steps_per_detent)
        self.long_press_seconds = _env_float("SHADOWBOX_ENCODER_LONG_PRESS_SECONDS", long_press_seconds)
        ab_glitch_us = _env_int("SHADOWBOX_ENCODER_AB_GLITCH_US", ab_glitch_us)
        sw_glitch_us = _env_int("SHADOWBOX_ENCODER_SW_GLITCH_US", sw_glitch_us)
        self.back_glitch_us = _env_int(
            "SHADOWBOX_BACK_BUTTON_GLITCH_US",
            back_glitch_us,
        )

        self._events: list[EncoderEvent] = []

        self._pi = pigpio.pi()
        if not self._pi.connected:
            raise RuntimeError("pigpio daemon not running")

        input_pins = [self.clk_pin, self.dt_pin, self.sw_pin]
        if self.back_pin is not None and self.back_pin not in input_pins:
            input_pins.append(self.back_pin)

        for pin in input_pins:
            self._pi.set_mode(pin, pigpio.INPUT)
            self._pi.set_pull_up_down(pin, pigpio.PUD_UP)

        self._pi.set_glitch_filter(self.clk_pin, ab_glitch_us)
        self._pi.set_glitch_filter(self.dt_pin, ab_glitch_us)
        self._pi.set_glitch_filter(self.sw_pin, sw_glitch_us)
        if self.back_pin is not None:
            self._pi.set_glitch_filter(self.back_pin, self.back_glitch_us)

        self._enc_state = self._read_ab()
        self._enc_accum = 0
        self._last_move_sign = 0

        self._encoder_press_started_at: float | None = None
        self._encoder_long_press_fired = False
        self._back_button_was_pressed = False

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

    def _back_button_pressed(self) -> bool:
        return self.back_pin is not None and self._pi.read(self.back_pin) == 0

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

        if pressed and self._encoder_press_started_at is None:
            self._encoder_press_started_at = now
            self._encoder_long_press_fired = False

        if self._encoder_press_started_at is None:
            return

        held = now - self._encoder_press_started_at

        if pressed and (not self._encoder_long_press_fired) and held >= self.long_press_seconds:
            self._encoder_long_press_fired = True
            self._events.append(EncoderEvent(kind="long_press"))

        if not pressed:
            if not self._encoder_long_press_fired:
                self._events.append(EncoderEvent(kind="short_press"))

            self._encoder_press_started_at = None
            self._encoder_long_press_fired = False

    def _poll_back_button(self) -> None:
        if self.back_pin is None:
            return

        pressed = self._back_button_pressed()
        if pressed and not self._back_button_was_pressed:
            self._events.append(EncoderEvent(kind="long_press"))
        self._back_button_was_pressed = pressed

    # --------------------------------------------------------
    # public API
    # --------------------------------------------------------

    def get_events(self) -> list[EncoderEvent]:
        self._poll_button()
        self._poll_back_button()
        events = self._events[:]
        self._events.clear()
        return events

    def is_encoder_button_pressed(self) -> bool:
        return self._button_pressed()

    def is_back_button_configured(self) -> bool:
        return self.back_pin is not None

    def is_back_button_pressed(self) -> bool:
        return self._back_button_pressed()

    def close(self) -> None:
        if hasattr(self, "_cb_a") and self._cb_a is not None:
            self._cb_a.cancel()
        if hasattr(self, "_cb_b") and self._cb_b is not None:
            self._cb_b.cancel()
        if hasattr(self, "_pi") and self._pi is not None:
            self._pi.stop()


def _env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    return int(value, 0)


def _env_float(name: str, default: float) -> float:
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    return float(value)


def _env_optional_int(name: str, default: int | None) -> int | None:
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    lowered = value.strip().lower()
    if lowered in {"none", "off", "disabled"}:
        return None
    return int(value, 0)

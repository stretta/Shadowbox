#!/usr/bin/env python3
"""
Raw ST7789 SPI TFT backend using spidev + GPIO control.
"""

from __future__ import annotations

import time

from shadowbox.display.base import DisplayBackend
from shadowbox.display.tft_text import line_height, measure_text, render_text_mask

try:
    from PIL import Image, ImageDraw
except ImportError as exc:  # pragma: no cover - hardware dependency
    raise RuntimeError("Pillow is required for the ST7789 raw display backend") from exc

try:
    import spidev
except ImportError as exc:  # pragma: no cover - hardware dependency
    raise RuntimeError("spidev is required for the ST7789 raw display backend") from exc

try:
    from gpiozero import PWMOutputDevice
except ImportError:  # pragma: no cover - optional hardware dependency
    PWMOutputDevice = None


class _GPIOPin:
    def __init__(self, bcm_pin: int):
        self.pin = bcm_pin
        self._backend = None
        self._line_request = None

        try:
            import gpiod

            self._backend = "gpiod"
            self._value_enum = gpiod.line.Value
            settings = gpiod.LineSettings(
                direction=gpiod.line.Direction.OUTPUT,
                output_value=self._value_enum.INACTIVE,
            )
            self._chip = gpiod.Chip("/dev/gpiochip4")
            self._line_request = self._chip.request_lines(
                consumer=f"shadowbox-st7789-raw-{bcm_pin}",
                config={bcm_pin: settings},
            )
            return
        except Exception:
            self._line_request = None

        try:
            import RPi.GPIO as GPIO

            self._backend = "rpi_gpio"
            self._gpio = GPIO
            GPIO.setwarnings(False)
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(self.pin, GPIO.OUT, initial=GPIO.LOW)
            return
        except Exception as exc:
            raise RuntimeError(
                f"Could not configure GPIO{bcm_pin}. Install python3-rpi.gpio or ensure python3-gpiod is available."
            ) from exc

    def write(self, high: bool) -> None:
        if self._backend == "gpiod":
            value = self._value_enum.ACTIVE if high else self._value_enum.INACTIVE
            self._line_request.set_value(self.pin, value)
            return
        self._gpio.output(self.pin, self._gpio.HIGH if high else self._gpio.LOW)

    def close(self) -> None:
        if self._backend == "gpiod" and self._line_request is not None:
            self._line_request.release()


class ST7789RawDisplay(DisplayBackend):
    def __init__(
        self,
        *,
        bus: int = 0,
        cs: int = 0,
        dc: int = 25,
        rst: int | None = 24,
        backlight: int | None = 18,
        spi_speed_hz: int = 40_000_000,
        rotation: int = 0,
        physical_width: int = 320,
        physical_height: int = 240,
        offset_left: int = 0,
        offset_top: int = 0,
        logical_width: int = 320,
        logical_height: int = 240,
        invert_colors: bool = False,
    ):
        if rotation not in {0, 180}:
            raise ValueError("ST7789 raw backend currently supports rotation 0 or 180")

        self.width = logical_width
        self.height = logical_height
        self.physical_width = physical_width
        self.physical_height = physical_height
        self.rotation = rotation
        self.offset_left = offset_left
        self.offset_top = offset_top
        self.invert_colors = invert_colors
        self.is_sleeping = False
        self._backlight_level = 1.0
        self._contrast_level = 255

        self._canvas = Image.new("L", (self.width, self.height), 0)
        self._draw = ImageDraw.Draw(self._canvas)

        self._spi = spidev.SpiDev()
        self._spi.open(bus, cs)
        self._spi.max_speed_hz = spi_speed_hz
        self._spi.mode = 0
        self._spi.no_cs = False

        self._dc = _GPIOPin(dc)
        self._rst = _GPIOPin(rst) if rst is not None else None
        self._backlight = None
        if backlight is not None and PWMOutputDevice is not None:
            try:
                self._backlight = PWMOutputDevice(
                    backlight,
                    active_high=True,
                    initial_value=0.0,
                    frequency=1000,
                )
            except Exception:
                self._backlight = None
        if self._backlight is None and backlight is not None:
            self._backlight = _GPIOPin(backlight)
        self._set_backlight(1.0)

    def _command(self, cmd: int, data: bytes | bytearray | None = None) -> None:
        self._dc.write(False)
        self._spi.xfer2([cmd & 0xFF])
        if data:
            self._data(data)

    def _data(self, data: bytes | bytearray) -> None:
        self._dc.write(True)
        chunk = 4096
        for i in range(0, len(data), chunk):
            self._spi.xfer3(list(data[i : i + chunk]))

    def _hardware_reset(self) -> None:
        if self._rst is None:
            return
        self._rst.write(True)
        time.sleep(0.05)
        self._rst.write(False)
        time.sleep(0.05)
        self._rst.write(True)
        time.sleep(0.12)

    def _set_window(self, x0: int, y0: int, x1: int, y1: int) -> None:
        self._command(0x2A, bytes([(x0 >> 8) & 0xFF, x0 & 0xFF, (x1 >> 8) & 0xFF, x1 & 0xFF]))
        self._command(0x2B, bytes([(y0 >> 8) & 0xFF, y0 & 0xFF, (y1 >> 8) & 0xFF, y1 & 0xFF]))
        self._command(0x2C)

    def _madctl(self) -> int:
        # Variant B from the raw test was the working sequence on the custom pt4 module.
        return 0x70 if self.rotation == 0 else 0xE0

    def init(self) -> None:
        self._hardware_reset()
        self._command(0x01)
        time.sleep(0.15)
        self._command(0x11)
        time.sleep(0.12)
        self._command(0x3A, b"\x55")
        self._command(0x36, bytes([self._madctl()]))
        self._command(0xB2, b"\x0C\x0C\x00\x33\x33")
        self._command(0xB7, b"\x35")
        self._command(0xBB, b"\x19")
        self._command(0xC0, b"\x2C")
        self._command(0xC2, b"\x01")
        self._command(0xC3, b"\x12")
        self._command(0xC4, b"\x20")
        self._command(0xC6, b"\x0F")
        self._command(0xD0, b"\xA4\xA1")
        self._command(0x21 if self.invert_colors else 0x20)
        self._command(0x29)
        time.sleep(0.05)
        self.is_sleeping = False
        self._set_backlight(self._backlight_level)
        self.clear()
        self.show()

    def clear(self) -> None:
        self._draw.rectangle((0, 0, self.width, self.height), fill=0)

    def _frame_bytes(self) -> bytes:
        image = self._canvas
        if self.width != self.physical_width or self.height != self.physical_height:
            image = image.resize((self.physical_width, self.physical_height), Image.Resampling.NEAREST)
        data = image.tobytes()
        out = bytearray(len(data) * 2)
        for i, value in enumerate(data):
            value = (value * self._contrast_level) // 255
            if self.invert_colors:
                value = 255 - value
            # Map 8-bit grayscale to RGB565 while preserving antialiasing.
            r = value >> 3
            g = value >> 2
            b = value >> 3
            rgb565 = (r << 11) | (g << 5) | b
            out[i * 2] = (rgb565 >> 8) & 0xFF
            out[i * 2 + 1] = rgb565 & 0xFF
        return bytes(out)

    def show(self) -> None:
        if self.is_sleeping:
            return
        x0 = self.offset_left
        y0 = self.offset_top
        x1 = x0 + self.physical_width - 1
        y1 = y0 + self.physical_height - 1
        self._set_window(x0, y0, x1, y1)
        self._data(self._frame_bytes())

    def _set_backlight(self, duty_cycle: float) -> None:
        duty_cycle = max(0.0, min(1.0, float(duty_cycle)))
        self._backlight_level = duty_cycle
        if self._backlight is None:
            return
        if hasattr(self._backlight, "value"):
            self._backlight.value = duty_cycle
            return
        self._backlight.write(duty_cycle > 0.0)

    def set_contrast(self, value: int) -> None:
        contrast = max(0, min(255, int(value)))
        self._contrast_level = contrast
        self._set_backlight(contrast / 255.0)

    def sleep(self) -> None:
        if self.is_sleeping:
            return
        self.is_sleeping = True
        self._command(0x28)
        if self._backlight is not None:
            if hasattr(self._backlight, "value"):
                self._backlight.value = 0.0
            else:
                self._backlight.write(False)

    def wake(self) -> None:
        if self.is_sleeping:
            self._command(0x29)
            self.is_sleeping = False
            self._set_backlight(self._backlight_level)
            self.show()

    def pixel(self, x: int, y: int, on: bool = True) -> None:
        if not (0 <= x < self.width and 0 <= y < self.height):
            return
        self._draw.point((x, y), fill=255 if on else 0)

    def hline(self, x: int, y: int, w: int, on: bool = True) -> None:
        if w <= 0:
            return
        self._draw.line((x, y, x + w - 1, y), fill=255 if on else 0)

    def vline(self, x: int, y: int, h: int, on: bool = True) -> None:
        if h <= 0:
            return
        self._draw.line((x, y, x, y + h - 1), fill=255 if on else 0)

    def rect(self, x: int, y: int, w: int, h: int, on: bool = True, fill: bool = False) -> None:
        if w <= 0 or h <= 0:
            return
        if fill:
            self._draw.rectangle((x, y, x + w - 1, y + h - 1), outline=255 if on else 0, fill=255 if on else 0)
            return
        self._draw.rectangle((x, y, x + w - 1, y + h - 1), outline=255 if on else 0, fill=None)

    def text(self, s: str, x: int, y: int, on: bool = True) -> None:
        self.text_with_style(s, x, y, 1, "regular", on=on)

    def text_scaled(self, s: str, x: int, y: int, scale: int = 1, on: bool = True) -> None:
        self.text_with_style(s, x, y, scale, "regular", on=on)

    def text_with_style(self, s: str, x: int, y: int, scale: int = 1, weight: str = "regular", on: bool = True) -> None:
        mask = render_text_mask(str(s), scale, weight)
        self._canvas.paste(255 if on else 0, (x, y, x + mask.width, y + mask.height), mask)

    def measure_text(self, s: str, scale: int = 1, weight: str = "regular") -> tuple[int, int]:
        return measure_text(str(s), scale, weight)

    def line_height(self, scale: int = 1, weight: str = "regular") -> int:
        return line_height(scale, weight)

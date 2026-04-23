#!/usr/bin/env python3
"""
Waveshare 2-inch ST7789V SPI TFT backend.

This backend follows the init sequence used by Waveshare's working Python demo
for the "2inch LCD Module" and preserves Shadowbox's existing monochrome UI by
scaling a logical framebuffer into a color PIL image before sending it to the
panel.
"""

from __future__ import annotations

from time import sleep

from shadowbox.display.base import DisplayBackend
from shadowbox.display.tft_text import line_height, mask_to_rgb, measure_text, render_text_mask

try:
    import numpy as np
except ImportError as exc:  # pragma: no cover - hardware dependency
    raise RuntimeError("numpy is required for the Waveshare 2-inch backend") from exc

try:
    from PIL import Image, ImageDraw
except ImportError as exc:  # pragma: no cover - hardware dependency
    raise RuntimeError("Pillow is required for the Waveshare 2-inch backend") from exc

try:
    import spidev
except ImportError as exc:  # pragma: no cover - hardware dependency
    raise RuntimeError("spidev is required for the Waveshare 2-inch backend") from exc

try:
    from gpiozero import DigitalOutputDevice, PWMOutputDevice
except ImportError as exc:  # pragma: no cover - hardware dependency
    raise RuntimeError("gpiozero is required for the Waveshare 2-inch backend") from exc


class Waveshare2InchDisplay(DisplayBackend):
    def __init__(
        self,
        *,
        spi_bus: int = 0,
        spi_cs: int = 0,
        spi_speed_hz: int = 40_000_000,
        dc: int = 25,
        rst: int = 27,
        backlight: int | None = 18,
        logical_width: int = 320,
        logical_height: int = 240,
        fg_color: tuple[int, int, int] = (255, 255, 255),
        bg_color: tuple[int, int, int] = (0, 0, 0),
    ):
        self.width = logical_width
        self.height = logical_height
        self._canvas = Image.new("L", (self.width, self.height), 0)
        self._draw = ImageDraw.Draw(self._canvas)
        self.is_sleeping = False
        self._backlight_level = 1.0
        self.fg_color = fg_color
        self.bg_color = bg_color

        self.panel_width = 320
        self.panel_height = 240

        self._spi = spidev.SpiDev(spi_bus, spi_cs)
        self._spi.max_speed_hz = spi_speed_hz
        self._spi.mode = 0b00

        self._dc = DigitalOutputDevice(dc, active_high=True, initial_value=False)
        self._rst = DigitalOutputDevice(rst, active_high=True, initial_value=False)
        self._backlight = (
            PWMOutputDevice(backlight, active_high=True, initial_value=0.0, frequency=1000)
            if backlight is not None
            else None
        )

    def _command(self, cmd: int) -> None:
        self._dc.off()
        self._spi.writebytes([cmd & 0xFF])

    def _data(self, values: list[int]) -> None:
        if not values:
            return
        self._dc.on()
        self._spi.writebytes([value & 0xFF for value in values])

    def _reset(self) -> None:
        self._rst.on()
        sleep(0.01)
        self._rst.off()
        sleep(0.01)
        self._rst.on()
        sleep(0.01)

    def _set_backlight(self, duty_cycle: float) -> None:
        self._backlight_level = max(0.0, min(1.0, duty_cycle))
        if self._backlight is not None:
            self._backlight.value = self._backlight_level

    def _initialize_panel(self) -> None:
        self._reset()
        self._set_backlight(self._backlight_level)

        init_sequence = [
            # Landscape orientation that matches the OLED reading direction.
            (0x36, [0x70]),
            (0x3A, [0x05]),
            (0x21, []),
            (0x2A, [0x00, 0x00, 0x00, 0xEF]),
            (0x2B, [0x00, 0x00, 0x01, 0x3F]),
            (0xB2, [0x0C, 0x0C, 0x00, 0x33, 0x33]),
            (0xB7, [0x35]),
            (0xBB, [0x1F]),
            (0xC0, [0x2C]),
            (0xC2, [0x01]),
            (0xC3, [0x12]),
            (0xC4, [0x20]),
            (0xC6, [0x0F]),
            (0xD0, [0xA4, 0xA1]),
            (0xE0, [0xD0, 0x08, 0x11, 0x08, 0x0C, 0x15, 0x39, 0x33, 0x50, 0x36, 0x13, 0x14, 0x29, 0x2D]),
            (0xE1, [0xD0, 0x08, 0x10, 0x08, 0x06, 0x06, 0x39, 0x44, 0x51, 0x0B, 0x16, 0x14, 0x2F, 0x31]),
            (0x21, []),
            (0x11, []),
            (0x29, []),
        ]

        for cmd, data in init_sequence:
            self._command(cmd)
            self._data(data)

    def init(self) -> None:
        self._initialize_panel()
        self.is_sleeping = False
        self.clear()
        self.show()

    def _set_window(self, x_start: int, y_start: int, x_end: int, y_end: int) -> None:
        self._command(0x2A)
        self._data([x_start >> 8, x_start & 0xFF, x_end >> 8, (x_end - 1) & 0xFF])
        self._command(0x2B)
        self._data([y_start >> 8, y_start & 0xFF, y_end >> 8, (y_end - 1) & 0xFF])
        self._command(0x2C)

    def _to_panel_image(self) -> Image.Image:
        logical = mask_to_rgb(self._canvas, self.fg_color, self.bg_color)

        if self.width == self.panel_width and self.height == self.panel_height:
            return logical

        scale = max(1, min(self.panel_width // self.width, self.panel_height // self.height))
        scaled_size = (self.width * scale, self.height * scale)
        scaled = logical.resize(scaled_size, Image.Resampling.NEAREST)

        canvas = Image.new("RGB", (self.panel_width, self.panel_height), self.bg_color)
        left = max(0, (self.panel_width - scaled_size[0]) // 2)
        top = max(0, (self.panel_height - scaled_size[1]) // 2)
        canvas.paste(scaled, (left, top))
        return canvas

    def show(self) -> None:
        if self.is_sleeping:
            return

        image = self._to_panel_image()
        img = np.asarray(image)
        pix = np.zeros((image.size[1], image.size[0], 2), dtype=np.uint8)
        pix[..., [0]] = np.add(np.bitwise_and(img[..., [0]], 0xF8), np.right_shift(img[..., [1]], 5))
        pix[..., [1]] = np.add(np.bitwise_and(np.left_shift(img[..., [1]], 3), 0xE0), np.right_shift(img[..., [2]], 3))
        data = pix.flatten().tolist()

        self._command(0x36)
        self._data([0x70])
        self._set_window(0, 0, self.panel_width, self.panel_height)
        self._dc.on()
        for i in range(0, len(data), 4096):
            self._spi.writebytes(data[i:i + 4096])

    def clear(self) -> None:
        self._draw.rectangle((0, 0, self.width, self.height), fill=0)

    def set_contrast(self, value: int) -> None:
        # TFT brightness is backlight-driven rather than OLED contrast-driven.
        duty = max(0, min(255, int(value))) / 255.0
        self._set_backlight(duty)

    def sleep(self) -> None:
        if not self.is_sleeping:
            self._command(0x28)
            self._set_backlight(0.0)
            self.is_sleeping = True

    def wake(self) -> None:
        if self.is_sleeping:
            # Reinitialize on wake so the panel reliably resumes after deep idle.
            self._initialize_panel()
            self.is_sleeping = False
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

    def fill_rect_level(self, x: int, y: int, w: int, h: int, level: int) -> None:
        if w <= 0 or h <= 0:
            return
        fill = max(0, min(255, int(level)))
        self._draw.rectangle((x, y, x + w - 1, y + h - 1), outline=fill, fill=fill)

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

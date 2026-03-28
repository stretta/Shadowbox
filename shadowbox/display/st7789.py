#!/usr/bin/env python3
"""
ST7789 SPI TFT backend that preserves the existing monochrome UI layout.
"""

from __future__ import annotations

from shadowbox.display.base import DisplayBackend
from shadowbox.display.tft_text import line_height, mask_to_rgb, measure_text, render_text_mask

try:
    from PIL import Image, ImageDraw
except ImportError as exc:  # pragma: no cover - hardware dependency
    raise RuntimeError("Pillow is required for the ST7789 display backend") from exc

try:
    import st7789
except ImportError as exc:  # pragma: no cover - hardware dependency
    raise RuntimeError("st7789 is required for the ST7789 display backend") from exc

try:
    from gpiozero import PWMOutputDevice
except ImportError:  # pragma: no cover - optional hardware dependency
    PWMOutputDevice = None


class ST7789Display(DisplayBackend):
    def __init__(
        self,
        *,
        bus: int = 0,
        cs: int = 0,
        dc: int = 9,
        rst: int | None = 13,
        backlight: int | None = 19,
        spi_speed_hz: int = 80_000_000,
        rotation: int = 90,
        physical_width: int = 320,
        physical_height: int = 240,
        offset_left: int = 0,
        offset_top: int = 0,
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
        self.fg_color = fg_color
        self.bg_color = bg_color
        self._backlight = None

        device_backlight = backlight
        if backlight is not None and PWMOutputDevice is not None:
            self._backlight = PWMOutputDevice(
                backlight,
                active_high=True,
                initial_value=0.0,
                frequency=1000,
            )
            device_backlight = None

        self.physical_width = physical_width
        self.physical_height = physical_height
        self._device = st7789.ST7789(
            port=bus,
            cs=cs,
            dc=dc,
            rst=rst,
            backlight=device_backlight,
            width=physical_width,
            height=physical_height,
            rotation=rotation,
            offset_left=offset_left,
            offset_top=offset_top,
            spi_speed_hz=spi_speed_hz,
        )

    def _set_backlight(self, duty_cycle: float) -> None:
        duty_cycle = max(0.0, min(1.0, duty_cycle))
        if self._backlight is not None:
            self._backlight.value = duty_cycle
            return

        setter = getattr(self._device, "set_backlight", None)
        if callable(setter):
            setter(duty_cycle > 0.0)

    def init(self) -> None:
        self.is_sleeping = False
        self._set_backlight(1.0)
        self.clear()
        self.show()

    def clear(self) -> None:
        self._draw.rectangle((0, 0, self.width, self.height), fill=0)

    def _to_image(self) -> Image.Image:
        logical = mask_to_rgb(self._canvas, self.fg_color, self.bg_color)

        if self.width == self.physical_width and self.height == self.physical_height:
            return logical

        scale = max(1, min(self.physical_width // self.width, self.physical_height // self.height))
        scaled_size = (self.width * scale, self.height * scale)
        scaled = logical.resize(scaled_size, Image.Resampling.NEAREST)

        canvas = Image.new("RGB", (self.physical_width, self.physical_height), self.bg_color)
        left = max(0, (self.physical_width - scaled_size[0]) // 2)
        top = max(0, (self.physical_height - scaled_size[1]) // 2)
        canvas.paste(scaled, (left, top))
        return canvas

    def show(self) -> None:
        if self.is_sleeping:
            return
        self._device.display(self._to_image())

    def set_contrast(self, value: int) -> None:
        # Map the OLED-era contrast API onto TFT backlight brightness.
        self._set_backlight(max(0, min(255, int(value))) / 255.0)

    def sleep(self) -> None:
        if self.is_sleeping:
            return
        self.is_sleeping = True
        self._set_backlight(0.0)

    def wake(self) -> None:
        if self.is_sleeping:
            self.is_sleeping = False
            self._set_backlight(1.0)
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

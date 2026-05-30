#!/usr/bin/env python3
"""
Waveshare 5-inch DSI LCD framebuffer backend.

The panel is driven by Raspberry Pi's DSI/KMS stack rather than a userspace SPI
controller. Shadowbox renders into an RGB logical canvas and writes packed
pixels to the 800x480 DSI framebuffer, /dev/fb0 by default.
"""

from __future__ import annotations

import glob
import mmap
import os
from pathlib import Path

from shadowbox.display.base import DisplayBackend
from shadowbox.display.tft_text import line_height, measure_text, render_text_line_mask, render_text_mask

try:
    from PIL import Image, ImageDraw
except ImportError as exc:  # pragma: no cover - hardware dependency
    raise RuntimeError("Pillow is required for the Waveshare 5-inch DSI backend") from exc

try:
    import numpy as np
except Exception:  # pragma: no cover - optional fast path dependency
    np = None


class Waveshare5InchDSIDisplay(DisplayBackend):
    def __init__(
        self,
        *,
        framebuffer: str = "/dev/fb0",
        physical_width: int = 800,
        physical_height: int = 480,
        logical_width: int = 800,
        logical_height: int = 480,
        pixel_format: str = "auto",
        backlight_path: str | None = None,
        fg_color: tuple[int, int, int] = (244, 247, 242),
        bg_color: tuple[int, int, int] = (15, 18, 18),
        text_scale_factor: float = 1.0,
    ):
        self.width = logical_width
        self.height = logical_height
        self.physical_width = physical_width
        self.physical_height = physical_height
        self.framebuffer = framebuffer
        self.pixel_format = pixel_format.strip().lower()
        self.fg_color = fg_color
        self.bg_color = bg_color
        self.text_scale_factor = float(text_scale_factor)
        self.is_sleeping = False
        self._backlight_level = 1.0
        self._contrast_level = 255

        self._canvas = Image.new("RGB", (self.width, self.height), self.bg_color)
        self._draw = ImageDraw.Draw(self._canvas)
        self._fb = None
        self._fb_map = None
        self._fb_size = 0
        self._stride = self.physical_width * 4
        self._bytes_per_pixel = 4
        self._backlight_dir = Path(backlight_path) if backlight_path else self._find_backlight_dir()
        self._backlight_max = self._read_backlight_max()

    @staticmethod
    def _sysfs_int(path: str | Path) -> int | None:
        try:
            return int(Path(path).read_text(encoding="ascii").strip(), 0)
        except (OSError, ValueError):
            return None

    @staticmethod
    def _sysfs_text(path: str | Path) -> str | None:
        try:
            return Path(path).read_text(encoding="ascii").strip()
        except OSError:
            return None

    @staticmethod
    def _find_backlight_dir() -> Path | None:
        candidates = sorted(glob.glob("/sys/class/backlight/*"))
        return Path(candidates[0]) if candidates else None

    def _read_backlight_max(self) -> int:
        if self._backlight_dir is None:
            return 255
        value = self._sysfs_int(self._backlight_dir / "max_brightness")
        return value if value is not None and value > 0 else 255

    def _apply_backlight(self, duty_cycle: float) -> None:
        duty_cycle = max(0.0, min(1.0, float(duty_cycle)))
        if self._backlight_dir is None:
            return
        value = round(duty_cycle * self._backlight_max)
        try:
            (self._backlight_dir / "brightness").write_text(f"{value}\n", encoding="ascii")
        except OSError:
            # Some images expose brightness as root-writable only. Rendering can
            # still continue; dim/sleep simply becomes unavailable.
            pass

    def _set_backlight(self, duty_cycle: float) -> None:
        duty_cycle = max(0.0, min(1.0, float(duty_cycle)))
        self._backlight_level = duty_cycle
        self._apply_backlight(duty_cycle)

    def _read_framebuffer_geometry(self) -> None:
        fb_name = Path(self.framebuffer).name
        sysfs = Path("/sys/class/graphics") / fb_name

        virtual_size = self._sysfs_text(sysfs / "virtual_size")
        if virtual_size and "," in virtual_size:
            width, height = virtual_size.split(",", 1)
            self.physical_width = int(width)
            self.physical_height = int(height)

        bits_per_pixel = self._sysfs_int(sysfs / "bits_per_pixel")
        if bits_per_pixel in {16, 24, 32}:
            self._bytes_per_pixel = bits_per_pixel // 8

        stride = self._sysfs_int(sysfs / "stride")
        if stride is None:
            stride = self.physical_width * self._bytes_per_pixel
        self._stride = stride

        if self.pixel_format == "auto":
            self.pixel_format = "rgb565" if self._bytes_per_pixel == 2 else "bgrx8888"

    def init(self) -> None:
        self._read_framebuffer_geometry()
        self._fb_size = self._stride * self.physical_height
        try:
            self._fb = os.open(self.framebuffer, os.O_RDWR)
            self._fb_map = mmap.mmap(self._fb, self._fb_size, mmap.MAP_SHARED, mmap.PROT_WRITE | mmap.PROT_READ)
        except OSError as exc:  # pragma: no cover - hardware dependency
            raise RuntimeError(
                f"Could not open {self.framebuffer}. Enable the Waveshare DSI overlay and ensure the framebuffer exists."
            ) from exc
        self.is_sleeping = False
        self._set_backlight(self._backlight_level)
        self.clear()
        self.show()

    def clear(self) -> None:
        self._draw.rectangle((0, 0, self.width, self.height), fill=self.bg_color)

    def _frame_image(self) -> Image.Image:
        logical = self._canvas
        if self._contrast_level < 255:
            logical = logical.point(lambda channel: (channel * self._contrast_level) // 255)

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

    def _pack_frame(self, image: Image.Image) -> bytes:
        def _pack_padded_rows(row_data: bytes, row_bytes: int) -> bytes:
            if self._stride == row_bytes:
                return row_data
            out = bytearray(self._stride * self.physical_height)
            for y in range(self.physical_height):
                source = y * row_bytes
                target = y * self._stride
                out[target : target + row_bytes] = row_data[source : source + row_bytes]
            return bytes(out)

        def _raw_bytes(raw_mode: str) -> bytes | None:
            try:
                return image.tobytes("raw", raw_mode)
            except TypeError:
                return None

        if self.pixel_format == "rgb565":
            if np is not None:
                rgb = np.asarray(image, dtype=np.uint8)
                packed = (
                    ((rgb[:, :, 0].astype(np.uint16) & 0xF8) << 8)
                    | ((rgb[:, :, 1].astype(np.uint16) & 0xFC) << 3)
                    | (rgb[:, :, 2].astype(np.uint16) >> 3)
                ).astype("<u2", copy=False)
                row_bytes = self.physical_width * 2
                if self._stride == row_bytes:
                    return packed.tobytes()
                out = bytearray(self._stride * self.physical_height)
                packed_rows = packed.tobytes()
                for y in range(self.physical_height):
                    source = y * row_bytes
                    target = y * self._stride
                    out[target : target + row_bytes] = packed_rows[source : source + row_bytes]
                return bytes(out)

            data = image.tobytes()
            out = bytearray(self._stride * self.physical_height)
            source_index = 0
            for y in range(self.physical_height):
                row_index = y * self._stride
                for x in range(self.physical_width):
                    r = data[source_index]
                    g = data[source_index + 1]
                    b = data[source_index + 2]
                    source_index += 3
                    rgb565 = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
                    target = row_index + (x * 2)
                    out[target] = rgb565 & 0xFF
                    out[target + 1] = (rgb565 >> 8) & 0xFF
            return bytes(out)

        if self.pixel_format in {"bgrx8888", "bgra8888"}:
            packed = _raw_bytes("BGRX")
            if packed is not None:
                return _pack_padded_rows(packed, self.physical_width * 4)
            data = image.tobytes()
            out = bytearray(self._stride * self.physical_height)
            source_index = 0
            for y in range(self.physical_height):
                row_index = y * self._stride
                for x in range(self.physical_width):
                    r = data[source_index]
                    g = data[source_index + 1]
                    b = data[source_index + 2]
                    source_index += 3
                    target = row_index + (x * 4)
                    out[target : target + 4] = bytes((b, g, r, 0))
            return bytes(out)

        if self.pixel_format == "xrgb8888":
            packed = _raw_bytes("XRGB")
            if packed is not None:
                return _pack_padded_rows(packed, self.physical_width * 4)
            data = image.tobytes()
            out = bytearray(self._stride * self.physical_height)
            source_index = 0
            for y in range(self.physical_height):
                row_index = y * self._stride
                for x in range(self.physical_width):
                    r = data[source_index]
                    g = data[source_index + 1]
                    b = data[source_index + 2]
                    source_index += 3
                    target = row_index + (x * 4)
                    out[target : target + 4] = bytes((0, r, g, b))
            return bytes(out)

        if self.pixel_format in {"rgbx8888", "rgba8888"}:
            packed = _raw_bytes("RGBX")
            if packed is not None:
                return _pack_padded_rows(packed, self.physical_width * 4)
            data = image.tobytes()
            out = bytearray(self._stride * self.physical_height)
            source_index = 0
            for y in range(self.physical_height):
                row_index = y * self._stride
                for x in range(self.physical_width):
                    target = row_index + (x * 4)
                    out[target : target + 3] = data[source_index : source_index + 3]
                    out[target + 3] = 0
                    source_index += 3
            return bytes(out)

        if self.pixel_format == "rgb888":
            data = image.tobytes()
            return _pack_padded_rows(data, self.physical_width * 3)

        raise ValueError(f"Unsupported DSI framebuffer pixel format: {self.pixel_format}")

    def show(self) -> None:
        if self.is_sleeping or self._fb_map is None:
            return
        frame = self._pack_frame(self._frame_image())
        self._fb_map.seek(0)
        self._fb_map.write(frame)

    def set_contrast(self, value: int) -> None:
        contrast = max(0, min(255, int(value)))
        self._contrast_level = contrast
        self._set_backlight(contrast / 255.0)

    def sleep(self) -> None:
        if self.is_sleeping:
            return
        self.is_sleeping = True
        self._apply_backlight(0.0)

    def wake(self) -> None:
        if self.is_sleeping:
            self.is_sleeping = False
            self._set_backlight(self._backlight_level)
            self.show()

    def pixel(self, x: int, y: int, on: bool = True) -> None:
        if not (0 <= x < self.width and 0 <= y < self.height):
            return
        self._draw.point((x, y), fill=self.fg_color if on else self.bg_color)

    def hline(self, x: int, y: int, w: int, on: bool = True) -> None:
        if w <= 0:
            return
        self._draw.line((x, y, x + w - 1, y), fill=self.fg_color if on else self.bg_color)

    def vline(self, x: int, y: int, h: int, on: bool = True) -> None:
        if h <= 0:
            return
        self._draw.line((x, y, x, y + h - 1), fill=self.fg_color if on else self.bg_color)

    def rect(self, x: int, y: int, w: int, h: int, on: bool = True, fill: bool = False) -> None:
        if w <= 0 or h <= 0:
            return
        color = self.fg_color if on else self.bg_color
        if fill:
            self._draw.rectangle((x, y, x + w - 1, y + h - 1), outline=color, fill=color)
            return
        self._draw.rectangle((x, y, x + w - 1, y + h - 1), outline=color, fill=None)

    def fill_rect_level(self, x: int, y: int, w: int, h: int, level: int) -> None:
        if w <= 0 or h <= 0:
            return
        level = max(0, min(255, int(level)))
        fill = tuple(
            int(self.bg_color[idx] + ((self.fg_color[idx] - self.bg_color[idx]) * (level / 255.0)))
            for idx in range(3)
        )
        self._draw.rectangle((x, y, x + w - 1, y + h - 1), outline=fill, fill=fill)

    def _normalize_color(self, color: tuple[int, int, int]) -> tuple[int, int, int]:
        return tuple(max(0, min(255, int(channel))) for channel in color[:3])

    def fill_rect_color(self, x: int, y: int, w: int, h: int, color: tuple[int, int, int]) -> None:
        if w <= 0 or h <= 0:
            return
        fill = self._normalize_color(color)
        self._draw.rectangle((x, y, x + w - 1, y + h - 1), outline=fill, fill=fill)

    def rect_color(self, x: int, y: int, w: int, h: int, color: tuple[int, int, int], fill: bool = False) -> None:
        if w <= 0 or h <= 0:
            return
        outline = self._normalize_color(color)
        self._draw.rectangle((x, y, x + w - 1, y + h - 1), outline=outline, fill=outline if fill else None)

    def rounded_rect_color(
        self,
        x: int,
        y: int,
        w: int,
        h: int,
        radius: int,
        color: tuple[int, int, int],
        fill: bool = False,
    ) -> None:
        if w <= 0 or h <= 0:
            return
        outline = self._normalize_color(color)
        self._draw.rounded_rectangle(
            (x, y, x + w - 1, y + h - 1),
            radius=max(0, int(radius)),
            outline=outline,
            fill=outline if fill else None,
        )

    def hline_color(self, x: int, y: int, w: int, color: tuple[int, int, int]) -> None:
        if w <= 0:
            return
        self._draw.line((x, y, x + w - 1, y), fill=self._normalize_color(color))

    def vline_color(self, x: int, y: int, h: int, color: tuple[int, int, int]) -> None:
        if h <= 0:
            return
        self._draw.line((x, y, x, y + h - 1), fill=self._normalize_color(color))

    def text_color(self, s: str, x: int, y: int, color: tuple[int, int, int], scale: int = 1, weight: str = "regular") -> None:
        mask = render_text_mask(str(s), scale, weight)
        if self.text_scale_factor != 1.0 and mask.size != (0, 0):
            mask = mask.resize(
                (
                    max(1, int(round(mask.width * self.text_scale_factor))),
                    max(1, int(round(mask.height * self.text_scale_factor))),
                ),
                Image.Resampling.LANCZOS,
            )
        self._canvas.paste(self._normalize_color(color), (x, y, x + mask.width, y + mask.height), mask)

    def text_line_color(self, s: str, x: int, y: int, color: tuple[int, int, int], scale: int = 1, weight: str = "regular") -> None:
        mask = render_text_line_mask(str(s), scale, weight)
        if self.text_scale_factor != 1.0 and mask.size != (0, 0):
            mask = mask.resize(
                (
                    max(1, int(round(mask.width * self.text_scale_factor))),
                    max(1, int(round(mask.height * self.text_scale_factor))),
                ),
                Image.Resampling.LANCZOS,
            )
        self._canvas.paste(self._normalize_color(color), (x, y, x + mask.width, y + mask.height), mask)

    def text(self, s: str, x: int, y: int, on: bool = True) -> None:
        self.text_with_style(s, x, y, 1, "regular", on=on)

    def text_scaled(self, s: str, x: int, y: int, scale: int = 1, on: bool = True) -> None:
        self.text_with_style(s, x, y, scale, "regular", on=on)

    def text_with_style(self, s: str, x: int, y: int, scale: int = 1, weight: str = "regular", on: bool = True) -> None:
        mask = render_text_mask(str(s), scale, weight)
        if self.text_scale_factor != 1.0 and mask.size != (0, 0):
            mask = mask.resize(
                (
                    max(1, int(round(mask.width * self.text_scale_factor))),
                    max(1, int(round(mask.height * self.text_scale_factor))),
                ),
                Image.Resampling.LANCZOS,
            )
        color = self.fg_color if on else self.bg_color
        self._canvas.paste(color, (x, y, x + mask.width, y + mask.height), mask)

    def measure_text(self, s: str, scale: int = 1, weight: str = "regular") -> tuple[int, int]:
        width, height = measure_text(str(s), scale, weight)
        if self.text_scale_factor != 1.0:
            width = max(0, int(round(width * self.text_scale_factor)))
            height = max(0, int(round(height * self.text_scale_factor)))
        return width, height

    def line_height(self, scale: int = 1, weight: str = "regular") -> int:
        height = line_height(scale, weight)
        if self.text_scale_factor != 1.0:
            height = max(1, int(round(height * self.text_scale_factor)))
        return height

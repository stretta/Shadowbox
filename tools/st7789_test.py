#!/usr/bin/env python3

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

try:
    from PIL import Image
except ImportError as exc:  # pragma: no cover - local hardware tool
    raise RuntimeError("Pillow is required for tools/st7789_test.py") from exc


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from shadowbox.display import load_display_from_env


def _env_text(name: str, default: str) -> str:
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    return value


def _print_config() -> None:
    print("ST7789 test configuration")
    print("========================")
    for name, default in (
        ("SHADOWBOX_DISPLAY", "st7789"),
        ("SHADOWBOX_ST7789_SPI_BUS", "0"),
        ("SHADOWBOX_ST7789_SPI_CS", "0"),
        ("SHADOWBOX_ST7789_DC", "9"),
        ("SHADOWBOX_ST7789_RST", "13"),
        ("SHADOWBOX_ST7789_BACKLIGHT", "19"),
        ("SHADOWBOX_ST7789_ROTATION", "90"),
        ("SHADOWBOX_ST7789_WIDTH", "320"),
        ("SHADOWBOX_ST7789_HEIGHT", "240"),
        ("SHADOWBOX_ST7789_OFFSET_LEFT", "0"),
        ("SHADOWBOX_ST7789_OFFSET_TOP", "0"),
        ("SHADOWBOX_LOGICAL_WIDTH", "320"),
        ("SHADOWBOX_LOGICAL_HEIGHT", "240"),
    ):
        print(f"{name}={_env_text(name, default)}")
    print("")


def _sleep(label: str, seconds: float) -> None:
    print(f"Showing {label} for {seconds:.1f}s")
    time.sleep(seconds)


def _show_solid(display, label: str, rgb: tuple[int, int, int], seconds: float) -> None:
    image = Image.new("RGB", (display.physical_width, display.physical_height), rgb)
    display._device.display(image)
    _sleep(label, seconds)


def _show_backend_pattern(display, seconds: float) -> None:
    print("Drawing backend pattern")
    display.clear()

    step_x = max(8, display.width // 8)
    step_y = max(8, display.height // 8)
    for x in range(0, display.width, step_x):
        display.vline(x, 0, display.height, True)
    for y in range(0, display.height, step_y):
        display.hline(0, y, display.width, True)

    display.rect(0, 0, display.width, display.height, True, False)
    display.rect(8, 8, max(1, display.width - 16), max(1, display.height - 16), True, False)
    display.text("ST7789", 16, 16, True)
    display.text("SPI TEST", 16, 40, True)
    display.text(f"{display.width}x{display.height}", 16, 64, True)
    display.show()
    _sleep("backend pattern", seconds)


def _show_quadrants(display, seconds: float) -> None:
    print("Drawing quadrant fill")
    display.clear()
    half_w = display.width // 2
    half_h = display.height // 2
    display.rect(0, 0, half_w, half_h, True, True)
    display.rect(half_w, half_h, display.width - half_w, display.height - half_h, True, True)
    display.show()
    _sleep("quadrant fill", seconds)


def main() -> None:
    _print_config()
    display = load_display_from_env(default_kind="st7789")
    display.init()

    if not hasattr(display, "_device") or not hasattr(display, "physical_width"):
        raise RuntimeError("tools/st7789_test.py requires SHADOWBOX_DISPLAY=st7789")

    print("Display initialized")
    _show_solid(display, "solid black", (0, 0, 0), 1.5)
    _show_solid(display, "solid white", (255, 255, 255), 1.5)
    _show_solid(display, "solid red", (255, 0, 0), 1.5)
    _show_solid(display, "solid green", (0, 255, 0), 1.5)
    _show_solid(display, "solid blue", (0, 0, 255), 1.5)
    _show_backend_pattern(display, 3.0)
    _show_quadrants(display, 3.0)

    print("Clearing display")
    display.clear()
    display.show()
    print("Done")


if __name__ == "__main__":
    main()

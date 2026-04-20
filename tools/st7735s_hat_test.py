#!/usr/bin/env python3

from __future__ import annotations

import os
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from shadowbox.display import load_display_from_env


def _env_text(name: str, default: str) -> str:
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    return value


def _print_config() -> None:
    print("ST7735S hat test configuration")
    print("==============================")
    for name, default in (
        ("SHADOWBOX_DISPLAY", "st7735s_hat"),
        ("SHADOWBOX_ST7735_SPI_BUS", "0"),
        ("SHADOWBOX_ST7735_SPI_CS", "0"),
        ("SHADOWBOX_ST7735_DC", "25"),
        ("SHADOWBOX_ST7735_RST", "27"),
        ("SHADOWBOX_ST7735_BACKLIGHT", "24"),
        ("SHADOWBOX_ST7735_SPI_SPEED_HZ", "20000000"),
        ("SHADOWBOX_ST7735_WIDTH", "128"),
        ("SHADOWBOX_ST7735_HEIGHT", "128"),
        ("SHADOWBOX_ST7735_OFFSET_LEFT", "2"),
        ("SHADOWBOX_ST7735_OFFSET_TOP", "3"),
        ("SHADOWBOX_ST7735_INVERT", "true"),
        ("SHADOWBOX_LOGICAL_WIDTH", "128"),
        ("SHADOWBOX_LOGICAL_HEIGHT", "128"),
    ):
        print(f"{name}={_env_text(name, default)}")
    print("")


def _pause(label: str, seconds: float) -> None:
    print(f"Showing {label} for {seconds:.1f}s")
    time.sleep(seconds)


def _show_text_pattern(display, seconds: float) -> None:
    display.clear()
    display.rect(0, 0, display.width, display.height, True, False)
    display.rect(8, 8, display.width - 16, display.height - 16, True, False)
    display.text("SHADOWBOX", 12, 16, True)
    display.text("ST7735S HAT", 12, 32, True)
    display.text(f"{display.width}x{display.height}", 12, 48, True)

    for x in range(0, display.width, 16):
        display.vline(x, 64, display.height - 64, True)
    for y in range(64, display.height, 16):
        display.hline(0, y, display.width, True)

    display.show()
    _pause("text/grid pattern", seconds)


def _show_fill_pattern(display, seconds: float) -> None:
    display.clear()
    half_w = display.width // 2
    half_h = display.height // 2
    display.rect(0, 0, half_w, half_h, True, True)
    display.rect(half_w, 0, display.width - half_w, half_h, False, True)
    display.rect(0, half_h, half_w, display.height - half_h, True, False)
    display.rect(half_w, half_h, display.width - half_w, display.height - half_h, True, True)
    display.show()
    _pause("quadrant pattern", seconds)


def main() -> None:
    _print_config()
    display = load_display_from_env(default_kind="st7735s_hat")
    display.init()

    if display.__class__.__name__ != "ST7735SHatDisplay":
        raise RuntimeError("tools/st7735s_hat_test.py requires SHADOWBOX_DISPLAY=st7735s_hat")

    print("Display initialized")
    _show_text_pattern(display, 3.0)
    _show_fill_pattern(display, 3.0)
    display.clear()
    display.show()
    print("Done")


if __name__ == "__main__":
    main()

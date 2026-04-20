from __future__ import annotations

import os

from shadowbox.display.ssd1306 import SSD1306Display
from shadowbox.display.ssd1309 import SSD1309Display


def _env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    return int(value, 0)


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def load_display_from_env(default_kind: str = "st7789_raw"):
    kind = os.environ.get("SHADOWBOX_DISPLAY", default_kind).strip().lower()
    kwargs = {}

    if kind in {"ssd1306", "ssd1309"}:
        kwargs["bus"] = _env_int("SHADOWBOX_I2C_BUS", 1)
        kwargs["addr"] = _env_int("SHADOWBOX_I2C_ADDR", 0x3C)
    elif kind == "st7789":
        kwargs.update(
            bus=_env_int("SHADOWBOX_ST7789_SPI_BUS", 0),
            cs=_env_int("SHADOWBOX_ST7789_SPI_CS", 0),
            dc=_env_int("SHADOWBOX_ST7789_DC", 9),
            rst=None if os.environ.get("SHADOWBOX_ST7789_RST", "13").strip().lower() == "none" else _env_int("SHADOWBOX_ST7789_RST", 13),
            backlight=None if os.environ.get("SHADOWBOX_ST7789_BACKLIGHT", "19").strip().lower() == "none" else _env_int("SHADOWBOX_ST7789_BACKLIGHT", 19),
            spi_speed_hz=_env_int("SHADOWBOX_ST7789_SPI_SPEED_HZ", 80_000_000),
            rotation=_env_int("SHADOWBOX_ST7789_ROTATION", 90),
            physical_width=_env_int("SHADOWBOX_ST7789_WIDTH", 320),
            physical_height=_env_int("SHADOWBOX_ST7789_HEIGHT", 240),
            offset_left=_env_int("SHADOWBOX_ST7789_OFFSET_LEFT", 0),
            offset_top=_env_int("SHADOWBOX_ST7789_OFFSET_TOP", 0),
            logical_width=_env_int("SHADOWBOX_LOGICAL_WIDTH", 320),
            logical_height=_env_int("SHADOWBOX_LOGICAL_HEIGHT", 240),
        )
    elif kind == "st7789_raw":
        kwargs.update(
            bus=_env_int("SHADOWBOX_ST7789_SPI_BUS", 0),
            cs=_env_int("SHADOWBOX_ST7789_SPI_CS", 0),
            dc=_env_int("SHADOWBOX_ST7789_DC", 25),
            rst=None if os.environ.get("SHADOWBOX_ST7789_RST", "24").strip().lower() == "none" else _env_int("SHADOWBOX_ST7789_RST", 24),
            backlight=None if os.environ.get("SHADOWBOX_ST7789_BACKLIGHT", "18").strip().lower() == "none" else _env_int("SHADOWBOX_ST7789_BACKLIGHT", 18),
            spi_speed_hz=_env_int("SHADOWBOX_ST7789_SPI_SPEED_HZ", 40_000_000),
            rotation=_env_int("SHADOWBOX_ST7789_ROTATION", 0),
            physical_width=_env_int("SHADOWBOX_ST7789_WIDTH", 320),
            physical_height=_env_int("SHADOWBOX_ST7789_HEIGHT", 240),
            offset_left=_env_int("SHADOWBOX_ST7789_OFFSET_LEFT", 0),
            offset_top=_env_int("SHADOWBOX_ST7789_OFFSET_TOP", 0),
            logical_width=_env_int("SHADOWBOX_LOGICAL_WIDTH", 320),
            logical_height=_env_int("SHADOWBOX_LOGICAL_HEIGHT", 240),
            invert_colors=_env_bool("SHADOWBOX_ST7789_INVERT", False),
        )
    elif kind == "st7735s_hat":
        kwargs.update(
            bus=_env_int("SHADOWBOX_ST7735_SPI_BUS", 0),
            cs=_env_int("SHADOWBOX_ST7735_SPI_CS", 0),
            dc=_env_int("SHADOWBOX_ST7735_DC", 25),
            rst=None if os.environ.get("SHADOWBOX_ST7735_RST", "27").strip().lower() == "none" else _env_int("SHADOWBOX_ST7735_RST", 27),
            backlight=None
            if os.environ.get("SHADOWBOX_ST7735_BACKLIGHT", "24").strip().lower() == "none"
            else _env_int("SHADOWBOX_ST7735_BACKLIGHT", 24),
            spi_speed_hz=_env_int("SHADOWBOX_ST7735_SPI_SPEED_HZ", 20_000_000),
            physical_width=_env_int("SHADOWBOX_ST7735_WIDTH", 128),
            physical_height=_env_int("SHADOWBOX_ST7735_HEIGHT", 128),
            offset_left=_env_int("SHADOWBOX_ST7735_OFFSET_LEFT", 2),
            offset_top=_env_int("SHADOWBOX_ST7735_OFFSET_TOP", 3),
            logical_width=_env_int("SHADOWBOX_LOGICAL_WIDTH", 128),
            logical_height=_env_int("SHADOWBOX_LOGICAL_HEIGHT", 128),
            invert_colors=_env_bool("SHADOWBOX_ST7735_INVERT", True),
        )
    elif kind == "waveshare_2inch":
        kwargs.update(
            spi_bus=_env_int("SHADOWBOX_WAVESHARE_SPI_BUS", 0),
            spi_cs=_env_int("SHADOWBOX_WAVESHARE_SPI_CS", 0),
            spi_speed_hz=_env_int("SHADOWBOX_WAVESHARE_SPI_SPEED_HZ", 40_000_000),
            dc=_env_int("SHADOWBOX_WAVESHARE_DC", 25),
            rst=_env_int("SHADOWBOX_WAVESHARE_RST", 27),
            backlight=None if os.environ.get("SHADOWBOX_WAVESHARE_BACKLIGHT", "18").strip().lower() == "none" else _env_int("SHADOWBOX_WAVESHARE_BACKLIGHT", 18),
            logical_width=_env_int("SHADOWBOX_LOGICAL_WIDTH", 320),
            logical_height=_env_int("SHADOWBOX_LOGICAL_HEIGHT", 240),
        )

    return create_display(kind, **kwargs)


def create_display(kind: str = "ssd1306", **kwargs):
    if kind == "ssd1306":
        return SSD1306Display(**kwargs)
    if kind == "ssd1309":
        return SSD1309Display(**kwargs)
    if kind == "st7789":
        from shadowbox.display.st7789 import ST7789Display

        return ST7789Display(**kwargs)
    if kind == "st7789_raw":
        from shadowbox.display.st7789_raw import ST7789RawDisplay

        return ST7789RawDisplay(**kwargs)
    if kind == "st7735s_hat":
        from shadowbox.display.st7735s_hat import ST7735SHatDisplay

        return ST7735SHatDisplay(**kwargs)
    if kind == "waveshare_2inch":
        from shadowbox.display.waveshare_2inch import Waveshare2InchDisplay

        return Waveshare2InchDisplay(**kwargs)
    raise ValueError(f"Unknown display backend: {kind}")


__all__ = ["SSD1306Display", "SSD1309Display", "create_display", "load_display_from_env"]

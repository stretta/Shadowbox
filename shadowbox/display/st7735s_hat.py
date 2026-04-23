#!/usr/bin/env python3
"""
Raw ST7735S SPI TFT backend for the Waveshare 1.44-inch LCD HAT.
"""

from __future__ import annotations

import time

from shadowbox.display.st7789_raw import ST7789RawDisplay


class ST7735SHatDisplay(ST7789RawDisplay):
    def __init__(
        self,
        *,
        bus: int = 0,
        cs: int = 0,
        dc: int = 25,
        rst: int | None = 27,
        backlight: int | None = 24,
        spi_speed_hz: int = 20_000_000,
        physical_width: int = 128,
        physical_height: int = 128,
        offset_left: int = 2,
        offset_top: int = 3,
        logical_width: int = 128,
        logical_height: int = 128,
        invert_colors: bool = True,
    ):
        # This panel's controller/orientation pairing was calibrated on hardware.
        # Quarter-turn runtime rotation values were misleading on the Waveshare
        # 1.44-inch HAT, so we keep the framebuffer unrotated and use the
        # empirically correct MADCTL value below instead of exposing rotation.
        super().__init__(
            bus=bus,
            cs=cs,
            dc=dc,
            rst=rst,
            backlight=backlight,
            spi_speed_hz=spi_speed_hz,
            rotation=0,
            physical_width=physical_width,
            physical_height=physical_height,
            offset_left=offset_left,
            offset_top=offset_top,
            logical_width=logical_width,
            logical_height=logical_height,
            invert_colors=invert_colors,
        )

    def _madctl(self) -> int:
        return 0x68

    def _initialize_panel(self) -> None:
        self._hardware_reset()
        self._command(0x01)
        time.sleep(0.15)
        self._command(0x11)
        time.sleep(0.15)

        init_sequence = [
            (0xB1, b"\x01\x2C\x2D"),
            (0xB2, b"\x01\x2C\x2D"),
            (0xB3, b"\x01\x2C\x2D\x01\x2C\x2D"),
            (0xB4, b"\x07"),
            (0xC0, b"\xA2\x02\x84"),
            (0xC1, b"\xC5"),
            (0xC2, b"\x0A\x00"),
            (0xC3, b"\x8A\x2A"),
            (0xC4, b"\x8A\xEE"),
            (0xC5, b"\x0E"),
            (0x36, bytes([self._madctl()])),
            (0x3A, b"\x05"),
            (0x21 if self.invert_colors else 0x20, None),
            (0x13, None),
            (0x29, None),
        ]

        for command, data in init_sequence:
            self._command(command, data)

        time.sleep(0.05)

    def init(self) -> None:
        self._initialize_panel()
        self.is_sleeping = False
        self._set_backlight(self._backlight_level)
        self.clear()
        self.show()

#!/usr/bin/env python3
"""
SSD1309 128x64 I2C display backend.
"""

from __future__ import annotations

from shadowbox.display.mono_i2c import MonoI2CDisplay


class SSD1309Display(MonoI2CDisplay):
    def __init__(self, bus: int = 1, addr: int = 0x3C):
        super().__init__(width=128, height=64, bus=bus, addr=addr)

    def init(self) -> None:
        self._cmd(
            0xAE,             # display off
            0x20, 0x00,       # horizontal addressing mode
            0xB0,             # page start
            0xC8,             # COM scan direction remapped
            0x00, 0x10,       # low/high column start
            0x40,             # start line = 0
            0x81, 0x7F,       # contrast
            0xA1,             # segment remap
            0xA6,             # normal display
            0xA8, 0x3F,       # multiplex ratio = 64
            0xA4,             # display follows RAM
            0xD3, 0x00,       # display offset
            0xD5, 0x80,       # display clock divide
            0xD9, 0x22,       # pre-charge
            0xDA, 0x12,       # COM pins for 128x64
            0xDB, 0x34,       # VCOM detect
            0xAD, 0x8A,       # DC-DC control / internal regulator on
            0xAF,             # display on
        )
        self.is_sleeping = False
        self.clear()
        self.show()

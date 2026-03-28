#!/usr/bin/env python3

from __future__ import annotations

import os
import time

import spidev


def _env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    return int(value, 0)


def _env_optional_int(name: str, default: int | None) -> int | None:
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    if value.strip().lower() == "none":
        return None
    return int(value, 0)


SPI_BUS = _env_int("SHADOWBOX_ST7789_SPI_BUS", 0)
SPI_CS = _env_int("SHADOWBOX_ST7789_SPI_CS", 0)
DC_PIN = _env_int("SHADOWBOX_ST7789_DC", 25)
RST_PIN = _env_optional_int("SHADOWBOX_ST7789_RST", 24)
BACKLIGHT_PIN = _env_optional_int("SHADOWBOX_ST7789_BACKLIGHT", 18)
SPI_SPEED_HZ = _env_int("SHADOWBOX_ST7789_SPI_SPEED_HZ", 40_000_000)
WIDTH = _env_int("SHADOWBOX_ST7789_WIDTH", 320)
HEIGHT = _env_int("SHADOWBOX_ST7789_HEIGHT", 240)


class GPIOPin:
    def __init__(self, bcm_pin: int):
        self.pin = bcm_pin
        self._backend = None
        self._line_request = None

        try:
            import gpiod

            self._backend = "gpiod"
            self._value_enum = gpiod.line.Value
            settings = gpiod.LineSettings(direction=gpiod.line.Direction.OUTPUT, output_value=self._value_enum.INACTIVE)
            self._chip = gpiod.Chip("/dev/gpiochip4")
            self._line_request = self._chip.request_lines(
                consumer=f"st7789-raw-test-{bcm_pin}",
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
            return


class ST7789Raw:
    def __init__(self):
        self.spi = spidev.SpiDev()
        self.spi.open(SPI_BUS, SPI_CS)
        self.spi.max_speed_hz = SPI_SPEED_HZ
        self.spi.mode = 0
        self.spi.no_cs = False

        self.dc = GPIOPin(DC_PIN)
        self.rst = GPIOPin(RST_PIN) if RST_PIN is not None else None
        self.backlight = GPIOPin(BACKLIGHT_PIN) if BACKLIGHT_PIN is not None else None

        if self.backlight is not None:
            self.backlight.write(True)

    def close(self) -> None:
        try:
            self.spi.close()
        finally:
            self.dc.close()
            if self.rst is not None:
                self.rst.close()
            if self.backlight is not None:
                self.backlight.close()

    def command(self, cmd: int, data: bytes | bytearray | None = None) -> None:
        self.dc.write(False)
        self.spi.xfer2([cmd & 0xFF])
        if data:
            self.data(data)

    def data(self, data: bytes | bytearray) -> None:
        self.dc.write(True)
        chunk = 4096
        for i in range(0, len(data), chunk):
            self.spi.xfer3(list(data[i : i + chunk]))

    def hardware_reset(self) -> None:
        if self.rst is None:
            return
        self.rst.write(True)
        time.sleep(0.05)
        self.rst.write(False)
        time.sleep(0.05)
        self.rst.write(True)
        time.sleep(0.12)

    def set_window(self, x0: int, y0: int, x1: int, y1: int) -> None:
        self.command(0x2A, bytes([(x0 >> 8) & 0xFF, x0 & 0xFF, (x1 >> 8) & 0xFF, x1 & 0xFF]))
        self.command(0x2B, bytes([(y0 >> 8) & 0xFF, y0 & 0xFF, (y1 >> 8) & 0xFF, y1 & 0xFF]))
        self.command(0x2C)

    def fill_rgb565(self, color: int) -> None:
        hi = (color >> 8) & 0xFF
        lo = color & 0xFF
        row = bytes([hi, lo]) * WIDTH
        self.set_window(0, 0, WIDTH - 1, HEIGHT - 1)
        for _ in range(HEIGHT):
            self.data(row)

    def init_variant_a(self) -> None:
        self.hardware_reset()
        self.command(0x01)
        time.sleep(0.15)
        self.command(0x11)
        time.sleep(0.12)
        self.command(0x3A, b"\x55")
        self.command(0x36, b"\x00")
        self.command(0x21)
        self.command(0x13)
        self.command(0x29)
        time.sleep(0.05)

    def init_variant_b(self) -> None:
        self.hardware_reset()
        self.command(0x01)
        time.sleep(0.15)
        self.command(0x11)
        time.sleep(0.12)
        self.command(0x3A, b"\x55")
        self.command(0x36, b"\x70")
        self.command(0xB2, b"\x0C\x0C\x00\x33\x33")
        self.command(0xB7, b"\x35")
        self.command(0xBB, b"\x19")
        self.command(0xC0, b"\x2C")
        self.command(0xC2, b"\x01")
        self.command(0xC3, b"\x12")
        self.command(0xC4, b"\x20")
        self.command(0xC6, b"\x0F")
        self.command(0xD0, b"\xA4\xA1")
        self.command(0x21)
        self.command(0x29)
        time.sleep(0.05)


def _show(label: str, fn) -> None:
    print(label)
    fn()
    time.sleep(1.5)


def main() -> None:
    print("ST7789 raw SPI test")
    print("===================")
    print(f"SPI bus/cs: {SPI_BUS}.{SPI_CS}")
    print(f"DC GPIO: {DC_PIN}")
    print(f"RST GPIO: {RST_PIN}")
    print(f"BACKLIGHT GPIO: {BACKLIGHT_PIN}")
    print(f"Resolution: {WIDTH}x{HEIGHT}")
    print("")

    panel = ST7789Raw()
    try:
        print("Trying init variant A")
        panel.init_variant_a()
        _show("A: black", lambda: panel.fill_rgb565(0x0000))
        _show("A: white", lambda: panel.fill_rgb565(0xFFFF))
        _show("A: red", lambda: panel.fill_rgb565(0xF800))
        _show("A: green", lambda: panel.fill_rgb565(0x07E0))
        _show("A: blue", lambda: panel.fill_rgb565(0x001F))

        print("Trying init variant B")
        panel.init_variant_b()
        _show("B: black", lambda: panel.fill_rgb565(0x0000))
        _show("B: white", lambda: panel.fill_rgb565(0xFFFF))
        _show("B: red", lambda: panel.fill_rgb565(0xF800))
        _show("B: green", lambda: panel.fill_rgb565(0x07E0))
        _show("B: blue", lambda: panel.fill_rgb565(0x001F))
    finally:
        panel.close()


if __name__ == "__main__":
    main()

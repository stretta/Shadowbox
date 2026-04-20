import importlib
import os
import sys
import types
import unittest
from unittest import mock


class _FakeDisplay:
    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs


class DisplayDefaultsTests(unittest.TestCase):
    def setUp(self) -> None:
        self._saved_modules = {}
        for name in (
            "shadowbox.display",
            "shadowbox.display.ssd1306",
            "shadowbox.display.ssd1309",
            "shadowbox.display.st7789_raw",
            "shadowbox.display.st7735s_hat",
        ):
            self._saved_modules[name] = sys.modules.get(name)
            sys.modules.pop(name, None)

        ssd1306_module = types.ModuleType("shadowbox.display.ssd1306")
        ssd1306_module.SSD1306Display = _FakeDisplay
        sys.modules["shadowbox.display.ssd1306"] = ssd1306_module

        ssd1309_module = types.ModuleType("shadowbox.display.ssd1309")
        ssd1309_module.SSD1309Display = _FakeDisplay
        sys.modules["shadowbox.display.ssd1309"] = ssd1309_module

        st7789_raw_module = types.ModuleType("shadowbox.display.st7789_raw")
        st7789_raw_module.ST7789RawDisplay = _FakeDisplay
        sys.modules["shadowbox.display.st7789_raw"] = st7789_raw_module

        st7735s_hat_module = types.ModuleType("shadowbox.display.st7735s_hat")
        st7735s_hat_module.ST7735SHatDisplay = _FakeDisplay
        sys.modules["shadowbox.display.st7735s_hat"] = st7735s_hat_module

        self.display_module = importlib.import_module("shadowbox.display")

    def tearDown(self) -> None:
        for name in (
            "shadowbox.display",
            "shadowbox.display.ssd1306",
            "shadowbox.display.ssd1309",
            "shadowbox.display.st7789_raw",
            "shadowbox.display.st7735s_hat",
        ):
            sys.modules.pop(name, None)

        for name, module in self._saved_modules.items():
            if module is not None:
                sys.modules[name] = module

    def test_default_display_profile_matches_st7789_raw_hardware(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            display = self.display_module.load_display_from_env()

        self.assertEqual(type(display).__name__, "_FakeDisplay")
        self.assertEqual(
            display.kwargs,
            {
                "bus": 0,
                "cs": 0,
                "dc": 25,
                "rst": 24,
                "backlight": 18,
                "spi_speed_hz": 40_000_000,
                "rotation": 0,
                "physical_width": 320,
                "physical_height": 240,
                "offset_left": 0,
                "offset_top": 0,
                "logical_width": 320,
                "logical_height": 240,
                "invert_colors": False,
            },
        )

    def test_st7735s_hat_profile_matches_waveshare_144_hat_defaults(self) -> None:
        with mock.patch.dict(os.environ, {"SHADOWBOX_DISPLAY": "st7735s_hat"}, clear=True):
            display = self.display_module.load_display_from_env()

        self.assertEqual(type(display).__name__, "_FakeDisplay")
        self.assertEqual(
            display.kwargs,
            {
                "bus": 0,
                "cs": 0,
                "dc": 25,
                "rst": 27,
                "backlight": 24,
                "spi_speed_hz": 20_000_000,
                "physical_width": 128,
                "physical_height": 128,
                "offset_left": 2,
                "offset_top": 3,
                "logical_width": 128,
                "logical_height": 128,
                "invert_colors": True,
            },
        )


if __name__ == "__main__":
    unittest.main()

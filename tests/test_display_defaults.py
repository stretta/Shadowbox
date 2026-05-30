import importlib
import importlib.util
import os
from pathlib import Path
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
            "shadowbox.display.waveshare_5inch_dsi",
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

        waveshare_5inch_dsi_module = types.ModuleType("shadowbox.display.waveshare_5inch_dsi")
        waveshare_5inch_dsi_module.Waveshare5InchDSIDisplay = _FakeDisplay
        sys.modules["shadowbox.display.waveshare_5inch_dsi"] = waveshare_5inch_dsi_module

        self.display_module = importlib.import_module("shadowbox.display")

    def tearDown(self) -> None:
        for name in (
            "shadowbox.display",
            "shadowbox.display.ssd1306",
            "shadowbox.display.ssd1309",
            "shadowbox.display.st7789_raw",
            "shadowbox.display.st7735s_hat",
            "shadowbox.display.waveshare_5inch_dsi",
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

    def test_waveshare_5inch_dsi_profile_matches_panel_defaults(self) -> None:
        with mock.patch.dict(os.environ, {"SHADOWBOX_DISPLAY": "waveshare_5inch_dsi"}, clear=True):
            display = self.display_module.load_display_from_env()

        self.assertEqual(type(display).__name__, "_FakeDisplay")
        self.assertEqual(
            display.kwargs,
            {
                "framebuffer": "/dev/fb0",
                "physical_width": 800,
                "physical_height": 480,
                "logical_width": 800,
                "logical_height": 480,
                "pixel_format": "auto",
                "backlight_path": None,
            },
        )

    def test_waveshare_5inch_dsi_profile_accepts_framebuffer_overrides(self) -> None:
        env = {
            "SHADOWBOX_DISPLAY": "waveshare_5inch_dsi",
            "SHADOWBOX_DSI_FRAMEBUFFER": "/dev/fb1",
            "SHADOWBOX_DSI_WIDTH": "480",
            "SHADOWBOX_DSI_HEIGHT": "800",
            "SHADOWBOX_LOGICAL_WIDTH": "240",
            "SHADOWBOX_LOGICAL_HEIGHT": "320",
            "SHADOWBOX_DSI_PIXEL_FORMAT": "rgb565",
            "SHADOWBOX_DSI_BACKLIGHT_PATH": "/sys/class/backlight/10-0045",
        }
        with mock.patch.dict(os.environ, env, clear=True):
            display = self.display_module.load_display_from_env()

        self.assertEqual(
            display.kwargs,
            {
                "framebuffer": "/dev/fb1",
                "physical_width": 480,
                "physical_height": 800,
                "logical_width": 240,
                "logical_height": 320,
                "pixel_format": "rgb565",
                "backlight_path": "/sys/class/backlight/10-0045",
            },
        )


class DisplayWakeTests(unittest.TestCase):
    @staticmethod
    def _load_display_class(module_name: str, relative_path: str, class_name: str):
        root = Path(__file__).resolve().parents[1]
        module_path = root / relative_path
        spec = importlib.util.spec_from_file_location(module_name, module_path)
        module = importlib.util.module_from_spec(spec)
        assert spec is not None
        assert spec.loader is not None

        shadowbox_module = types.ModuleType("shadowbox")
        display_package = types.ModuleType("shadowbox.display")
        base_module = types.ModuleType("shadowbox.display.base")
        base_module.DisplayBackend = object
        tft_text_module = types.ModuleType("shadowbox.display.tft_text")
        tft_text_module.line_height = lambda scale=1, weight="regular": 8 * scale
        tft_text_module.measure_text = lambda text, scale=1, weight="regular": (len(str(text)) * 6 * scale, 8 * scale)
        tft_text_module.render_text_mask = lambda text, scale=1, weight="regular": types.SimpleNamespace(width=0, height=0)
        tft_text_module.mask_to_rgb = lambda image, fg, bg: image

        pil_module = types.ModuleType("PIL")
        pil_module.Image = types.SimpleNamespace(
            new=lambda *args, **kwargs: None,
            Resampling=types.SimpleNamespace(NEAREST=0),
            Transpose=types.SimpleNamespace(ROTATE_270=0, ROTATE_180=1, ROTATE_90=2),
        )
        pil_module.ImageDraw = types.SimpleNamespace(Draw=lambda image: None)

        stubs = {
            "shadowbox": shadowbox_module,
            "shadowbox.display": display_package,
            "shadowbox.display.base": base_module,
            "shadowbox.display.tft_text": tft_text_module,
            "PIL": pil_module,
            "spidev": types.ModuleType("spidev"),
            "gpiozero": types.SimpleNamespace(PWMOutputDevice=object, DigitalOutputDevice=object),
            "numpy": types.ModuleType("numpy"),
        }

        with mock.patch.dict(sys.modules, stubs, clear=False):
            spec.loader.exec_module(module)
        return getattr(module, class_name)

    def test_st7789_raw_wake_reinitializes_panel_and_replays_framebuffer(self) -> None:
        ST7789RawDisplay = self._load_display_class(
            "shadowbox.display.st7789_raw_testcopy",
            "shadowbox/display/st7789_raw.py",
            "ST7789RawDisplay",
        )
        display = ST7789RawDisplay.__new__(ST7789RawDisplay)
        display.is_sleeping = True
        display._backlight_level = 0.5
        calls: list[object] = []
        display._initialize_panel = lambda: calls.append("init")
        display._set_backlight = lambda level: calls.append(("backlight", level))
        display.show = lambda: calls.append("show")

        display.wake()

        self.assertFalse(display.is_sleeping)
        self.assertEqual(calls, ["init", ("backlight", 0.5), "show"])

    def test_st7789_raw_init_power_cycles_backlight_before_panel_init(self) -> None:
        ST7789RawDisplay = self._load_display_class(
            "shadowbox.display.st7789_raw_testcopy",
            "shadowbox/display/st7789_raw.py",
            "ST7789RawDisplay",
        )
        display = ST7789RawDisplay.__new__(ST7789RawDisplay)
        display._backlight_level = 0.75
        calls: list[object] = []
        display._power_cycle_backlight = lambda: calls.append("power")
        display._initialize_panel = lambda: calls.append("init")
        display._set_backlight = lambda level: calls.append(("backlight", level))
        display.clear = lambda: calls.append("clear")
        display.show = lambda: calls.append("show")

        display.init()

        self.assertFalse(display.is_sleeping)
        self.assertEqual(calls, ["power", "init", ("backlight", 0.75), "clear", "show"])

    def test_waveshare_wake_reinitializes_panel_and_replays_framebuffer(self) -> None:
        Waveshare2InchDisplay = self._load_display_class(
            "shadowbox.display.waveshare_2inch_testcopy",
            "shadowbox/display/waveshare_2inch.py",
            "Waveshare2InchDisplay",
        )
        display = Waveshare2InchDisplay.__new__(Waveshare2InchDisplay)
        display.is_sleeping = True
        display._backlight_level = 0.25
        calls: list[object] = []
        display._initialize_panel = lambda: calls.append("init")
        display.show = lambda: calls.append("show")

        display.wake()

        self.assertFalse(display.is_sleeping)
        self.assertEqual(calls, ["init", "show"])


if __name__ == "__main__":
    unittest.main()

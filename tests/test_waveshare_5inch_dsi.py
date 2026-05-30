import importlib.util
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock


def _load_display_class():
    root = Path(__file__).resolve().parents[1]
    module_path = root / "shadowbox/display/waveshare_5inch_dsi.py"
    spec = importlib.util.spec_from_file_location("shadowbox.display.waveshare_5inch_dsi_testcopy", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None
    assert spec.loader is not None

    class _FakeCanvas:
        size = (1, 1)
        width = 1
        height = 1

        def paste(self, *_args, **_kwargs) -> None:
            pass

    class _FakeDraw:
        def rectangle(self, *_args, **_kwargs) -> None:
            pass

        def point(self, *_args, **_kwargs) -> None:
            pass

        def line(self, *_args, **_kwargs) -> None:
            pass

    pil_module = types.ModuleType("PIL")
    pil_module.Image = types.SimpleNamespace(
        new=lambda *_args, **_kwargs: _FakeCanvas(),
        Resampling=types.SimpleNamespace(NEAREST=0),
    )
    pil_module.ImageDraw = types.SimpleNamespace(Draw=lambda _image: _FakeDraw())

    stubs = {
        "PIL": pil_module,
        "shadowbox.display.base": types.SimpleNamespace(DisplayBackend=object),
        "shadowbox.display.tft_text": types.SimpleNamespace(
            line_height=lambda scale=1, weight="regular": 8 * scale,
            measure_text=lambda text, scale=1, weight="regular": (len(str(text)) * 6 * scale, 8 * scale),
            render_text_line_mask=lambda text, scale=1, weight="regular": types.SimpleNamespace(width=0, height=0, size=(0, 0)),
            render_text_mask=lambda text, scale=1, weight="regular": types.SimpleNamespace(width=0, height=0),
        ),
    }

    with mock.patch.dict(sys.modules, stubs, clear=False):
        spec.loader.exec_module(module)
    return module.Waveshare5InchDSIDisplay


class _ImageBytes:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def tobytes(self, *args) -> bytes:
        if args:
            raise TypeError("raw mode is not available")
        return self._data


class _ImageRawBytes:
    def __init__(self, rgb_data: bytes, raw_data: bytes) -> None:
        self._rgb_data = rgb_data
        self._raw_data = raw_data
        self.raw_calls: list[tuple] = []

    def tobytes(self, *args) -> bytes:
        self.raw_calls.append(tuple(args))
        if args:
            return self._raw_data
        return self._rgb_data


class Waveshare5InchDSITests(unittest.TestCase):
    def setUp(self) -> None:
        self.Display = _load_display_class()

    def test_pack_frame_supports_bgrx8888_framebuffer_order(self) -> None:
        display = self.Display(
            physical_width=2,
            physical_height=1,
            logical_width=2,
            logical_height=1,
            pixel_format="bgrx8888",
        )
        display._stride = 8
        image = _ImageBytes(bytes([255, 0, 0, 0, 255, 0]))

        self.assertEqual(display._pack_frame(image), bytes([0, 0, 255, 0, 0, 255, 0, 0]))

    def test_pack_frame_supports_rgb565_framebuffer_order(self) -> None:
        display = self.Display(
            physical_width=2,
            physical_height=1,
            logical_width=2,
            logical_height=1,
            pixel_format="rgb565",
        )
        display._stride = 4
        image = _ImageBytes(bytes([255, 0, 0, 0, 255, 0]))

        self.assertEqual(display._pack_frame(image), bytes([0x00, 0xF8, 0xE0, 0x07]))

    def test_pack_frame_uses_fast_raw_path_for_bgrx8888(self) -> None:
        display = self.Display(
            physical_width=2,
            physical_height=1,
            logical_width=2,
            logical_height=1,
            pixel_format="bgrx8888",
        )
        display._stride = 8
        image = _ImageRawBytes(
            rgb_data=bytes([255, 0, 0, 0, 255, 0]),
            raw_data=bytes([0, 0, 255, 0, 0, 255, 0, 0]),
        )

        self.assertEqual(display._pack_frame(image), bytes([0, 0, 255, 0, 0, 255, 0, 0]))
        self.assertEqual(image.raw_calls, [("raw", "BGRX")])

    def test_pack_frame_fast_raw_path_preserves_padded_stride(self) -> None:
        display = self.Display(
            physical_width=2,
            physical_height=2,
            logical_width=2,
            logical_height=2,
            pixel_format="bgrx8888",
        )
        display._stride = 12
        image = _ImageRawBytes(
            rgb_data=b"",
            raw_data=bytes(range(16)),
        )

        self.assertEqual(
            display._pack_frame(image),
            bytes(range(8)) + bytes(4) + bytes(range(8, 16)) + bytes(4),
        )

    def test_sleep_preserves_brightness_for_wake(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            backlight = Path(temp_dir)
            (backlight / "max_brightness").write_text("255\n", encoding="ascii")
            (backlight / "brightness").write_text("255\n", encoding="ascii")
            display = self.Display(backlight_path=str(backlight))
            display._backlight_level = 0.5
            display.show = lambda: None

            display.sleep()
            self.assertEqual((backlight / "brightness").read_text(encoding="ascii"), "0\n")
            self.assertEqual(display._backlight_level, 0.5)

            display.wake()
            self.assertEqual((backlight / "brightness").read_text(encoding="ascii"), "128\n")


if __name__ == "__main__":
    unittest.main()

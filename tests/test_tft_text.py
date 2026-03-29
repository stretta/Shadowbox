import unittest
import importlib.util
from pathlib import Path
import sys
import types


_MODULE_PATH = Path(__file__).resolve().parents[1] / "shadowbox" / "display" / "tft_text.py"
_SPEC = importlib.util.spec_from_file_location("shadowbox.display.tft_text", _MODULE_PATH)
assert _SPEC is not None and _SPEC.loader is not None

pil_module = types.ModuleType("PIL")
image_module = types.ModuleType("PIL.Image")
image_draw_module = types.ModuleType("PIL.ImageDraw")
image_font_module = types.ModuleType("PIL.ImageFont")


class _FakeImage:
    size = (1, 1)

    def paste(self, *_args, **_kwargs) -> None:
        pass


class _FakeDraw:
    def textbbox(self, *_args, **_kwargs) -> tuple[int, int, int, int]:
        return (0, 0, 1, 1)

    def text(self, *_args, **_kwargs) -> None:
        pass


image_module.new = lambda *_args, **_kwargs: _FakeImage()
image_draw_module.Draw = lambda *_args, **_kwargs: _FakeDraw()
image_font_module.truetype = lambda *_args, **_kwargs: object()
image_font_module.load_default = lambda: object()
image_font_module.FreeTypeFont = object
image_font_module.ImageFont = object
pil_module.Image = image_module
pil_module.ImageDraw = image_draw_module
pil_module.ImageFont = image_font_module
sys.modules.setdefault("PIL", pil_module)
sys.modules.setdefault("PIL.Image", image_module)
sys.modules.setdefault("PIL.ImageDraw", image_draw_module)
sys.modules.setdefault("PIL.ImageFont", image_font_module)

_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)
_normalize_weight_name = _MODULE._normalize_weight_name
_FONT_CANDIDATES = _MODULE._FONT_CANDIDATES


class TftTextTests(unittest.TestCase):
    def test_normalize_weight_name_maps_condensed_aliases(self) -> None:
        self.assertEqual(_normalize_weight_name("condensed"), "condensed-regular")
        self.assertEqual(_normalize_weight_name("bold condensed"), "condensed-bold")
        self.assertEqual(_normalize_weight_name("medium_condensed"), "condensed-medium")
        self.assertEqual(_normalize_weight_name("condensed semibold"), "condensed-semibold")

    def test_default_weights_prefer_condensed_family(self) -> None:
        self.assertEqual(Path(_FONT_CANDIDATES["regular"][0]).name, "IBMPlexSansCondensed-Regular.ttf")
        self.assertEqual(Path(_FONT_CANDIDATES["medium"][0]).name, "IBMPlexSansCondensed-Medium.ttf")
        self.assertEqual(Path(_FONT_CANDIDATES["bold"][0]).name, "IBMPlexSansCondensed-Bold.ttf")


if __name__ == "__main__":
    unittest.main()

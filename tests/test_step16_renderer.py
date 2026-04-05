import sys
import types
import unittest
from types import SimpleNamespace


pythonosc_module = types.ModuleType("pythonosc")
udp_client_module = types.ModuleType("pythonosc.udp_client")
udp_client_module.SimpleUDPClient = object
pythonosc_module.udp_client = udp_client_module
sys.modules.setdefault("pythonosc", pythonosc_module)
sys.modules.setdefault("pythonosc.udp_client", udp_client_module)

from shadowbox.renderer import STEP16_ENABLED_FILL_LEVEL, ShadowboxRenderer


class _Step16Display:
    width = 320
    height = 240

    def __init__(self) -> None:
        self.rect_calls: list[tuple[int, int, int, int, bool, bool]] = []
        self.fill_level_calls: list[tuple[int, int, int, int, int]] = []

    def text_with_style(self, s: str, x: int, y: int, scale: int = 1, weight: str = "regular", on: bool = True) -> None:
        pass

    def measure_text(self, s: str, scale: int = 1, weight: str = "regular") -> tuple[int, int]:
        return (len(str(s)) * 8 * scale, 8 * scale)

    def line_height(self, scale: int = 1, weight: str = "regular") -> int:
        return 8 * scale

    def hline(self, x: int, y: int, w: int, on: bool = True) -> None:
        pass

    def vline(self, x: int, y: int, h: int, on: bool = True) -> None:
        pass

    def rect(self, x: int, y: int, w: int, h: int, on: bool = True, fill: bool = False) -> None:
        self.rect_calls.append((x, y, w, h, on, fill))

    def fill_rect_level(self, x: int, y: int, w: int, h: int, level: int) -> None:
        self.fill_level_calls.append((x, y, w, h, level))


class Step16RendererTests(unittest.TestCase):
    def test_tft_active_steps_use_70_percent_fill_level(self) -> None:
        display = _Step16Display()
        renderer = ShadowboxRenderer(display)
        ui = SimpleNamespace(active_step16_playhead=None)
        state = SimpleNamespace(edit_value=0b101, edit_step16_focus=0)

        renderer.draw_edit_step16(ui, {"name": "step16"}, state)

        self.assertEqual(len(display.fill_level_calls), 2)
        self.assertTrue(all(call[-1] == STEP16_ENABLED_FILL_LEVEL for call in display.fill_level_calls))
        self.assertTrue(all(fill is False for *_rest, fill in display.rect_calls[:16]))


if __name__ == "__main__":
    unittest.main()

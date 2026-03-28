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

from shadowbox.renderer import ShadowboxRenderer


class _StubDisplay:
    width = 320
    height = 240

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
        pass


class _CapturingRenderer(ShadowboxRenderer):
    def __init__(self, display) -> None:
        super().__init__(display)
        self.caption_calls = 0
        self.keyboard_y = None

    def _draw_edit_caption(self, text: str, y: int) -> None:
        self.caption_calls += 1

    def _draw_ttid_keyboard(self, mask: int, selected_pc: int, x: int, y: int, w: int, h: int) -> None:
        self.keyboard_y = y

    def _text(self, text: str, x: int, y: int, scale: int = 1, weight: str = "regular", on: bool = True) -> None:
        pass

    def _draw_right_aligned(self, text: str, right_x: int, y: int, scale: int = 1, weight: str = "regular") -> None:
        pass


class TtidRendererTests(unittest.TestCase):
    def test_full_tft_keyboard_mode_does_not_draw_caption(self) -> None:
        renderer = _CapturingRenderer(_StubDisplay())
        state = SimpleNamespace(
            edit_value=0,
            edit_ttid_mode="keyboard",
            edit_ttid_selected_pc=0,
            edit_ttid_load_root=0,
            edit_ttid_scale_names=[],
            edit_ttid_scale_index=0,
        )

        renderer.draw_edit_ttid(state, {"name": "ttid"})

        self.assertIsNotNone(renderer.keyboard_y)
        self.assertEqual(renderer.caption_calls, 0)


if __name__ == "__main__":
    unittest.main()

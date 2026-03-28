import sys
import types
import unittest


pythonosc_module = types.ModuleType("pythonosc")
udp_client_module = types.ModuleType("pythonosc.udp_client")
udp_client_module.SimpleUDPClient = object
pythonosc_module.udp_client = udp_client_module
sys.modules.setdefault("pythonosc", pythonosc_module)
sys.modules.setdefault("pythonosc.udp_client", udp_client_module)

from shadowbox.brick_panel import BRICK_PANEL_TRIGGER_PRESSES, BrickPanelGame
from shadowbox.renderer import ShadowboxRenderer
from shadowbox.ui import UIEvent, ShadowboxUI


class _FakeDisplay:
    width = 128
    height = 64

    def clear(self) -> None:
        pass

    def text_with_style(self, text: str, x: int, y: int, scale: int, weight: str, on: bool = True) -> None:
        pass

    def measure_text(self, text: str, scale: int = 1, weight: str = "regular") -> tuple[int, int]:
        return (len(str(text)) * 6 * max(1, scale), 8 * max(1, scale))

    def line_height(self, scale: int = 1, weight: str = "regular") -> int:
        return 8 * max(1, scale)

    def pixel(self, x: int, y: int, on: bool = True) -> None:
        pass

    def hline(self, x: int, y: int, w: int, on: bool = True) -> None:
        pass

    def vline(self, x: int, y: int, h: int, on: bool = True) -> None:
        pass

    def rect(self, x: int, y: int, w: int, h: int, on: bool = True, fill: bool = False) -> None:
        pass

    def show(self) -> None:
        pass


class BrickPanelTests(unittest.TestCase):
    def test_about_unlocks_brick_panel_after_hidden_press_count(self) -> None:
        ui = ShadowboxUI()
        ui.state.ui_mode = "ABOUT"

        for _ in range(BRICK_PANEL_TRIGGER_PRESSES):
            ui.handle_event(UIEvent(kind="short_press"))

        self.assertEqual(ui.state.ui_mode, "BRICK_PANEL")
        self.assertFalse(ui.brick_panel.launched)

    def test_brick_panel_long_press_returns_to_about(self) -> None:
        ui = ShadowboxUI()
        ui.state.ui_mode = "BRICK_PANEL"

        ui.handle_event(UIEvent(kind="long_press"))

        self.assertEqual(ui.state.ui_mode, "ABOUT")

    def test_press_launches_ball_and_brick_hit_scores(self) -> None:
        game = BrickPanelGame()
        game.press()

        for _ in range(120):
            game.update()
            if game.score > 0:
                break

        self.assertTrue(game.launched)
        self.assertGreater(game.score, 0)

    def test_renderer_draws_brick_panel_mode(self) -> None:
        ui = ShadowboxUI()
        ui.state.ui_mode = "BRICK_PANEL"
        renderer = ShadowboxRenderer(_FakeDisplay())

        renderer.draw(ui)


if __name__ == "__main__":
    unittest.main()

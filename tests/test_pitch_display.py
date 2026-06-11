import sys
import types
import unittest
from types import SimpleNamespace

from shadowbox.editors.pitch_display import normalize_pitch_to_midi_note


pythonosc_module = types.ModuleType("pythonosc")
udp_client_module = types.ModuleType("pythonosc.udp_client")
udp_client_module.SimpleUDPClient = object
pythonosc_module.udp_client = udp_client_module
sys.modules.setdefault("pythonosc", pythonosc_module)
sys.modules.setdefault("pythonosc.udp_client", udp_client_module)

from shadowbox.renderer import ShadowboxRenderer


class _StubDisplay:
    width = 128
    height = 32

    def __init__(self) -> None:
        self.ops: list[tuple] = []

    def clear(self) -> None:
        pass

    def text_with_style(self, text: str, x: int, y: int, scale: int, weight: str, on: bool = True) -> None:
        self.ops.append(("text", text, x, y, scale, weight, on))

    def measure_text(self, text: str, scale: int = 1, weight: str = "regular") -> tuple[int, int]:
        return (len(str(text)) * 6 * max(1, scale), 8 * max(1, scale))

    def line_height(self, scale: int = 1, weight: str = "regular") -> int:
        return 8 * max(1, scale)

    def pixel(self, x: int, y: int, on: bool = True) -> None:
        self.ops.append(("pixel", x, y, on))

    def hline(self, x: int, y: int, w: int, on: bool = True) -> None:
        self.ops.append(("hline", x, y, w, on))

    def vline(self, x: int, y: int, h: int, on: bool = True) -> None:
        self.ops.append(("vline", x, y, h, on))

    def rect(self, x: int, y: int, w: int, h: int, on: bool = True, fill: bool = False) -> None:
        self.ops.append(("rect", x, y, w, h, on, fill))

    def show(self) -> None:
        pass


class _FullTftDisplay(_StubDisplay):
    width = 320
    height = 240


class _TouchPitchDisplay(_StubDisplay):
    width = 800
    height = 480

    def fill_rect_color(self, x: int, y: int, w: int, h: int, color) -> None:
        self.ops.append(("fill_rect_color", x, y, w, h, color))

    def rect_color(self, x: int, y: int, w: int, h: int, color, fill: bool = False) -> None:
        self.ops.append(("rect_color", x, y, w, h, color, fill))

    def rounded_rect_color(self, x: int, y: int, w: int, h: int, radius: int, color, fill: bool = False) -> None:
        self.ops.append(("rounded_rect_color", x, y, w, h, radius, color, fill))

    def hline_color(self, x: int, y: int, w: int, color) -> None:
        self.ops.append(("hline_color", x, y, w, color))

    def text_color(self, text: str, x: int, y: int, color, scale: int = 1, weight: str = "regular") -> None:
        self.ops.append(("text_color", text, x, y, color, scale, weight))


class _HatDisplay(_StubDisplay):
    width = 128
    height = 128


_HatDisplay.__module__ = "shadowbox.display.st7735s_hat"


class _RendererUIStub(SimpleNamespace):
    def __getattr__(self, name: str):
        return ""


class _RendererStateStub(SimpleNamespace):
    def __getattr__(self, name: str):
        return ""


class PitchDisplayTests(unittest.TestCase):
    def setUp(self) -> None:
        self.renderer = ShadowboxRenderer(_StubDisplay())

    def test_normalize_pitch_to_midi_note_accepts_numeric_inputs(self) -> None:
        self.assertEqual(normalize_pitch_to_midi_note(69), 69)
        self.assertEqual(normalize_pitch_to_midi_note(69.49), 69)
        self.assertEqual(normalize_pitch_to_midi_note("69.5"), 70)
        self.assertEqual(normalize_pitch_to_midi_note(" 60 "), 60)
        self.assertEqual(normalize_pitch_to_midi_note([57.6]), 58)

    def test_normalize_pitch_to_midi_note_rejects_non_numeric_inputs(self) -> None:
        self.assertIsNone(normalize_pitch_to_midi_note(None))
        self.assertIsNone(normalize_pitch_to_midi_note("-"))
        self.assertIsNone(normalize_pitch_to_midi_note("A4"))
        self.assertIsNone(normalize_pitch_to_midi_note(float("nan")))
        self.assertIsNone(normalize_pitch_to_midi_note(True))

    def test_pitch_display_segments_use_midi_integer_for_numeric_pitch(self) -> None:
        segments = self.renderer._pitch_display_segments("69.8", 2)
        self.assertEqual(
            segments,
            [("70", 2, "regular"), (" ", 2, "regular"), ("A#4", 2, "medium")],
        )

    def test_pitch_display_segments_only_fall_back_for_non_numeric_pitch(self) -> None:
        segments = self.renderer._pitch_display_segments("A4", 2)
        self.assertEqual(segments, [("A4", 2, "medium")])

    def test_wrap_text_to_width_preserves_full_words_when_possible(self) -> None:
        renderer = ShadowboxRenderer(_StubDisplay())
        lines = renderer._wrap_text_to_width("press to enter", max_width=60, scale=1)

        self.assertEqual(lines, ["press to", "enter"])

    def test_draw_startup_status_wraps_hint_on_full_tft_without_ellipsis(self) -> None:
        display = _FullTftDisplay()
        renderer = ShadowboxRenderer(display)

        renderer.draw_startup_status(
            "SHADOWBOX",
            "waiting for OSCQuery Runner",
            "(this is normal) press to enter",
        )

        text_ops = [op for op in display.ops if op[0] == "text"]
        rendered_text = [op[1] for op in text_ops]

        self.assertIn("waiting for OSCQuery", rendered_text)
        self.assertIn("Runner", rendered_text)
        self.assertIn("(this is normal) press", rendered_text)
        self.assertIn("to enter", rendered_text)
        self.assertTrue(all("..." not in text for text in rendered_text))
        self.assertIn(2, [op[4] for op in text_ops])
        self.assertIn(4, [op[4] for op in text_ops])

    def test_draw_startup_status_draws_activity_bar_when_phase_is_given(self) -> None:
        display = _FullTftDisplay()
        renderer = ShadowboxRenderer(display)

        renderer.draw_startup_status(
            "SHADOWBOX",
            "waiting for OSCQuery Runner",
            "(this is normal) press to enter",
            activity_phase=0.25,
        )

        rect_ops = [op for op in display.ops if op[0] == "rect"]

        self.assertGreaterEqual(len(rect_ops), 2)
        self.assertTrue(any(op[6] is False for op in rect_ops))
        self.assertTrue(any(op[6] is True for op in rect_ops))

    def test_st7735s_hat_uses_four_text_rows(self) -> None:
        renderer = ShadowboxRenderer(_HatDisplay())

        self.assertEqual(renderer.layout_mode, "tft_tiny_text")
        self.assertEqual(renderer.content_rows, [26, 50, 74, 98])

    def test_st7735s_hat_top_menu_renders_as_text_list_not_icon_cards(self) -> None:
        display = _HatDisplay()
        renderer = ShadowboxRenderer(display)
        ui = _RendererUIStub(
            state=_RendererStateStub(
                ui_mode="TOP",
                top_index=1,
                busy=False,
                activity_ticks=0,
            ),
            top_level_items=["SETS", "INSTANCES", "SYSTEM"],
        )

        renderer.draw(ui)

        text_ops = [op for op in display.ops if op[0] == "text"]
        rendered = [op[1] for op in text_ops]
        self.assertIn("SHADOWBOX", rendered)
        self.assertIn("  SETS", rendered)
        self.assertIn("> INSTANCES", rendered)
        self.assertIn("  SYSTEM", rendered)
        self.assertFalse(any(op[0] == "rect" for op in display.ops))
        self.assertFalse(any(op[0] == "hline" for op in display.ops))

    def test_st7735s_hat_startup_status_uses_simple_splash(self) -> None:
        display = _HatDisplay()
        renderer = ShadowboxRenderer(display)

        renderer.draw_startup_status(
            "SHADOWBOX",
            "waiting for OSCQuery Runner",
            "(this is normal) press to enter",
        )

        text_ops = [op for op in display.ops if op[0] == "text"]
        rendered = [op[1] for op in text_ops]
        self.assertIn("SHADOW", rendered)
        self.assertIn("BOX", rendered)
        self.assertNotIn("waiting for OSCQuery Runner", rendered)
        self.assertFalse(any("waiting" in text.lower() for text in rendered))
        self.assertFalse(any("press" in text.lower() for text in rendered))

    def test_touch_tuner_uses_card_style_and_larger_readout(self) -> None:
        display = _TouchPitchDisplay()
        renderer = ShadowboxRenderer(display)
        renderer.set_touch_mode(True)
        ui = SimpleNamespace(
            active_pitch_display_pitch={"value": "69.8"},
            active_pitch_display_cents={"value": "+1.7"},
        )

        renderer.draw_edit_pitch_display(ui, {"name": "pitch"})

        rounded = [op for op in display.ops if op[0] == "rounded_rect_color"]
        text_ops = [op for op in display.ops if isinstance(op[0], str)]
        self.assertTrue(rounded)
        self.assertIn("TUNER", [op[1] for op in display.ops if op[0] == "text_color"])
        self.assertTrue(any(op[0] == "text" and op[1] in {"70", "A#4"} and op[4] == 6 for op in text_ops))
        self.assertTrue(any(op[0] == "text" and op[1] == "+1.7c" and op[4] == 2 for op in display.ops))


if __name__ == "__main__":
    unittest.main()

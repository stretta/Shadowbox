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

from shadowbox.render_scheduler import RenderScheduler
from shadowbox.renderer import ShadowboxRenderer
from shadowbox.surfaces import resolve_instance_surface
from shadowbox.surfaces.list_sequencer import FIELD_KEYS
from shadowbox.surfaces.list_vel_sequencer import ROW_KEYS
from shadowbox.surfaces.organ import FOOTAGES
from shadowbox.surfaces.shadowscore_client import (
    ack_label,
    midi_note_label,
    parse_midi_debug,
    parse_playback_debug,
    parse_shadowscore_ack,
    transfer_status_label,
)
from shadowbox.touch import TouchLayout
from shadowbox.ui import ShadowboxUI, UIEvent


def _param(name, *, value=0.0, minimum=0.0, maximum=1.0, metadata=None):
    return {
        "name": name,
        "path": f"/rnbo/inst/7/params/{name}",
        "value": value,
        "min": minimum,
        "max": maximum,
        "metadata": dict(metadata or {}),
    }


def _state(name, value=0.0):
    return {
        "name": name,
        "path": f"/rnbo/inst/7/messages/out/{name}",
        "value": value,
        "metadata": {},
    }


def _scope_instance():
    return {
        "id": "7",
        "name": "TimeDomainScope",
        "label": "MY SCOPE",
        "params": [_param("SamplingRate", value=48.0, minimum=10.0, maximum=100.0, metadata={"editor": "Scope Display"})],
        "state": [_state("scope", [0.1, -0.1])],
    }


def _analog_instance():
    params = []
    for stage in range(1, 17):
        params.append(_param(f"{stage:02d}StageValue", value=60.0, minimum=0.0, maximum=127.0))
        params.append(_param(f"{stage:02d}StageStep", value=1.0, minimum=0.0, maximum=1.0))
    params.extend(
        [
            _param("MaxCnt", value="16"),
            _param("Clock/Clock", value="On"),
            _param("Clock/Swing", value="Off"),
            _param("Clock/ClockInterval", value=240.0, minimum=30.0, maximum=3840.0),
            _param("Clock/SwingAmt", value=0.5, minimum=0.5, maximum=1.0),
        ]
    )
    return {
        "id": "7",
        "name": "AnalogSequencer",
        "label": "RENAMED",
        "params": params,
        "state": [_state("current_stage", [3.0])],
    }


def _organ_instance():
    names = ["Bass", "Quint", "Neutral", "Octave", "Nazard", "Block-flute", "Tierce", "Larigot", "Sifflute"]
    return {
        "id": "7",
        "name": "Organ",
        "label": "DRAWBARS",
        "params": [_param(name, value=-96.0, minimum=-96.0, maximum=0.0) for name in names],
        "state": [],
    }


def _tuner_instance():
    return {
        "id": "7",
        "name": "Tuner",
        "label": "Tuner",
        "params": [
            _param("Tuner", value=0.0, minimum=0.0, maximum=1.0, metadata={"editor": "pitch_display"}),
            _param("Smooth", value=0.0, minimum=0.0, maximum=100.0),
            _param("NoiseThreshold", value=0.0, minimum=0.0, maximum=100.0),
        ],
        "state": [_state("pitch_name", []), _state("pitch_cents", [])],
    }


def _live_organ_instance():
    instance = _organ_instance()
    for param in instance["params"]:
        param["name"] = f"Tonewheel/{param['name']}"
        param["path"] = f"/rnbo/inst/7/params/{param['name']}"
    return instance


def _list_input(name):
    return {
        "name": name,
        "path": f"/rnbo/inst/7/messages/in/{name}",
        "metadata": {},
    }


def _list_sequencer_instance():
    names = ["Steps", "StepsSecondary", "PrimaryRotation", "SecondaryRotation", "Oct", "Velocity", "Duration"]
    return {
        "id": "7",
        "name": "ListSequencer",
        "label": "LISTS",
        "params": [],
        "inputs": [_list_input(name) for name in names],
        "state": [_state(f"{name}Ack", [0.0, 1.0] if name == "Steps" else [1.0, 2.0]) for name in names],
    }


def _list_vel_sequencer_instance():
    names = [f"{row}row" for row in range(1, 9)]
    mute_params = [
        _param(f"{row}mute", value="On" if row == 2 else "Off")
        for row in range(1, 9)
    ]
    for param in mute_params:
        param["vals"] = ["Off", "On"]
    return {
        "id": "7",
        "name": "ListVelSequencer",
        "label": "VELOCITIES",
        "params": [
            _param(f"{row}map", value=float(35 + row), minimum=0.0, maximum=127.0)
            for row in range(1, 9)
        ] + mute_params,
        "inputs": [_list_input(name) for name in names],
        "state": [
            _state(f"{name}Ack", [40.0, 80.0] if name == "1row" else [64.0])
            for name in names
        ],
    }


def _shadowscore_client_instance():
    return {
        "id": "7",
        "name": "ShadowScoreClient",
        "label": "PLAYER THREE",
        "params": [],
        "state": [
            _state("current_stage", [384]),
            _state("playback_debug", [30, 384, 3, 60, 4, 100, 63, 8, 84, 67, 2, 112]),
            _state("midi_debug", [67, 112, 256.4102478027344]),
            _state("shadowscore_ack", [90, 93, 42, 819, 384, 1]),
        ],
    }


def _snapshot(instances):
    return SimpleNamespace(
        instances=instances,
        patchers=[],
        add_instance_path="",
        remove_instance_path="",
        system={},
    )


class _SurfaceDisplay:
    width = 800
    height = 480

    def __init__(self):
        self.ops = []

    def clear(self):
        pass

    def show(self):
        pass

    def measure_text(self, text, scale=1, weight="regular"):
        return len(str(text)) * 8 * scale, 12 * scale

    def line_height(self, scale=1, weight="regular"):
        return 12 * scale

    def text_with_style(self, *args, **kwargs):
        self.ops.append(("text", *args))

    def text_color(self, *args, **kwargs):
        self.ops.append(("text_color", *args))

    def text_line_color(self, *args, **kwargs):
        self.ops.append(("text_line_color", *args))

    def rect(self, *args, **kwargs):
        self.ops.append(("rect", *args))

    def hline(self, *args, **kwargs):
        self.ops.append(("hline", *args))

    def vline(self, *args, **kwargs):
        self.ops.append(("vline", *args))

    def fill_rect_color(self, *args, **kwargs):
        self.ops.append(("fill_rect_color", *args))

    def rect_color(self, *args, **kwargs):
        self.ops.append(("rect_color", *args))

    def rounded_rect_color(self, *args, **kwargs):
        self.ops.append(("rounded_rect_color", *args))

    def hline_color(self, *args, **kwargs):
        self.ops.append(("hline_color", *args))


class InstanceSurfaceTests(unittest.TestCase):
    def test_resolution_uses_export_name_not_label(self):
        instance = _scope_instance()
        instance["label"] = "Tuner"
        resolved = resolve_instance_surface(instance)
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved[0].key, "time_domain_scope")

    def test_missing_scope_state_rejects_surface(self):
        instance = _scope_instance()
        instance["state"] = []
        self.assertIsNone(resolve_instance_surface(instance))

    def test_live_tuner_contract_resolves_pitch_and_cents(self):
        resolved = resolve_instance_surface(_tuner_instance())
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved[0].key, "tuner")
        self.assertEqual(resolved[1].params["anchor"]["name"], "Tuner")
        self.assertEqual(resolved[1].state["pitch"]["name"], "pitch_name")
        self.assertEqual(resolved[1].state["cents"]["name"], "pitch_cents")

    def test_shadowscore_client_resolves_canonical_export_and_four_outports(self):
        instance = _shadowscore_client_instance()
        instance["label"] = "RENAMED PLAYER"

        resolved = resolve_instance_surface(instance)

        self.assertIsNotNone(resolved)
        self.assertEqual(resolved[0].key, "shadowscore_client")
        self.assertEqual(tuple(resolved[1].state), (
            "current_stage",
            "playback_debug",
            "midi_debug",
            "shadowscore_ack",
        ))

    def test_shadowscore_client_rejects_missing_or_duplicate_required_outport(self):
        missing = _shadowscore_client_instance()
        missing["state"] = [item for item in missing["state"] if item["name"] != "midi_debug"]
        duplicate = _shadowscore_client_instance()
        duplicate["state"].append(dict(duplicate["state"][1], path="/rnbo/inst/7/state/playback_debug"))

        self.assertIsNone(resolve_instance_surface(missing))
        self.assertIsNone(resolve_instance_surface(duplicate))

    def test_shadowscore_client_parses_chord_midi_ack_and_note_names(self):
        chord = parse_playback_debug([30, 24, 2, 60, 4, 100, 63, 8, 84])

        self.assertEqual(chord, {
            "stage": 24,
            "note_count": 2,
            "notes": [
                {"pitch": 60, "duration": 4, "velocity": 100},
                {"pitch": 63, "duration": 8, "velocity": 84},
            ],
        })
        self.assertEqual(
            parse_midi_debug([79, 64, 256.4102478027344]),
            {"pitch": 79, "velocity": 64, "duration_ms": 256.4102478027344},
        )
        self.assertEqual(ack_label([90, 92, 42, 819, 1]), "READY")
        self.assertEqual(ack_label([90, 93, 42, 819, 24, 1]), "ACTIVE")
        self.assertEqual(parse_shadowscore_ack([90, 1, 43, 60, 1617, 4]), {
            "opcode": 1,
            "transaction_id": 43,
            "phase": "receiving",
            "received": 0,
            "expected": 60,
            "pattern_length": 1617,
            "stages_per_beat": 4,
        })
        self.assertEqual(
            transfer_status_label(parse_shadowscore_ack([90, 91, 43, 5, 10, 0])),
            "REJECTED ROW ORDER 10",
        )
        self.assertEqual(midi_note_label(60), "C4")
        self.assertEqual(midi_note_label(63), "Eb4")

    def test_shadowscore_client_rejects_malformed_playback_lists(self):
        self.assertIsNone(parse_playback_debug([30, 4, 2, 60, 4, 100]))
        self.assertIsNone(parse_playback_debug([30, -1, 0]))
        self.assertIsNone(parse_playback_debug([31, 4, 0]))
        self.assertIsNone(parse_midi_debug([60, 4]))

    def test_shadowscore_client_surface_tracks_distinct_recent_playback_events(self):
        ui = ShadowboxUI()
        instance = _shadowscore_client_instance()
        ui.apply_runner_snapshot(_snapshot([instance]))
        ui.state.ui_mode = "INSTANCE_MENU"
        ui.state.instance_menu_cursor = 1

        ui.handle_event(UIEvent("short_press"))

        self.assertEqual(ui.state.active_surface_key, "shadowscore_client")
        self.assertEqual([event["stage"] for event in ui.state.surface_state["playback_events"]], [384])
        playback = next(item for item in instance["state"] if item["name"] == "playback_debug")
        self.assertTrue(ui.apply_instance_state_update("7", playback["path"], [30, 385, 0]))
        self.assertTrue(ui.apply_instance_state_update("7", playback["path"], [30, 385, 0]))
        self.assertEqual([event["stage"] for event in ui.state.surface_state["playback_events"]], [384, 385])
        self.assertEqual(ui.state.surface_state["last_note_event"]["stage"], 384)
        self.assertEqual(ui.state.surface_state["rest_events"], 1)

        for stage in range(386, 406):
            ui.apply_instance_state_update("7", playback["path"], [30, stage, 0])
        self.assertEqual(len(ui.state.surface_state["playback_events"]), 17)
        self.assertEqual(ui.state.surface_state["playback_events"][-1]["stage"], 405)

    def test_shadowscore_client_snapshot_refresh_records_new_playback_event(self):
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(_snapshot([_shadowscore_client_instance()]))
        ui.state.ui_mode = "INSTANCE_MENU"
        ui.state.instance_menu_cursor = 1
        ui.handle_event(UIEvent("short_press"))
        refreshed = _shadowscore_client_instance()
        next(item for item in refreshed["state"] if item["name"] == "playback_debug")["value"] = [30, 385, 0]

        ui.apply_runner_snapshot(_snapshot([refreshed]))

        self.assertEqual([event["stage"] for event in ui.state.surface_state["playback_events"]], [384, 385])

    def test_shadowscore_client_surface_tracks_transaction_progress(self):
        ui = ShadowboxUI()
        instance = _shadowscore_client_instance()
        ui.apply_runner_snapshot(_snapshot([instance]))
        ui.state.ui_mode = "INSTANCE_MENU"
        ui.state.instance_menu_cursor = 1
        ui.handle_event(UIEvent("short_press"))
        ack = next(item for item in instance["state"] if item["name"] == "shadowscore_ack")

        self.assertTrue(ui.apply_instance_state_update("7", ack["path"], [90, 1, 43, 60, 1617, 4]))
        self.assertTrue(ui.apply_instance_state_update("7", ack["path"], [90, 20, 43, 9, 10, 1]))

        self.assertEqual(ui.state.surface_state["transfer_status"]["received"], 10)
        self.assertEqual(ui.state.surface_state["transfer_status"]["expected"], 60)
        display = _SurfaceDisplay()
        renderer = ShadowboxRenderer(display)
        renderer.set_touch_mode(True)
        renderer.draw(ui)
        text = [op[1] for op in display.ops if op[0] in {"text", "text_color"}]
        self.assertIn("RECEIVING 10/60", text)
        self.assertIn("TXN 43", text)

    def test_shadowscore_client_surface_renders_musical_state(self):
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(_snapshot([_shadowscore_client_instance()]))
        ui.state.ui_mode = "INSTANCE_MENU"
        ui.state.instance_menu_cursor = 1
        ui.handle_event(UIEvent("short_press"))
        display = _SurfaceDisplay()
        renderer = ShadowboxRenderer(display)
        renderer.set_touch_mode(True)

        renderer.draw(ui)

        text = [op[1] for op in display.ops if op[0] in {"text", "text_color"}]
        self.assertIn("STAGE 384", text)
        self.assertIn("C4", text)
        self.assertIn("Eb4", text)
        self.assertIn("G4", text)
        self.assertIn("ACTIVE", text)
        self.assertIn("LAST MIDI  G4  v112  256ms", text)
        self.assertIn("RECENT EVENTS", text)

    def test_shadowscore_client_rest_preserves_last_chord_without_claiming_it_is_current(self):
        ui = ShadowboxUI()
        instance = _shadowscore_client_instance()
        ui.apply_runner_snapshot(_snapshot([instance]))
        ui.state.ui_mode = "INSTANCE_MENU"
        ui.state.instance_menu_cursor = 1
        ui.handle_event(UIEvent("short_press"))
        playback = next(item for item in instance["state"] if item["name"] == "playback_debug")
        stage = next(item for item in instance["state"] if item["name"] == "current_stage")
        ui.apply_instance_state_update("7", stage["path"], [385])
        ui.apply_instance_state_update("7", playback["path"], [30, 385, 0])
        display = _SurfaceDisplay()
        renderer = ShadowboxRenderer(display)
        renderer.set_touch_mode(True)

        renderer.draw(ui)

        text = [op[1] for op in display.ops if op[0] in {"text", "text_color"}]
        self.assertIn("STAGE 385", text)
        self.assertIn("REST 1  ·  LAST CHORD STAGE 384", text)
        self.assertIn("C4", text)
        self.assertIn("Eb4", text)
        self.assertIn("G4", text)

    def test_current_wren_organ_db_contract_resolves_canonically(self):
        resolved = resolve_instance_surface(_live_organ_instance())
        self.assertIsNotNone(resolved)
        self.assertEqual(tuple(resolved[1].params), FOOTAGES)
        self.assertEqual(resolved[1].params["16"]["name"], "Tonewheel/Bass")
        self.assertEqual(resolved[1].params["1"]["name"], "Tonewheel/Sifflute")

    def test_planned_organ_contract_resolves_in_canonical_order(self):
        names = ["Drawbar1", "Drawbar1_1_3", "Drawbar16", "Drawbar2", "Drawbar8", "Drawbar5_1_3", "Drawbar4", "Drawbar2_2_3", "Drawbar1_3_5"]
        instance = {
            "id": "7",
            "name": "Organ",
            "params": [_param(name, minimum=0, maximum=8) for name in names],
            "state": [],
        }
        resolved = resolve_instance_surface(instance)
        self.assertEqual(tuple(resolved[1].params), FOOTAGES)

    def test_surface_menu_opens_without_modifying_param_cursor(self):
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(_snapshot([_scope_instance()]))
        ui.state.ui_mode = "INSTANCE_MENU"
        ui.state.instance_menu_cursor = 1
        ui.state.param_cursor = 9
        self.assertEqual(ui.instance_menu_items[0], "TIME DOMAIN SCOPE")

        ui.handle_event(UIEvent("short_press"))

        self.assertEqual(ui.state.ui_mode, "INSTANCE_SURFACE")
        self.assertEqual(ui.state.active_surface_key, "time_domain_scope")
        self.assertEqual(ui.state.param_cursor, 9)
        self.assertEqual(ui.state.edit_scope_samples, [0.1, -0.1])

    def test_back_returns_to_instance_menu(self):
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(_snapshot([_scope_instance()]))
        ui.state.ui_mode = "INSTANCE_MENU"
        ui.state.instance_menu_cursor = 1
        ui.handle_event(UIEvent("short_press"))

        ui.handle_event(UIEvent("long_press"))

        self.assertEqual(ui.state.ui_mode, "INSTANCE_MENU")
        self.assertEqual(ui.state.active_surface_key, "")

    def test_incompatible_refresh_closes_surface(self):
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(_snapshot([_scope_instance()]))
        ui.state.ui_mode = "INSTANCE_MENU"
        ui.state.instance_menu_cursor = 1
        ui.handle_event(UIEvent("short_press"))
        incompatible = _scope_instance()
        incompatible["state"] = []

        ui.apply_runner_snapshot(_snapshot([incompatible]))

        self.assertEqual(ui.state.ui_mode, "INSTANCE_MENU")

    def test_scope_surface_refresh_preserves_history(self):
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(_snapshot([_scope_instance()]))
        ui.state.ui_mode = "INSTANCE_MENU"
        ui.state.instance_menu_cursor = 1
        ui.handle_event(UIEvent("short_press"))
        ui.state.edit_scope_samples = [0.5, 0.25]

        ui.apply_runner_snapshot(_snapshot([_scope_instance()]))

        self.assertEqual(ui.state.edit_scope_samples, [0.5, 0.25])

    def test_surface_frame_rates(self):
        ui = ShadowboxUI()
        for instance, expected in ((_scope_instance(), 15.0), (_analog_instance(), 20.0)):
            ui.apply_runner_snapshot(_snapshot([instance]))
            ui.state.ui_mode = "INSTANCE_MENU"
            ui.state.instance_menu_cursor = 1
            ui.handle_event(UIEvent("short_press"))
            self.assertEqual(RenderScheduler.frame_rate(ui), expected)
            ui._exit_instance_surface()

    def test_list_sequencer_resolves_ordered_osc_inports(self):
        resolved = resolve_instance_surface(_list_sequencer_instance())

        self.assertIsNotNone(resolved)
        self.assertEqual(resolved[0].key, "list_sequencer")
        self.assertEqual(tuple(resolved[1].inputs), FIELD_KEYS)
        self.assertEqual(resolved[1].inputs["steps_secondary"]["name"], "StepsSecondary")
        self.assertEqual(resolved[1].state["duration_ack"]["name"], "DurationAck")

    def test_list_sequencer_rejects_missing_required_inport(self):
        instance = _list_sequencer_instance()
        instance["inputs"] = [item for item in instance["inputs"] if item["name"] != "Duration"]

        self.assertIsNone(resolve_instance_surface(instance))

    def test_list_sequencer_open_reads_ack_fields_and_hydrates_drafts(self):
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(_snapshot([_list_sequencer_instance()]))
        ui.state.ui_mode = "INSTANCE_MENU"
        ui.state.instance_menu_cursor = 1

        ui.handle_event(UIEvent("short_press"))

        self.assertEqual(ui.state.active_surface_key, "list_sequencer")
        self.assertEqual(ui.state.surface_state["drafts"]["steps"], "0 1")
        reads = [action for action in ui.pop_actions() if action.kind == "send_osc"]
        self.assertEqual(len(reads), len(FIELD_KEYS))
        self.assertTrue(all(action.value == [-999] for action in reads))

    def test_list_sequencer_keypad_sends_complete_numeric_list(self):
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(_snapshot([_list_sequencer_instance()]))
        ui.state.ui_mode = "INSTANCE_MENU"
        ui.state.instance_menu_cursor = 1
        ui.handle_event(UIEvent("short_press"))
        ui.pop_actions()
        ui.state.surface_state["drafts"]["steps"] = ""

        for key in ("1", "space", "0", "space", "1"):
            ui.handle_event(UIEvent("edit_list_key", button_id=key))
        ui.handle_event(UIEvent("send_list_field"))

        writes = [action for action in ui.pop_actions() if action.kind == "send_osc"]
        self.assertEqual(len(writes), 1)
        self.assertEqual(writes[0].path, "/rnbo/inst/7/messages/in/Steps")
        self.assertEqual(writes[0].value, [1, 0, 1])

    def test_list_sequencer_signed_field_uses_contextual_sign(self):
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(_snapshot([_list_sequencer_instance()]))
        ui.state.ui_mode = "INSTANCE_MENU"
        ui.state.instance_menu_cursor = 1
        ui.handle_event(UIEvent("short_press"))
        ui.pop_actions()
        ui.handle_event(UIEvent("select_list_field", index=2))
        ui.state.surface_state["drafts"]["primary_rotation"] = ""

        ui.handle_event(UIEvent("toggle_list_sign"))
        ui.handle_event(UIEvent("edit_list_key", button_id="6"))
        ui.handle_event(UIEvent("edit_list_key", button_id="0"))
        ui.handle_event(UIEvent("send_list_field"))

        write = next(action for action in ui.pop_actions() if action.kind == "send_osc")
        self.assertEqual(write.value, [-60])

    def test_list_sequencer_keypad_field_steps_are_surface_scoped(self):
        ui = ShadowboxUI()
        ui.handle_event(UIEvent("step_list_field", delta=1))
        self.assertEqual(ui.state.surface_focus, 0)

        ui.apply_runner_snapshot(_snapshot([_list_sequencer_instance()]))
        ui.state.ui_mode = "INSTANCE_MENU"
        ui.state.instance_menu_cursor = 1
        ui.handle_event(UIEvent("short_press"))
        ui.handle_event(UIEvent("step_list_field", delta=1))
        self.assertEqual(ui.state.surface_focus, 1)
        ui.handle_event(UIEvent("step_list_field", delta=-1))
        self.assertEqual(ui.state.surface_focus, 0)

    def test_list_sequencer_keypad_next_field_wraps_to_first_field(self):
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(_snapshot([_list_sequencer_instance()]))
        ui.state.ui_mode = "INSTANCE_MENU"
        ui.state.instance_menu_cursor = 1
        ui.handle_event(UIEvent("short_press"))
        ui.state.surface_focus = len(FIELD_KEYS) - 1

        ui.handle_event(UIEvent("keypad_step", delta=1))

        self.assertEqual(ui.state.surface_focus, 0)

    def test_context_neutral_keypad_events_retain_list_sequencer_behavior(self):
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(_snapshot([_list_sequencer_instance()]))
        ui.state.ui_mode = "INSTANCE_MENU"
        ui.state.instance_menu_cursor = 1
        ui.handle_event(UIEvent("short_press"))
        ui.pop_actions()
        ui._list_surface_drafts()["steps"] = ""

        ui.handle_event(UIEvent("keypad_digit", button_id="1"))
        ui.handle_event(UIEvent("keypad_space"))
        ui.handle_event(UIEvent("keypad_digit", button_id="0"))
        ui.handle_event(UIEvent("keypad_decimal"))
        ui.handle_event(UIEvent("keypad_digit", button_id="1"))
        ui.handle_event(UIEvent("keypad_enter"))

        write = next(action for action in ui.pop_actions() if action.kind == "send_osc")
        self.assertEqual(write.value, [1, 1])

    def test_list_sequencer_steps_reject_non_binary_values(self):
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(_snapshot([_list_sequencer_instance()]))
        ui.state.ui_mode = "INSTANCE_MENU"
        ui.state.instance_menu_cursor = 1
        ui.handle_event(UIEvent("short_press"))
        ui.pop_actions()
        ui.state.surface_state["drafts"]["steps"] = "0 2"

        ui.handle_event(UIEvent("send_list_field"))

        self.assertEqual([action for action in ui.pop_actions() if action.kind == "send_osc"], [])
        self.assertEqual(ui.state.status_message, "INVALID LIST")

    def test_list_sequencer_ack_updates_clean_but_not_dirty_draft(self):
        ui = ShadowboxUI()
        instance = _list_sequencer_instance()
        ui.apply_runner_snapshot(_snapshot([instance]))
        ui.state.ui_mode = "INSTANCE_MENU"
        ui.state.instance_menu_cursor = 1
        ui.handle_event(UIEvent("short_press"))
        ui.pop_actions()
        steps_ack = next(item for item in instance["state"] if item["name"] == "StepsAck")

        self.assertTrue(ui.apply_instance_state_update("7", steps_ack["path"], [1, 1, 0]))
        self.assertEqual(ui.state.surface_state["drafts"]["steps"], "1 1 0")
        ui.handle_event(UIEvent("edit_list_key", button_id="1"))
        self.assertTrue(ui.apply_instance_state_update("7", steps_ack["path"], [0]))
        self.assertEqual(ui.state.surface_state["drafts"]["steps"], "1 1 01")

    def test_list_sequencer_rotate_reads_current_list_then_moves_first_item_to_end(self):
        ui = ShadowboxUI()
        instance = _list_sequencer_instance()
        ui.apply_runner_snapshot(_snapshot([instance]))
        ui.state.ui_mode = "INSTANCE_MENU"
        ui.state.instance_menu_cursor = 1
        ui.handle_event(UIEvent("short_press"))
        ui.pop_actions()
        ui.state.surface_state["drafts"]["steps"] = "0 0 0"
        ui.state.surface_state["dirty"]["steps"] = True

        ui.handle_event(UIEvent("rotate_list_field", index=0))

        read = next(action for action in ui.pop_actions() if action.kind == "send_osc")
        self.assertEqual(read.path, "/rnbo/inst/7/messages/in/Steps")
        self.assertEqual(read.value, [-999])
        steps_ack = next(item for item in instance["state"] if item["name"] == "StepsAck")
        self.assertTrue(ui.apply_instance_state_update("7", steps_ack["path"], [1, 0, 1]))
        write = next(action for action in ui.pop_actions() if action.kind == "send_osc")
        self.assertEqual(write.path, "/rnbo/inst/7/messages/in/Steps")
        self.assertEqual(write.value, [0, 1, 1])
        self.assertEqual(ui.state.surface_state["drafts"]["steps"], "0 1 1")
        self.assertNotIn("steps", ui.state.surface_state["dirty"])

    def test_list_sequencer_surface_renders_seven_fields_and_twelve_keys(self):
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(_snapshot([_list_sequencer_instance()]))
        ui.state.ui_mode = "INSTANCE_MENU"
        ui.state.instance_menu_cursor = 1
        ui.handle_event(UIEvent("short_press"))
        renderer = ShadowboxRenderer(_SurfaceDisplay())
        renderer.set_touch_mode(True)

        renderer.draw(ui)

        fields = [target for target in renderer.touch_layout.targets if target.kind == "list_field"]
        keys = [target for target in renderer.touch_layout.targets if target.kind == "list_key"]
        sends = [target for target in renderer.touch_layout.targets if target.kind == "list_send"]
        rotates = [target for target in renderer.touch_layout.targets if target.kind == "list_rotate"]
        self.assertEqual(len(fields), 7)
        self.assertEqual(len(keys), 12)
        self.assertEqual(len(sends), 1)
        self.assertEqual(len(rotates), 7)
        self.assertTrue(all(target.label == "ROT" for target in rotates))
        self.assertEqual([target.label for target in fields], [
            "Stp",
            "Stp2",
            "Rot",
            "Rot2",
            "Oct",
            "Vel",
            "Dur",
        ])
        self.assertFalse(any(target.kind == "list_sign" for target in renderer.touch_layout.targets))

        ui.handle_event(UIEvent("select_list_field", index=2))
        renderer.draw(ui)

        signs = [target for target in renderer.touch_layout.targets if target.kind == "list_sign"]
        self.assertEqual(len(signs), 1)
        self.assertEqual(signs[0].action_kind, "toggle_list_sign")

    def test_list_vel_sequencer_resolves_rows_maps_and_ack_state(self):
        resolved = resolve_instance_surface(_list_vel_sequencer_instance())

        self.assertIsNotNone(resolved)
        self.assertEqual(resolved[0].key, "list_vel_sequencer")
        self.assertEqual(tuple(resolved[1].inputs), ROW_KEYS)
        self.assertEqual(resolved[1].params["row_1_mute"]["name"], "1mute")
        self.assertEqual(resolved[1].params["row_4_map"]["name"], "4map")
        self.assertEqual(resolved[1].state["row_8_ack"]["name"], "8rowAck")

    def test_list_vel_sequencer_accepts_legacy_misspelled_fourth_row(self):
        instance = _list_vel_sequencer_instance()
        fourth = instance["inputs"][3]
        fourth["name"] = "4ow"
        fourth["path"] = "/rnbo/inst/7/messages/in/4ow"

        resolved = resolve_instance_surface(instance)

        self.assertIsNotNone(resolved)
        self.assertEqual(resolved[1].inputs["row_4"]["name"], "4ow")

    def test_list_vel_sequencer_open_reads_rows_and_hydrates_drafts(self):
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(_snapshot([_list_vel_sequencer_instance()]))
        ui.state.ui_mode = "INSTANCE_MENU"
        ui.state.instance_menu_cursor = 1

        ui.handle_event(UIEvent("short_press"))

        self.assertEqual(ui.state.active_surface_key, "list_vel_sequencer")
        self.assertEqual(ui.state.surface_state["drafts"]["row_1"], "40 80")
        reads = [action for action in ui.pop_actions() if action.kind == "send_osc"]
        self.assertEqual(len(reads), len(ROW_KEYS))
        self.assertTrue(all(action.value == [-999] for action in reads))

    def test_list_vel_sequencer_sends_selected_velocity_row(self):
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(_snapshot([_list_vel_sequencer_instance()]))
        ui.state.ui_mode = "INSTANCE_MENU"
        ui.state.instance_menu_cursor = 1
        ui.handle_event(UIEvent("short_press"))
        ui.pop_actions()
        ui.handle_event(UIEvent("select_list_field", index=2))
        ui.state.surface_state["drafts"]["row_3"] = "24 48 96"

        ui.handle_event(UIEvent("send_list_field"))

        write = next(action for action in ui.pop_actions() if action.kind == "send_osc")
        self.assertEqual(write.path, "/rnbo/inst/7/messages/in/3row")
        self.assertEqual(write.value, [24, 48, 96])

    def test_list_vel_sequencer_rotate_reads_and_sends_selected_row(self):
        ui = ShadowboxUI()
        instance = _list_vel_sequencer_instance()
        ui.apply_runner_snapshot(_snapshot([instance]))
        ui.state.ui_mode = "INSTANCE_MENU"
        ui.state.instance_menu_cursor = 1
        ui.handle_event(UIEvent("short_press"))
        ui.pop_actions()

        ui.handle_event(UIEvent("rotate_list_field", index=2))

        read = next(action for action in ui.pop_actions() if action.kind == "send_osc")
        self.assertEqual(read.path, "/rnbo/inst/7/messages/in/3row")
        self.assertEqual(read.value, [-999])
        row_ack = next(item for item in instance["state"] if item["name"] == "3rowAck")
        self.assertTrue(ui.apply_instance_state_update("7", row_ack["path"], [24, 48, 96]))
        write = next(action for action in ui.pop_actions() if action.kind == "send_osc")
        self.assertEqual(write.path, "/rnbo/inst/7/messages/in/3row")
        self.assertEqual(write.value, [48, 96, 24])

    def test_list_vel_sequencer_mute_button_toggles_row_param(self):
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(_snapshot([_list_vel_sequencer_instance()]))
        ui.state.ui_mode = "INSTANCE_MENU"
        ui.state.instance_menu_cursor = 1
        ui.handle_event(UIEvent("short_press"))
        ui.pop_actions()

        ui.handle_event(UIEvent("toggle_list_mute", index=1))

        self.assertEqual(ui.surface_param_binding("row_2_mute")["value"], "Off")
        self.assertEqual(ui.state.surface_focus, 1)
        write = next(action for action in ui.pop_actions() if action.kind == "set_param")
        self.assertEqual(write.path, "/rnbo/inst/7/params/2mute")
        self.assertEqual(write.value, "Off")

    def test_list_vel_sequencer_rejects_velocity_outside_midi_range(self):
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(_snapshot([_list_vel_sequencer_instance()]))
        ui.state.ui_mode = "INSTANCE_MENU"
        ui.state.instance_menu_cursor = 1
        ui.handle_event(UIEvent("short_press"))
        ui.pop_actions()
        ui.state.surface_state["drafts"]["row_1"] = "64 128"

        ui.handle_event(UIEvent("send_list_field"))

        self.assertEqual([action for action in ui.pop_actions() if action.kind == "send_osc"], [])
        self.assertEqual(ui.state.status_message, "INVALID LIST")

    def test_list_vel_sequencer_surface_renders_eight_rows_with_pitch_maps(self):
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(_snapshot([_list_vel_sequencer_instance()]))
        ui.state.ui_mode = "INSTANCE_MENU"
        ui.state.instance_menu_cursor = 1
        ui.handle_event(UIEvent("short_press"))
        renderer = ShadowboxRenderer(_SurfaceDisplay())
        renderer.set_touch_mode(True)

        renderer.draw(ui)

        rows = [target for target in renderer.touch_layout.targets if target.kind == "list_field"]
        keys = [target for target in renderer.touch_layout.targets if target.kind == "list_key"]
        sends = [target for target in renderer.touch_layout.targets if target.kind == "list_send"]
        mutes = [target for target in renderer.touch_layout.targets if target.kind == "list_mute"]
        rotates = [target for target in renderer.touch_layout.targets if target.kind == "list_rotate"]
        self.assertEqual(len(rows), 8)
        self.assertEqual(len(mutes), 8)
        self.assertEqual(len(rotates), 8)
        self.assertEqual(len(keys), 12)
        self.assertEqual(len(sends), 1)
        self.assertEqual([target.label for target in rows], [
            "1:36",
            "2:37",
            "3:38",
            "4:39",
            "5:40",
            "6:41",
            "7:42",
            "8:43",
        ])
        self.assertEqual(sends[0].label, "SEND ROW")
        self.assertTrue(all(target.label == "M" for target in mutes))
        self.assertTrue(all(target.label == "ROT" for target in rotates))
        self.assertFalse(any(target.kind == "list_sign" for target in renderer.touch_layout.targets))

    def test_list_vel_sequencer_buttons_use_rounded_borders(self):
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(_snapshot([_list_vel_sequencer_instance()]))
        ui.state.ui_mode = "INSTANCE_MENU"
        ui.state.instance_menu_cursor = 1
        ui.handle_event(UIEvent("short_press"))
        display = _SurfaceDisplay()
        renderer = ShadowboxRenderer(display)
        renderer.set_touch_mode(True)

        renderer.draw(ui)

        rounded = [op for op in display.ops if op[0] == "rounded_rect_color"]
        mute = next(target for target in renderer.touch_layout.targets if target.kind == "list_mute")
        send = next(target for target in renderer.touch_layout.targets if target.kind == "list_send")
        mute_shapes = [
            op
            for op in rounded
            if op[1] == mute.x and mute.y <= op[2] < mute.y + mute.h and op[3] == mute.w and op[5] == 7
        ]
        send_shapes = [op for op in rounded if op[1:5] == (send.x, send.y, send.w, send.h) and op[5] == 10]
        self.assertEqual([op[-1] for op in mute_shapes], [True, False])
        self.assertEqual([op[-1] for op in send_shapes], [True, False])
        self.assertFalse(any(op[0] == "rect_color" and op[1] == mute.x and op[3] == mute.w for op in display.ops))
        self.assertFalse(any(op[0] == "rect_color" and op[1:5] == (send.x, send.y, send.w, send.h) for op in display.ops))

    def test_analog_touch_updates_stage_and_toggle(self):
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(_snapshot([_analog_instance()]))
        ui.state.ui_mode = "INSTANCE_MENU"
        ui.state.instance_menu_cursor = 1
        ui.handle_event(UIEvent("short_press"))

        ui.handle_event(UIEvent("set_surface_value", index=2, value=0.5, pressed=True))
        ui.handle_event(UIEvent("toggle_surface_value", index=2))

        self.assertAlmostEqual(ui.surface_param_binding("stage_03_value")["value"], 48.0)
        self.assertEqual(ui.surface_param_binding("stage_03_enabled")["value"], 0)
        writes = [action for action in ui.pop_actions() if action.kind == "set_param"]
        self.assertEqual(len(writes), 2)

    def test_analog_surface_renders_sixteen_touch_targets(self):
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(_snapshot([_analog_instance()]))
        ui.state.ui_mode = "INSTANCE_MENU"
        ui.state.instance_menu_cursor = 1
        ui.handle_event(UIEvent("short_press"))
        renderer = ShadowboxRenderer(_SurfaceDisplay())
        renderer.set_touch_mode(True)

        renderer.draw(ui)

        targets = [target for target in renderer.touch_layout.targets if target.kind == "analog_stage_value"]
        toggles = [target for target in renderer.touch_layout.targets if target.kind == "analog_stage_toggle"]
        ranges = [target for target in renderer.touch_layout.targets if target.kind == "analog_pitch_range"]
        self.assertEqual(len(targets), 16)
        self.assertEqual(len(toggles), 16)
        self.assertEqual([target.button_id for target in ranges], ["low", "high"])
        self.assertEqual([target.label for target in ranges], ["LOW C1", "HIGH C5"])
        self.assertTrue(all(not target.label for target in targets + toggles))
        rendered_text = [op[1] for op in renderer.display.ops if op[0] in {"text", "text_color"}]
        self.assertNotIn("STAGES", rendered_text)
        self.assertFalse(any(text in {str(index) for index in range(1, 17)} for text in rendered_text))
        self.assertTrue(all(toggle.h <= 34 for toggle in toggles))

    def test_analog_surface_maps_one_based_current_stage_to_stage_cell(self):
        for current_stage, expected_index in ((1.0, 0), (4.0, 3), (16.0, 15)):
            instance = _analog_instance()
            instance["state"][0]["value"] = [current_stage]
            ui = ShadowboxUI()
            ui.apply_runner_snapshot(_snapshot([instance]))
            ui.state.ui_mode = "INSTANCE_MENU"
            ui.state.instance_menu_cursor = 1
            ui.handle_event(UIEvent("short_press"))
            renderer = ShadowboxRenderer(_SurfaceDisplay())
            renderer.set_touch_mode(True)

            renderer.draw(ui)

            stages = [target for target in renderer.touch_layout.targets if target.kind == "analog_stage_value"]
            markers = [
                op
                for op in renderer.display.ops
                if op[0] == "fill_rect_color" and op[4] == 5
            ]
            self.assertEqual(len(markers), 1)
            self.assertEqual(markers[0][1], stages[expected_index].x)

    def test_analog_pitch_range_clips_stages_and_constrains_touch(self):
        ui = ShadowboxUI()
        instance = _analog_instance()
        instance["params"][0]["value"] = 20.0
        instance["params"][2]["value"] = 90.0
        ui.apply_runner_snapshot(_snapshot([instance]))
        ui.state.ui_mode = "INSTANCE_MENU"
        ui.state.instance_menu_cursor = 1
        ui.handle_event(UIEvent("short_press"))
        ui.pop_actions()

        ui.handle_event(UIEvent("set_surface_range", value=48 / 127, button_id="high"))

        self.assertEqual(ui.analog_pitch_range, (24, 48))
        self.assertEqual(ui.surface_param_binding("stage_01_value")["value"], 24.0)
        self.assertEqual(ui.surface_param_binding("stage_02_value")["value"], 48.0)
        clipped = [action for action in ui.pop_actions() if action.kind == "set_param"]
        self.assertEqual(len(clipped), 16)
        self.assertEqual({action.value for action in clipped}, {24.0, 48.0})

        ui.handle_event(UIEvent("set_surface_value", index=2, value=1.0, pressed=True))
        self.assertEqual(ui.surface_param_binding("stage_03_value")["value"], 48.0)

    def test_touch_layout_maps_pitch_range_horizontally(self):
        layout = TouchLayout(800, 480)
        layout.add_target("range", 100, 100, 256, 30, action_kind="set_surface_range", button_id="low")

        action = layout.action_for_point(227 / 799, 110 / 479)

        self.assertEqual(action.kind, "set_surface_range")
        self.assertEqual(action.button_id, "low")
        self.assertAlmostEqual(action.value, 127 / 255)

    def test_organ_touch_maps_top_to_minus_96_and_bottom_to_zero(self):
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(_snapshot([_organ_instance()]))
        ui.state.ui_mode = "INSTANCE_MENU"
        ui.state.instance_menu_cursor = 1
        ui.handle_event(UIEvent("short_press"))

        ui.handle_event(UIEvent("set_surface_value", index=0, value=0.0, pressed=True))
        self.assertEqual(ui.surface_param_binding("16")["value"], -96.0)
        ui.handle_event(UIEvent("set_surface_value", index=0, value=1.0, pressed=False))
        self.assertEqual(ui.surface_param_binding("16")["value"], 0.0)

    def test_organ_encoder_selects_then_adjusts_in_one_db_steps(self):
        ui = ShadowboxUI()
        instance = _organ_instance()
        instance["params"][0]["value"] = -48.0
        ui.apply_runner_snapshot(_snapshot([instance]))
        ui.state.ui_mode = "INSTANCE_MENU"
        ui.state.instance_menu_cursor = 1
        ui.handle_event(UIEvent("short_press"))

        ui.handle_event(UIEvent("step", 1))
        self.assertEqual(ui.state.surface_focus, 1)
        ui.handle_event(UIEvent("short_press"))
        ui.handle_event(UIEvent("step", 1))

        self.assertEqual(ui.surface_param_binding("5_1_3")["value"], -95.0)

    def test_organ_surface_renders_nine_vertical_touch_targets(self):
        ui = ShadowboxUI()
        instance = _organ_instance()
        next(param for param in instance["params"] if param["name"] == "Nazard")["value"] = 0.0
        ui.apply_runner_snapshot(_snapshot([instance]))
        ui.state.ui_mode = "INSTANCE_MENU"
        ui.state.instance_menu_cursor = 1
        ui.handle_event(UIEvent("short_press"))
        renderer = ShadowboxRenderer(_SurfaceDisplay())
        renderer.set_touch_mode(True)

        renderer.draw(ui)

        targets = [target for target in renderer.touch_layout.targets if target.kind == "organ_drawbar"]
        self.assertEqual(len(targets), 9)
        self.assertTrue(all(target.button_id == "organ_drawbar" for target in targets))
        self.assertLess(targets[0].x, 50)
        self.assertTrue(
            any(op[0] == "fill_rect_color" and op[-1] == (128, 128, 128) for op in renderer.display.ops)
        )

    def test_vertical_surface_target_maps_top_to_one(self):
        layout = TouchLayout(800, 480)
        layout.add_target("stage", 100, 100, 40, 200, action_kind="set_surface_value", index=3)
        top = layout.action_for_point(120 / 799, 100 / 479)
        bottom = layout.action_for_point(120 / 799, 299 / 479)
        self.assertAlmostEqual(top.value, 1.0)
        self.assertAlmostEqual(bottom.value, 0.0)

    def test_organ_vertical_target_maps_top_to_zero(self):
        layout = TouchLayout(800, 480)
        layout.add_target(
            "drawbar",
            100,
            100,
            40,
            200,
            action_kind="set_surface_value",
            index=3,
            button_id="organ_drawbar",
        )
        top = layout.action_for_point(120 / 799, 100 / 479)
        bottom = layout.action_for_point(120 / 799, 299 / 479)
        self.assertAlmostEqual(top.value, 0.0)
        self.assertAlmostEqual(bottom.value, 1.0)

    def test_step16_metadata_remains_parameter_scoped(self):
        instance = {
            "id": "7",
            "name": "SimpleSequencer",
            "params": [_param("steps", metadata={"editor": "step16"})],
            "state": [],
        }
        self.assertIsNone(resolve_instance_surface(instance))

    def test_scope_metadata_no_longer_dispatches_from_parameter_list(self):
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(_snapshot([_scope_instance()]))
        ui.state.ui_mode = "PARAM_LIST"
        ui.state.param_cursor = 1

        ui.handle_event(UIEvent("short_press"))

        self.assertEqual(ui.state.ui_mode, "EDIT")
        self.assertEqual(ui.state.edit_value, 48.0)
        self.assertEqual(ui.state.edit_scope_samples, [])
        self.assertIsNone(RenderScheduler.frame_rate(ui))

    def test_tuner_metadata_no_longer_dispatches_from_parameter_list(self):
        ui = ShadowboxUI()
        ui.apply_runner_snapshot(_snapshot([_tuner_instance()]))
        ui.state.ui_mode = "PARAM_LIST"
        ui.state.param_cursor = 1

        ui.handle_event(UIEvent("short_press"))

        self.assertEqual(ui.state.ui_mode, "EDIT")
        self.assertEqual(ui.state.edit_value, 0.0)
        self.assertIsNone(RenderScheduler.frame_rate(ui))


if __name__ == "__main__":
    unittest.main()

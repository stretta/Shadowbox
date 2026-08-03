from types import SimpleNamespace
import sys
import types


_STUB_MODULE_NAMES = (
    "pythonosc",
    "pythonosc.dispatcher",
    "pythonosc.osc_server",
    "pythonosc.udp_client",
    "shadowbox.display",
    "shadowbox.encoder",
    "shadowbox.renderer",
    "shadowbox.ui",
)
_SAVED_MODULES = {name: sys.modules.get(name) for name in _STUB_MODULE_NAMES}

pythonosc_module = types.ModuleType("pythonosc")
dispatcher_module = types.ModuleType("pythonosc.dispatcher")
osc_server_module = types.ModuleType("pythonosc.osc_server")
udp_client_module = types.ModuleType("pythonosc.udp_client")


class _FakeDispatcher:
    def map(self, *args, **kwargs):
        pass


class _FakeOSCUDPServer:
    def __init__(self, *args, **kwargs):
        self.server_address = ("127.0.0.1", 13333)

    def serve_forever(self):
        pass

    def shutdown(self):
        pass


dispatcher_module.Dispatcher = _FakeDispatcher
osc_server_module.ThreadingOSCUDPServer = _FakeOSCUDPServer
udp_client_module.SimpleUDPClient = object
pythonosc_module.dispatcher = dispatcher_module
pythonosc_module.osc_server = osc_server_module
pythonosc_module.udp_client = udp_client_module
sys.modules.setdefault("pythonosc", pythonosc_module)
sys.modules.setdefault("pythonosc.dispatcher", dispatcher_module)
sys.modules.setdefault("pythonosc.osc_server", osc_server_module)
sys.modules.setdefault("pythonosc.udp_client", udp_client_module)

display_module = types.ModuleType("shadowbox.display")
display_module.load_display_from_env = lambda *args, **kwargs: None
encoder_module = types.ModuleType("shadowbox.encoder")
encoder_module.EncoderInput = object
renderer_module = types.ModuleType("shadowbox.renderer")
renderer_module.create_renderer = lambda *args, **kwargs: None
renderer_module.should_enable_touch_layout = lambda *args, **kwargs: False
ui_module = types.ModuleType("shadowbox.ui")
ui_module.ShadowboxUI = object
sys.modules.setdefault("shadowbox.display", display_module)
sys.modules.setdefault("shadowbox.encoder", encoder_module)
sys.modules.setdefault("shadowbox.renderer", renderer_module)
sys.modules.setdefault("shadowbox.ui", ui_module)

from shadowbox.shadowbox import (
    JACK_CARD_PATH_DEFAULT,
    JACK_RESTART_TIMEOUT_SECONDS,
    JACK_RESTART_PATH_DEFAULT,
    STARTUP_EMPTY_SET_GRACE_SECONDS,
    STARTUP_DISCOVERY_TIMEOUT,
    STARTUP_AUDIO_DEVICE_PRIORITY_DEFAULT,
    _audio_device_priority_from_env,
    _audio_needs_recovery,
    _fanout_transpose,
    _jack_restart_ready,
    _parse_audio_device_priority,
    _preferred_audio_device,
    _report_transpose_delivery,
    _snapshot_ready,
    _snapshot_waiting_for_instances,
    _startup_discovery_timed_out,
    _startup_status_lines,
    _startup_audio_attempt_timed_out,
    _transpose_osc_command,
    _try_startup_audio_device,
    _update_empty_set_settling,
)

for _name, _module in _SAVED_MODULES.items():
    if _module is None:
        sys.modules.pop(_name, None)
    else:
        sys.modules[_name] = _module


class _FakeRNBO:
    def __init__(self):
        self.sent = []
        self.restarted = []
        self.discoveries = 0

    def send_value(self, path, value):
        self.sent.append((path, value))

    def set_audio_device(self, device_name):
        self.send_value(JACK_CARD_PATH_DEFAULT, device_name)

    def restart_jack(self, path):
        self.restarted.append(path)

    def discover(self):
        self.discoveries += 1
        return SimpleNamespace()


class _TransposeRNBO:
    def __init__(self):
        self.sent = []

    def set_param(self, path, value):
        self.sent.append((path, value))


class _FakeUI:
    def __init__(self):
        self.state = SimpleNamespace(
            system={
                "audio": {
                    "card_options": ["USB Audio", "Dummy"],
                    "current_card": "USB Audio",
                    "input_targets": [],
                    "output_targets": [],
                },
                "maint": {},
            }
        )
        self.snapshots = []

    def apply_runner_snapshot(self, snapshot):
        self.snapshots.append(snapshot)


def test_jack_restart_ready_requires_selected_card_and_live_jack_info():
    def snapshot(card, cpu_load):
        return SimpleNamespace(system={"audio": {"current_card": card}, "status": {"cpu_load": cpu_load}})

    assert not _jack_restart_ready(snapshot("hw:USB", None), "hw:USB")
    assert not _jack_restart_ready(snapshot("hw:Dummy", 0.0), "hw:USB")
    assert _jack_restart_ready(snapshot("hw:USB", 0.0), "hw:USB")


def test_startup_audio_restart_uses_full_jack_timeout_window():
    assert STARTUP_DISCOVERY_TIMEOUT == 60.0
    assert not _startup_audio_attempt_timed_out(10.0, 13.0)
    assert _startup_audio_attempt_timed_out(10.0, 10.0 + JACK_RESTART_TIMEOUT_SECONDS)


def test_startup_audio_device_uses_default_restart_path_when_snapshot_lacks_one():
    ui = _FakeUI()
    rnbo = _FakeRNBO()

    assert _try_startup_audio_device(ui, rnbo, "hw:ES8")

    assert rnbo.sent == [(JACK_CARD_PATH_DEFAULT, "hw:ES8")]
    assert rnbo.restarted == [JACK_RESTART_PATH_DEFAULT]
    assert rnbo.discoveries == 0
    assert len(ui.snapshots) == 0


def test_audio_fallback_is_needed_when_current_card_is_not_available():
    audio = {
        "current_card": "hw:ES8",
        "card_options": ["hw:0", "hw:Dummy"],
        "input_targets": ["system:capture_1"],
        "output_targets": ["system:playback_1"],
    }

    assert _audio_needs_recovery(audio)


def test_audio_device_priority_parser_uses_defaults_and_removes_duplicates():
    assert _parse_audio_device_priority(None) == STARTUP_AUDIO_DEVICE_PRIORITY_DEFAULT
    assert _parse_audio_device_priority(" hw:ES8, hw:Dummy,hw:ES8, ") == ("hw:ES8", "hw:Dummy")


def test_legacy_recovery_device_is_used_when_priority_is_unset(monkeypatch):
    monkeypatch.delenv("SHADOWBOX_AUDIO_DEVICE_PRIORITY", raising=False)
    monkeypatch.setenv("SHADOWBOX_STARTUP_AUDIO_RECOVERY_DEVICE", "hw:USB")

    assert _audio_device_priority_from_env() == ("hw:USB",)


def test_preferred_audio_device_uses_order_and_available_cards():
    audio = {"card_options": ["hw:Dummy", "hw:sndrpihifiberry", "hw:ES8"]}

    assert _preferred_audio_device(audio) == "hw:ES8"
    assert _preferred_audio_device(audio, excluded={"hw:ES8"}) == "hw:sndrpihifiberry"


def test_preferred_audio_device_falls_back_to_hifiberry_then_dummy():
    hifiberry = {"card_options": ["hw:Dummy", "hw:sndrpihifiberry"]}
    dummy = {"card_options": ["hw:Dummy"]}
    unavailable = {"card_options": []}

    assert _preferred_audio_device(hifiberry) == "hw:sndrpihifiberry"
    assert _preferred_audio_device(dummy) == "hw:Dummy"
    assert _preferred_audio_device(unavailable) == ""


def test_startup_waits_when_set_is_published_before_instances():
    snapshot = SimpleNamespace(
        instances=[],
        patchers=["ShadowScoreClient"],
        add_instance_path="/rnbo/inst/control/load",
        remove_instance_path="/rnbo/inst/control/unload",
        system={
            "set_name": "Finch",
            "sets": {
                "current_name": "Finch",
                "initial_value": "Finch",
                "auto_start_last": True,
            },
            "status": {"runner_version": "1.4.3"},
            "audio": {"current_card": "hw:Dummy", "card_options": ["hw:Dummy"], "sample_rate_options": [48000]},
            "maint": {"jack_restart_path": "/rnbo/jack/restart"},
        },
    )

    assert _snapshot_waiting_for_instances(snapshot)
    assert not _snapshot_ready(snapshot)
    assert _startup_status_lines(snapshot, stable_passes=0) == ("loading set", "Finch")


def test_startup_accepts_named_set_that_remains_stably_empty():
    snapshot = SimpleNamespace(
        instances=[],
        patchers=["Empty"],
        add_instance_path="/rnbo/inst/control/load",
        remove_instance_path="/rnbo/inst/control/unload",
        system={
            "set_name": "New Blank Graph",
            "sets": {
                "current_name": "New Blank Graph",
                "initial_value": "",
                "auto_start_last": True,
            },
            "status": {"runner_version": "1.4.4"},
            "audio": {"current_card": "hw:Dummy", "card_options": ["hw:Dummy"], "sample_rate_options": [48000]},
            "maint": {"jack_restart_path": "/rnbo/jack/restart"},
        },
    )

    signature, settled_since, allow_empty = _update_empty_set_settling(snapshot, None, None, 10.0)
    assert not allow_empty

    signature, settled_since, allow_empty = _update_empty_set_settling(
        snapshot,
        signature,
        settled_since,
        10.0 + STARTUP_EMPTY_SET_GRACE_SECONDS,
    )

    assert allow_empty
    assert _snapshot_ready(snapshot, allow_empty_set=True)
    assert _startup_status_lines(snapshot, allow_empty_set=True) == ("RNBO found", "stabilizing...")


def test_empty_set_grace_resets_when_runner_snapshot_changes():
    def snapshot(set_name, card="hw:Dummy"):
        return SimpleNamespace(
            instances=[],
            patchers=["Empty"],
            add_instance_path="/rnbo/inst/control/load",
            remove_instance_path="/rnbo/inst/control/unload",
            system={
                "set_name": set_name,
                "sets": {"current_name": set_name, "initial_value": "", "auto_start_last": True},
                "status": {"runner_version": "1.4.4"},
                "audio": {"current_card": card, "card_options": [card], "sample_rate_options": [48000]},
                "maint": {"jack_restart_path": "/rnbo/jack/restart"},
            },
        )

    signature, settled_since, _allow_empty = _update_empty_set_settling(snapshot("Blank A"), None, None, 5.0)
    changed_signature, changed_since, allow_empty = _update_empty_set_settling(
        snapshot("Blank B", card="hw:ES8"),
        signature,
        settled_since,
        5.0 + STARTUP_EMPTY_SET_GRACE_SECONDS,
    )

    assert changed_signature != signature
    assert changed_since == 5.0 + STARTUP_EMPTY_SET_GRACE_SECONDS
    assert not allow_empty


def test_empty_set_grace_clears_when_instances_arrive():
    snapshot = SimpleNamespace(
        instances=[],
        patchers=["Voice"],
        add_instance_path="/rnbo/inst/control/load",
        remove_instance_path="/rnbo/inst/control/unload",
        system={
            "set_name": "Slow Set",
            "sets": {"current_name": "Slow Set", "initial_value": "", "auto_start_last": True},
            "status": {"runner_version": "1.4.4"},
            "audio": {"current_card": "hw:Dummy", "card_options": ["hw:Dummy"], "sample_rate_options": [48000]},
            "maint": {"jack_restart_path": "/rnbo/jack/restart"},
        },
    )
    signature, settled_since, _allow_empty = _update_empty_set_settling(snapshot, None, None, 2.0)
    snapshot.instances = [{"id": "1", "label": "Voice"}]

    signature, settled_since, allow_empty = _update_empty_set_settling(
        snapshot,
        signature,
        settled_since,
        3.0,
    )

    assert signature is None
    assert settled_since is None
    assert not allow_empty
    assert _snapshot_ready(snapshot)


def test_empty_set_grace_ignores_volatile_transport_values():
    snapshot = SimpleNamespace(
        instances=[],
        patchers=["Empty"],
        add_instance_path="/rnbo/inst/control/load",
        remove_instance_path="/rnbo/inst/control/unload",
        system={
            "set_name": "New Blank Graph",
            "sets": {"current_name": "New Blank Graph", "initial_value": "", "auto_start_last": True},
            "status": {"runner_version": "1.4.4"},
            "audio": {"current_card": "hw:Dummy", "card_options": ["hw:Dummy"], "sample_rate_options": [48000]},
            "maint": {"jack_restart_path": "/rnbo/jack/restart"},
            "transport": {"bpm": 120.0, "rolling": False},
        },
    )
    signature, settled_since, _allow_empty = _update_empty_set_settling(snapshot, None, None, 4.0)
    snapshot.system["transport"] = {"bpm": 98.0, "rolling": True}

    unchanged_signature, unchanged_since, allow_empty = _update_empty_set_settling(
        snapshot,
        signature,
        settled_since,
        4.0 + STARTUP_EMPTY_SET_GRACE_SECONDS,
    )

    assert unchanged_signature == signature
    assert unchanged_since == settled_since
    assert allow_empty


def test_startup_timeout_is_not_blocked_by_named_empty_set():
    snapshot = SimpleNamespace(
        instances=[],
        patchers=["Empty"],
        add_instance_path="/rnbo/inst/control/load",
        remove_instance_path="/rnbo/inst/control/unload",
        system={
            "set_name": "New Blank Graph",
            "sets": {"current_name": "New Blank Graph", "initial_value": "", "auto_start_last": True},
            "status": {"runner_version": "1.4.4"},
            "audio": {"current_card": "hw:Dummy", "card_options": ["hw:Dummy"], "sample_rate_options": [48000]},
            "maint": {"jack_restart_path": "/rnbo/jack/restart"},
        },
    )

    assert _startup_discovery_timed_out(0.0, STARTUP_DISCOVERY_TIMEOUT, "", snapshot)


def test_startup_allows_empty_runner_when_no_set_is_expected():
    snapshot = SimpleNamespace(
        instances=[],
        patchers=["Empty"],
        add_instance_path="/rnbo/inst/control/load",
        remove_instance_path="",
        system={
            "set_name": "",
            "sets": {
                "current_name": "",
                "initial_value": "",
                "auto_start_last": False,
            },
            "status": {"runner_version": "1.4.3"},
            "audio": {"current_card": "hw:Dummy", "card_options": ["hw:Dummy"], "sample_rate_options": [48000]},
            "maint": {"jack_restart_path": "/rnbo/jack/restart"},
        },
    )

    assert not _snapshot_waiting_for_instances(snapshot)
    assert _snapshot_ready(snapshot)


def test_transpose_fanout_sends_each_generation_once_and_can_force_replacement():
    ui = SimpleNamespace(
        state=SimpleNamespace(
            transpose_authority="standalone",
            instances=[
                {
                    "id": "1",
                    "name": "Voice A",
                    "params": [
                        {
                            "name": "ChromaticTranspose",
                            "path": "/rnbo/inst/1/params/ChromaticTranspose",
                            "value": 0,
                            "min": -12,
                            "max": 12,
                        }
                    ],
                }
            ]
        )
    )
    rnbo = _TransposeRNBO()
    delivered = {}

    assert _fanout_transpose(ui, rnbo, "chromatic", 3, delivered) == (1, 0)
    assert _fanout_transpose(ui, rnbo, "chromatic", 3, delivered) == (0, 0)
    assert _fanout_transpose(ui, rnbo, "chromatic", 3, delivered, force_instance_ids={"1"}) == (1, 0)
    assert rnbo.sent == [
        ("/rnbo/inst/1/params/ChromaticTranspose", 3),
        ("/rnbo/inst/1/params/ChromaticTranspose", 3),
    ]


def test_transpose_fanout_reports_out_of_range_without_clamping():
    ui = SimpleNamespace(
        state=SimpleNamespace(
            transpose_authority="standalone",
            instances=[
                {
                    "id": "1",
                    "params": [
                        {"name": "ScalarTranspose", "path": "/scalar", "value": 0, "min": -7, "max": 7}
                    ],
                }
            ]
        )
    )
    rnbo = _TransposeRNBO()

    assert _fanout_transpose(ui, rnbo, "scalar", 8, {}) == (0, 1)
    assert rnbo.sent == []


def test_transpose_delivery_feedback_is_quiet_when_no_target_participates():
    ui = SimpleNamespace(status_messages=[], set_status_message=lambda message: ui.status_messages.append(message))

    _report_transpose_delivery(ui, 0)

    assert ui.status_messages == []


def test_transpose_delivery_feedback_reports_published_target_range_failure():
    ui = SimpleNamespace(status_messages=[], set_status_message=lambda message: ui.status_messages.append(message))

    _report_transpose_delivery(ui, 2)

    assert ui.status_messages == ["2 transpose target out of range"]


def test_source_aware_transpose_osc_command_preserves_declared_source():
    assert _transpose_osc_command("/shadowbox/transpose/chromatic", [4, "GraphEditor"]) == (
        "chromatic",
        4,
        "GraphEditor",
    )
    assert _transpose_osc_command("/shadowbox/transpose/scalar", -2) == ("scalar", -2, "External OSC")
    assert _transpose_osc_command("/rnbo/inst/1/params/ScalarTranspose", 2) is None

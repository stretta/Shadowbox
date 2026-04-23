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
ui_module = types.ModuleType("shadowbox.ui")
ui_module.ShadowboxUI = object
sys.modules.setdefault("shadowbox.display", display_module)
sys.modules.setdefault("shadowbox.encoder", encoder_module)
sys.modules.setdefault("shadowbox.renderer", renderer_module)
sys.modules.setdefault("shadowbox.ui", ui_module)

from shadowbox.shadowbox import (
    JACK_CARD_PATH_DEFAULT,
    JACK_RESTART_PATH_DEFAULT,
    _audio_needs_dummy_fallback,
    _try_dummy_audio_fallback,
    _try_startup_audio_recovery,
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


def test_startup_audio_recovery_sends_default_runner_paths():
    rnbo = _FakeRNBO()

    assert _try_startup_audio_recovery(rnbo, "Dummy")

    assert rnbo.sent == [(JACK_CARD_PATH_DEFAULT, "Dummy")]
    assert rnbo.restarted == [JACK_RESTART_PATH_DEFAULT]


def test_startup_audio_recovery_ignores_blank_device_name():
    rnbo = _FakeRNBO()

    assert not _try_startup_audio_recovery(rnbo, "")

    assert rnbo.sent == []
    assert rnbo.restarted == []


def test_dummy_audio_fallback_uses_default_restart_path_when_snapshot_lacks_one():
    ui = _FakeUI()
    rnbo = _FakeRNBO()

    assert _try_dummy_audio_fallback(ui, rnbo)

    assert rnbo.sent == [(JACK_CARD_PATH_DEFAULT, "Dummy")]
    assert rnbo.restarted == [JACK_RESTART_PATH_DEFAULT]
    assert rnbo.discoveries == 1
    assert len(ui.snapshots) == 1


def test_audio_fallback_is_needed_when_current_card_is_not_available():
    audio = {
        "current_card": "hw:ES8",
        "card_options": ["hw:0", "hw:Dummy"],
        "input_targets": ["system:capture_1"],
        "output_targets": ["system:playback_1"],
    }

    assert _audio_needs_dummy_fallback(audio)

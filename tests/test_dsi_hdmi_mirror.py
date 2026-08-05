import importlib.util
import types
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "configure_dsi_hdmi_mirror.py"
SPEC = importlib.util.spec_from_file_location("configure_dsi_hdmi_mirror", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC is not None
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class _Object:
    def __init__(self, **values):
        self.__dict__.update(values)


class _Plane(_Object):
    def get_prop_value(self, name):
        return {"CRTC_ID": 90, "FB_ID": 721}[name]


class _Request:
    def __init__(self, _card):
        self.properties = None

    def add(self, _plane, properties):
        self.properties = properties

    def test(self):
        return 0

    def commit_sync(self):
        return 0


class DSIHDMIMirrorTests(unittest.TestCase):
    def test_configures_active_primary_dsi_plane(self) -> None:
        crtc = _Object(id=90)
        connector = _Object(fullname="DSI-1", connected=True, get_current_crtc=lambda: crtc)
        plane = _Plane(id=79, plane_type="primary")
        card = _Object(connectors=[connector], planes=[plane])
        pykms = types.SimpleNamespace(
            Card=lambda: card,
            PlaneType=types.SimpleNamespace(Primary="primary"),
            AtomicReq=_Request,
        )

        result = MODULE.configure_mirror(
            pykms,
            connector_name="DSI-1",
            source_width=1920,
            source_height=1080,
            destination_width=800,
            destination_height=480,
        )

        self.assertEqual(result["plane_id"], 79)
        self.assertEqual(result["source_width"], 1920)
        self.assertFalse(result["test_only"])

    def test_rejects_missing_connector(self) -> None:
        card = _Object(connectors=[], planes=[])
        pykms = types.SimpleNamespace(Card=lambda: card)

        with self.assertRaisesRegex(RuntimeError, "not connected"):
            MODULE.configure_mirror(
                pykms,
                connector_name="DSI-1",
                source_width=1920,
                source_height=1080,
                destination_width=800,
                destination_height=480,
            )


if __name__ == "__main__":
    unittest.main()

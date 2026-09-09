from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from shadowbox.shadowscore_transport import shadowscore_transport_urls


class ShadowScoreTransportTests(unittest.TestCase):
    def test_url_resolution_prefers_override_then_local_and_discovered_coordinator(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = root / "registration-state.json"
            config = root / "peer.json"
            state.write_text(json.dumps({"sessionHostUrl": "http://wren.local:8790/"}), encoding="utf-8")
            config.write_text(json.dumps({"registration": {"sessionHostUrl": "http://manual.local:8790"}}), encoding="utf-8")
            self.assertEqual(
                shadowscore_transport_urls(
                    environ={"SHADOWBOX_SHADOWSCORE_URL": "http://override.local:8790/"},
                    registration_state=state,
                    peer_config=config,
                ),
                [
                    "http://override.local:8790",
                    "http://127.0.0.1:8790",
                    "http://wren.local:8790",
                    "http://manual.local:8790",
                ],
            )

if __name__ == "__main__":
    unittest.main()

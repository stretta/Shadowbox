from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from shadowbox.shadowscore_transport import (
    notify_shadowscore_transport,
    notify_shadowscore_transport_async,
    shadowscore_transport_urls,
)


class _Response:
    def __init__(self, status: int = 200):
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


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

    def test_notification_falls_through_to_coordinator_and_sends_explicit_intent(self) -> None:
        requests = []

        def opener(request, timeout):
            requests.append((request, timeout))
            if len(requests) == 1:
                raise OSError("local server unavailable")
            return _Response()

        self.assertTrue(
            notify_shadowscore_transport(
                True,
                unit_id="finch",
                urls=["http://127.0.0.1:8790", "http://wren.local:8790"],
                opener=opener,
            )
        )
        request, timeout = requests[-1]
        self.assertEqual(request.full_url, "http://wren.local:8790/transport/external")
        self.assertEqual(timeout, 0.5)
        self.assertEqual(
            json.loads(request.data.decode("utf-8")),
            {"source": "shadowbox", "unitId": "finch", "rolling": True},
        )

    def test_async_notification_starts_daemon_worker_without_blocking(self) -> None:
        created = []

        class FakeThread:
            def __init__(self, **kwargs):
                created.append(kwargs)

            def start(self):
                created[-1]["started"] = True

        notify_shadowscore_transport_async(False, unit_id="wren", thread_factory=FakeThread)
        self.assertTrue(created[0]["daemon"])
        self.assertTrue(created[0]["started"])
        self.assertEqual(created[0]["kwargs"], {"rolling": False, "unit_id": "wren"})


if __name__ == "__main__":
    unittest.main()

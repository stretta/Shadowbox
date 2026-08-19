from __future__ import annotations

import json
import io
import unittest
import urllib.error

from shadowbox.shadowscore_transport_client import (
    ShadowScoreTransportCoordinator,
    parse_sse_events,
    transport_error_message,
)


class _Response:
    def __init__(self, body: bytes):
        self.body = body

    def read(self):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class ShadowScoreTransportClientTests(unittest.TestCase):
    def test_sse_parser_yields_named_json_events_and_ignores_comments(self) -> None:
        events = list(parse_sse_events(iter([
            b": keepalive\n",
            b"event: snapshot\n",
            b'data: {"revision":4,\n',
            b'data: "is_playing":true}\n',
            b"\n",
        ])))
        self.assertEqual(events, [("snapshot", {"revision": 4, "is_playing": True})])

    def test_command_worker_uses_canonical_envelope_and_returns_object(self) -> None:
        requests = []

        def opener(request, timeout):
            requests.append((request, timeout))
            return _Response(json.dumps({"object": {"revision": 8, "is_playing": True}}).encode())

        coordinator = ShadowScoreTransportCoordinator(
            urls=["http://wren.local:8790"],
            unit_id="wren",
            opener=opener,
        )
        coordinator.request("play")
        coordinator._jobs.put(None)
        coordinator._run_commands()

        result = coordinator.drain()[0]
        request, timeout = requests[0]
        payload = json.loads(request.data.decode())
        self.assertEqual(request.full_url, "http://wren.local:8790/api/v1/objects/transport")
        self.assertEqual(request.method, "POST")
        self.assertEqual(payload["client_id"], "shadowbox-wren")
        self.assertEqual(payload["operation"], "play")
        self.assertEqual(payload["args"], {})
        self.assertTrue(payload["request_id"])
        self.assertEqual(timeout, 30.0)
        self.assertEqual(result.kind, "command")
        self.assertEqual(result.snapshot["revision"], 8)

    def test_http_error_body_becomes_concise_actionable_front_panel_message(self) -> None:
        error = urllib.error.HTTPError(
            "http://wren:8790/api/v1/objects/transport",
            400,
            "Bad Request",
            {},
            io.BytesIO(json.dumps({
                "error": "RNBO playback is not ready: finch:24 saved-not-active, heron:16 saved-not-active"
            }).encode()),
        )
        self.assertEqual(
            transport_error_message(error, operation="play"),
            "PLAY FAILED · 2 CLIENTS NOT READY",
        )


if __name__ == "__main__":
    unittest.main()

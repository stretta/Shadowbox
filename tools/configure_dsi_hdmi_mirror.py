#!/usr/bin/env python3
"""Scale the shared HDMI framebuffer onto the Shadowbox DSI connector."""

from __future__ import annotations

import argparse
import json
import signal


_ACTIVE_RESOURCES = None


def configure_mirror(
    pykms,
    *,
    connector_name: str,
    source_width: int,
    source_height: int,
    destination_width: int,
    destination_height: int,
    test_only: bool = False,
) -> dict[str, int | str | bool]:
    global _ACTIVE_RESOURCES
    card = pykms.Card()
    connector = next((item for item in card.connectors if item.fullname == connector_name), None)
    if connector is None or not connector.connected:
        raise RuntimeError(f"KMS connector {connector_name!r} is not connected")

    crtc = connector.get_current_crtc()
    if crtc is None:
        raise RuntimeError(f"KMS connector {connector_name!r} has no active CRTC")

    planes = [
        plane
        for plane in card.planes
        if plane.get_prop_value("CRTC_ID") == crtc.id and plane.get_prop_value("FB_ID") != 0
    ]
    plane = next((item for item in planes if item.plane_type == pykms.PlaneType.Primary), None)
    if plane is None:
        raise RuntimeError(f"KMS connector {connector_name!r} has no active primary plane")

    properties = {
        "SRC_X": 0,
        "SRC_Y": 0,
        "SRC_W": source_width << 16,
        "SRC_H": source_height << 16,
        "CRTC_X": 0,
        "CRTC_Y": 0,
        "CRTC_W": destination_width,
        "CRTC_H": destination_height,
    }
    request = pykms.AtomicReq(card)
    request.add(plane, properties)
    result = request.test() if test_only else request.commit_sync()
    if result != 0:
        action = "validate" if test_only else "configure"
        raise RuntimeError(f"Could not {action} KMS plane scaling: result {result}")

    # Keep the DRM fd and objects alive. Raspberry Pi's fbdev client restores
    # its original plane rectangle when the KMS client releases ownership.
    _ACTIVE_RESOURCES = (card, connector, crtc, plane, request)

    return {
        "connector": connector.fullname,
        "crtc_id": crtc.id,
        "plane_id": plane.id,
        "source_width": source_width,
        "source_height": source_height,
        "destination_width": destination_width,
        "destination_height": destination_height,
        "test_only": test_only,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--connector", default="DSI-1")
    parser.add_argument("--source-width", type=int, required=True)
    parser.add_argument("--source-height", type=int, required=True)
    parser.add_argument("--destination-width", type=int, required=True)
    parser.add_argument("--destination-height", type=int, required=True)
    parser.add_argument("--test-only", action="store_true")
    parser.add_argument("--hold", action="store_true", help="retain KMS ownership until terminated")
    args = parser.parse_args()

    import pykms

    result = configure_mirror(
        pykms,
        connector_name=args.connector,
        source_width=args.source_width,
        source_height=args.source_height,
        destination_width=args.destination_width,
        destination_height=args.destination_height,
        test_only=args.test_only,
    )
    print(json.dumps(result, sort_keys=True), flush=True)
    if args.hold and not args.test_only:
        while True:
            signal.pause()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import json
import os
from pathlib import Path


DEFAULT_SHADOWSCORE_URL = "http://127.0.0.1:8790"
DEFAULT_REGISTRATION_STATE = Path("/home/pi/ShadowscoreServer/data/registration-state.json")
DEFAULT_PEER_CONFIG = Path("/home/pi/ShadowscoreServer/config/shadowbox.hardware-peer.json")


def shadowscore_transport_urls(
    *,
    environ: dict[str, str] | None = None,
    registration_state: Path = DEFAULT_REGISTRATION_STATE,
    peer_config: Path = DEFAULT_PEER_CONFIG,
) -> list[str]:
    env = os.environ if environ is None else environ
    candidates = [env.get("SHADOWBOX_SHADOWSCORE_URL", ""), DEFAULT_SHADOWSCORE_URL]
    candidates.extend(_urls_from_json(registration_state, ("sessionHostUrl",)))
    candidates.extend(_urls_from_json(peer_config, ("registration", "sessionHostUrl")))
    urls = []
    for candidate in candidates:
        url = str(candidate or "").strip().rstrip("/")
        if url and url not in urls:
            urls.append(url)
    return urls

def _urls_from_json(path: Path, keys: tuple[str, ...]) -> list[str]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        for key in keys:
            value = value[key]
        return [str(value)] if value else []
    except (OSError, ValueError, TypeError, KeyError):
        return []

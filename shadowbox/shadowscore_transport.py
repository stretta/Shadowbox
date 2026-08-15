from __future__ import annotations

import json
import os
import socket
import urllib.request
from pathlib import Path
from threading import Thread
from typing import Callable


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


def notify_shadowscore_transport(
    rolling: bool,
    *,
    unit_id: str | None = None,
    urls: list[str] | None = None,
    timeout: float = 0.5,
    opener: Callable = urllib.request.urlopen,
) -> bool:
    payload = json.dumps(
        {
            "source": "shadowbox",
            "unitId": str(unit_id or socket.gethostname()).strip(),
            "rolling": bool(rolling),
        },
        separators=(",", ":"),
    ).encode("utf-8")
    for base_url in urls or shadowscore_transport_urls():
        request = urllib.request.Request(
            f"{base_url.rstrip('/')}/transport/external",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with opener(request, timeout=timeout) as response:
                status = int(getattr(response, "status", 200))
                if 200 <= status < 300:
                    return True
        except Exception:
            continue
    return False


def notify_shadowscore_transport_async(
    rolling: bool,
    *,
    unit_id: str | None = None,
    thread_factory: Callable = Thread,
) -> None:
    thread = thread_factory(
        target=notify_shadowscore_transport,
        kwargs={"rolling": bool(rolling), "unit_id": unit_id},
        daemon=True,
    )
    thread.start()


def _urls_from_json(path: Path, keys: tuple[str, ...]) -> list[str]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        for key in keys:
            value = value[key]
        return [str(value)] if value else []
    except (OSError, ValueError, TypeError, KeyError):
        return []

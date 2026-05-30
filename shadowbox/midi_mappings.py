from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


MIDI_MAPPINGS_PATH = Path.home() / "rnbo-ui" / "midi_mappings.json"


def _profile_name(instance: dict | None) -> str:
    if not isinstance(instance, dict):
        return ""
    for key in ("name", "label", "id"):
        value = str(instance.get(key, "") or "").strip()
        if value:
            return value
    return ""


def _normalize_midi_mapping(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}

    mapping: dict[str, Any] = {}
    for key in ("chan", "ctrl"):
        item = value.get(key)
        if isinstance(item, bool):
            continue
        if isinstance(item, (int, float)):
            mapping[key] = int(item) if float(item).is_integer() else item
        elif isinstance(item, str) and item.strip():
            try:
                numeric = float(item.strip())
                mapping[key] = int(numeric) if numeric.is_integer() else numeric
            except ValueError:
                continue
    return mapping


def collect_instance_midi_mappings(instance: dict | None) -> dict[str, dict[str, Any]]:
    if not isinstance(instance, dict):
        return {}

    mappings: dict[str, dict[str, Any]] = {}
    for param in instance.get("params", []):
        if not isinstance(param, dict):
            continue
        name = str(param.get("name", "") or "").strip()
        metadata = param.get("metadata", {})
        midi = metadata.get("midi") if isinstance(metadata, dict) else None
        mapping = _normalize_midi_mapping(midi)
        if name and mapping:
            mappings[name] = mapping
    return mappings


def load_mapping_store(path: Path = MIDI_MAPPINGS_PATH) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    if not isinstance(data, dict):
        data = {}
    data.setdefault("version", 1)
    profiles = data.get("profiles")
    if not isinstance(profiles, dict):
        data["profiles"] = {}
    return data


def save_mapping_store(data: dict[str, Any], path: Path = MIDI_MAPPINGS_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp_path.replace(path)


def save_instance_midi_profile(instance: dict | None, path: Path = MIDI_MAPPINGS_PATH, *, allow_empty: bool = False) -> int:
    profile_name = _profile_name(instance)
    mappings = collect_instance_midi_mappings(instance)
    if not profile_name or (not mappings and not allow_empty):
        return 0

    store = load_mapping_store(path)
    store["profiles"][profile_name] = {
        "patcher": profile_name,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "params": mappings,
    }
    save_mapping_store(store, path)
    return len(mappings)


def mapping_profile_for_instance(instance: dict | None, path: Path = MIDI_MAPPINGS_PATH) -> dict[str, dict[str, Any]]:
    profile_name = _profile_name(instance)
    if not profile_name:
        return {}

    store = load_mapping_store(path)
    profile = store.get("profiles", {}).get(profile_name, {})
    params = profile.get("params") if isinstance(profile, dict) else None
    if not isinstance(params, dict):
        return {}

    mappings: dict[str, dict[str, Any]] = {}
    for name, value in params.items():
        mapping = _normalize_midi_mapping(value)
        if mapping:
            mappings[str(name)] = mapping
    return mappings


def apply_midi_profile_to_instance(instance: dict | None, rnbo, path: Path = MIDI_MAPPINGS_PATH) -> int:
    mappings = mapping_profile_for_instance(instance, path)
    if not isinstance(instance, dict) or not mappings:
        return 0

    applied = 0
    for param in instance.get("params", []):
        if not isinstance(param, dict):
            continue
        name = str(param.get("name", "") or "").strip()
        param_path = str(param.get("path", "") or "").strip()
        if not name or not param_path or name not in mappings:
            continue

        metadata = param.get("metadata", {})
        next_metadata = dict(metadata) if isinstance(metadata, dict) else {}
        next_metadata["midi"] = mappings[name]
        rnbo.send_value(f"{param_path}/meta", json.dumps(next_metadata, separators=(",", ":")))
        applied += 1
    return applied

#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path


ROOT_NAMES = [
    "C", "C#", "D", "Eb", "E", "F",
    "F#", "G", "Ab", "A", "Bb", "B",
]

WHITE_PCS = [0, 2, 4, 5, 7, 9, 11]
BLACK_PCS = [1, 3, 6, 8, 10]


def is_ttid_param(param: dict) -> bool:
    name = str(param.get("name", "")).strip().lower()
    ptype = str(param.get("type", "")).strip().lower()
    return (
        ptype == "ttid"
        or name == "ttid"
        or name.endswith("/ttid")
        or "/ttid/" in name
    )


def get_root_names() -> list[str]:
    return ROOT_NAMES[:]


def note_name(pc: int) -> str:
    return ROOT_NAMES[int(pc) % 12]


def default_scales_path() -> Path:
    return Path(__file__).resolve().parent / "data" / "scales.json"


def load_scales(path: str | Path | None = None) -> dict:
    p = Path(path) if path is not None else default_scales_path()
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text())
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {}


def get_scale_names(path: str | Path | None = None) -> list[str]:
    scales = load_scales(path)
    return sorted(scales.keys(), key=str.lower)


def normalize_mask(value: int) -> int:
    return int(value) & 0xFFF


def normalize_ttid(value: int) -> int:
    return normalize_mask(value)


def is_pc_on(ttid: int, pc: int) -> bool:
    if ttid is None:
        return False
    return (int(ttid) & (1 << (int(pc) % 12))) != 0


def toggle_pc(ttid: int, pc: int) -> int:
    if ttid is None:
        ttid = 0
    return int(ttid) ^ (1 << (int(pc) % 12))

def toggle_bit(ttid: int, pc: int) -> int:
    return toggle_pc(ttid, pc)

def normalize_ttid(value: int) -> int:
    return normalize_mask(value)

def apply_scale_to_mask(root_index: int, scale_name: str, path: str | Path | None = None) -> int:
    return encode_scale_to_mask(root_index, scale_name, path)

def set_pc(ttid: int, pc: int, enabled: bool) -> int:
    if ttid is None:
        ttid = 0
    bit = 1 << (int(pc) % 12)
    if enabled:
        return int(ttid) | bit
    return int(ttid) & ~bit


def encode_scale_to_mask(root_index: int, scale_name: str, path: str | Path | None = None) -> int:
    scales = load_scales(path)
    pcs = scales.get(scale_name, [])
    if not isinstance(pcs, list):
        return 0

    root_index = int(root_index) % 12
    mask = 0
    for pc in pcs:
        shifted = (int(pc) + root_index) % 12
        mask |= (1 << shifted)

    return normalize_mask(mask)


def apply_scale_to_mask(root_index: int, scale_name: str, path: str | Path | None = None) -> int:
    return encode_scale_to_mask(root_index, scale_name, path)

#!/usr/bin/env python3

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


@dataclass(frozen=True)
class ResolvedSurface:
    instance_id: str
    params: dict[str, dict] = field(default_factory=dict)
    state: dict[str, dict] = field(default_factory=dict)


SurfaceResolver = Callable[[dict], ResolvedSurface | None]


@dataclass(frozen=True)
class InstanceSurfaceSpec:
    key: str
    title: str
    export_names: frozenset[str]
    resolve: SurfaceResolver
    frame_rate: float | None = None

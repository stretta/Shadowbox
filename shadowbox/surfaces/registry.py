#!/usr/bin/env python3

from __future__ import annotations

from shadowbox.surfaces.analog_sequencer import resolve_analog_sequencer_bindings
from shadowbox.surfaces.base import InstanceSurfaceSpec, ResolvedSurface
from shadowbox.surfaces.organ import resolve_organ_bindings
from shadowbox.surfaces.time_domain_scope import resolve_time_domain_scope_bindings
from shadowbox.surfaces.tuner import resolve_tuner_bindings


SURFACE_SPECS = (
    InstanceSurfaceSpec("organ", "ORGAN", frozenset({"Organ"}), resolve_organ_bindings, None),
    InstanceSurfaceSpec(
        "analog_sequencer",
        "ANALOG SEQUENCER",
        frozenset({"AnalogSequencer"}),
        resolve_analog_sequencer_bindings,
        20.0,
    ),
    InstanceSurfaceSpec(
        "time_domain_scope",
        "TIME DOMAIN SCOPE",
        frozenset({"TimeDomainScope"}),
        resolve_time_domain_scope_bindings,
        15.0,
    ),
    InstanceSurfaceSpec("tuner", "TUNER", frozenset({"Tuner"}), resolve_tuner_bindings, 20.0),
)

_BY_KEY = {spec.key: spec for spec in SURFACE_SPECS}


def surface_spec_for_instance(instance: dict | None) -> InstanceSurfaceSpec | None:
    if not isinstance(instance, dict):
        return None
    export_name = str(instance.get("name", ""))
    return next((spec for spec in SURFACE_SPECS if export_name in spec.export_names), None)


def resolve_instance_surface(instance: dict | None) -> tuple[InstanceSurfaceSpec, ResolvedSurface] | None:
    spec = surface_spec_for_instance(instance)
    if spec is None or instance is None:
        return None
    resolved = spec.resolve(instance)
    return (spec, resolved) if resolved is not None else None


def surface_spec_for_key(key: str) -> InstanceSurfaceSpec | None:
    return _BY_KEY.get(str(key))

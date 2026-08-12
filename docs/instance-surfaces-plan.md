# Instance Surfaces Development Plan

## Implementation status

The instance-surfaces plan is implemented:

- Static canonical-name registry and compatibility resolvers
- Independent `INSTANCE_SURFACE` UI state and navigation
- Snapshot re-resolution and safe fallback when a contract disappears
- Surface-specific render cadence
- Time Domain Scope and Tuner instance-surface migrations
- Contract-driven 16-stage Analog Sequencer surface
- OSC-inport-driven ListSequencer surface with ACK readback
- Eight-row ListVelSequencer surface with pitch-map context and ACK readback
- Read-only ShadowScoreClient musical playback surface with current chord,
  zero-based stage, recent-event history, lifecycle state, and last MIDI output
- Removal of the obsolete Scope and Tuner parameter-editor dispatch routes
- Automated registry, lifecycle, navigation, touch, rendering, and cadence
  coverage

The remainder of this document preserves the original phased design rationale.
Future-tense phase text is historical; the current runtime contract is defined
by `shadowbox/surfaces/`, `shadowbox/ui.py`, and the summary above.

The Organ surface uses the live `wren` export contract: `Bass`, `Quint`,
`Neutral`, `Octave`, `Nazard`, `Block-flute`, `Tierce`, `Larigot`, and
`Sifflute` are continuous `-96..0 dB` parameters mapped to the canonical
footages. `-96 dB` is the top/off position and `0 dB` is the bottom/full-on
position.

## Purpose

Shadowbox currently selects custom editors through individual RNBO parameters.
That model remains appropriate when a surface is fundamentally an alternate
representation of one parameter, such as TTID or the Trigger Sequencer's
`steps` parameter.

Some interfaces instead represent an RNBO export as a whole. They may bind
multiple parameters, combine editable parameters with runtime state, or present
a device-level visual metaphor. This plan introduces **instance surfaces** for
those interfaces.

Initial instance surfaces:

- Organ
- Analog Sequencer
- Time Domain Scope
- Tuner
- ListSequencer

Existing parameter editors that remain parameter-scoped:

- Numeric, boolean, and enum editors
- TTID
- Trigger Sequencer / `step16`

The distinction is semantic rather than simply based on parameter count. Time
Domain Scope and Tuner can be instance surfaces even if each currently uses a
single editable anchor parameter, because their visible experience represents
the complete device and consumes additional runtime state.

## Design decisions

### Surface identification

Shadowbox will maintain a static registry keyed by the canonical RNBO export
name:

```text
Organ             -> organ
AnalogSequencer   -> analog_sequencer
TimeDomainScope   -> time_domain_scope
Tuner             -> tuner
ListSequencer     -> list_sequencer
```

Resolution must use the instance's exported patcher `name`, not its mutable
instance label or JACK name.

This first implementation does not depend on export-level custom metadata, a
dummy parameter, or a general dynamic layout schema. Runtime validation of the
expected parameter and state contract protects against an export name being
reused for an incompatible device.

### Navigation

An instance with a valid surface will expose a surface-specific entry in its
instance menu:

```text
..
ORGAN
PARAMETERS
PRESETS
AUDIO
MIDI
```

The normal `PARAMETERS` entry remains available for comprehensive access and
debugging. Initially, selecting an instance will not automatically open its
surface. A later preference may make a registered surface the default
destination on touch hardware.

### UI ownership

Instance surfaces will use an `INSTANCE_SURFACE` UI mode independent of the
parameter-oriented `EDIT` mode. Surface state must not be represented through
`param_cursor` or `selected_param`.

New UI state will include, at minimum:

```text
active_surface_key
surface_focus
surface_state
surface_touch_capture
```

Back, short press, and long press should return to the instance menu unless a
particular surface explicitly defines another interaction.

## Phase 1: Instance-surface infrastructure

Add a small static surface API and registry:

```text
shadowbox/surfaces/
    __init__.py
    base.py
    registry.py
    organ.py
    analog_sequencer.py
    time_domain_scope.py
    tuner.py
    list_sequencer.py
```

This should remain an internal API rather than becoming a general plug-in
system in the first pass.

A registration will describe the export identity, title, binding resolver, and
render cadence:

```python
InstanceSurfaceSpec(
    key="organ",
    title="ORGAN",
    export_names={"Organ"},
    resolve=resolve_organ_bindings,
    frame_rate=None,
)
```

The resolver examines the discovered instance and either rejects it or returns
semantic bindings:

```python
ResolvedSurface(
    instance_id="34",
    params={
        "drawbar_16": "/rnbo/inst/34/params/...",
        "drawbar_5_1_3": "/rnbo/inst/34/params/...",
    },
    state={},
)
```

The resolver is the compatibility check. If required parameters or runtime
state are absent or ambiguous, Shadowbox will not offer the surface and will
retain the ordinary parameter interface.

### Lifecycle and refresh behavior

Each surface is responsible for:

- Resolving current parameter and state bindings
- Initializing and cleaning up surface-local state
- Interpreting encoder and touch events
- Rendering with existing renderer primitives

Bindings should be stored primarily as stable parameter names or OSC paths,
not references to discovered parameter dictionaries. Discovery refreshes can
replace those dictionaries.

On every Runner snapshot, Shadowbox will:

1. Re-resolve the active surface against the current instance.
2. Preserve focus and transient state when the contract remains valid.
3. Update displayed values from the latest discovered parameters and state.
4. Exit safely to the instance menu if the instance disappears or becomes
   incompatible.

Surface parameter changes will continue through the existing `set_param`
action mechanism.

### Render scheduling

The active surface will declare its animation requirements:

- Organ: event-driven rendering
- Tuner: approximately 20 fps while active
- Time Domain Scope: approximately 15 fps while active
- Analog Sequencer: approximately 20 fps while its playhead is moving

This will replace scheduler logic that recognizes special editors by inspecting
`selected_param`.

## Phase 2: Organ vertical slice

Organ is the first complete instance surface. It exercises multi-parameter
binding, canonical ordering, specialized rendering, continuous touch
interaction, encoder fallback, and live OSC updates.

### Parameter resolution

Drawbar identity will be derived from normalized parameter names rather than
parameter enumeration order.

The resolver will recognize the canonical footages and arrange them in fixed
Hammond order:

| Position | Footage | Color |
| ---: | ---: | --- |
| 1 | 16' | brown |
| 2 | 5 1/3' | brown |
| 3 | 8' | white |
| 4 | 4' | white |
| 5 | 2 2/3' | black |
| 6 | 2' | white |
| 7 | 1 3/5' | black |
| 8 | 1 1/3' | black |
| 9 | 1' | white |

The parser recognizes the semantic names used by the current export:

```text
Bass
Quint
Neutral
Octave
Nazard
Block-flute
Tierce
Larigot
Sifflute
```

The RNBO-safe `Drawbar16`, `Drawbar5_1_3`, and related spellings remain
accepted when they publish one complete, unambiguous drawbar bank.

Before implementation, the live Organ export on `wren` will be inspected to
confirm its exact parameter names, ranges, and step behavior.

The resolver will require one unambiguous parameter for each footage. Missing
or duplicate footage will reject the surface instead of silently producing an
incorrect layout. Other Organ parameters will remain accessible through the
normal parameter list.

### Drawbar behavior

The control geometry is reversed relative to a conventional vertical slider:

```text
top    = -96 dB, fully pushed in/off
bottom = 0 dB, fully pulled out/full-on
```

The current dB value mapping is therefore:

```python
fraction = (touch_y - track_top) / track_height
value = minimum + fraction * (maximum - minimum)
```

The fraction must not be inverted.

The initial drawbar contract is:

- Parameter range is continuous `-96..0 dB`
- `-96 dB` is fully pushed in/off at the top
- `0 dB` is fully pulled out/full-on at the bottom
- Touch immediately moves the selected drawbar
- Vertical dragging updates it live
- Visual movement happens immediately without waiting for OSCQuery readback
- Runner readback remains authoritative and reconciles the displayed value

The current direct-touch path already emits continuous samples for the
horizontal numeric slider. Instance surfaces will generalize it to support:

- Touch targets whose values are derived from the vertical axis
- Pointer capture, so a gesture remains assigned to the drawbar where it began
- Coalescing to the latest value per drawbar per input/render cycle

Coalescing preserves responsive local motion without emitting every raw
touchscreen sample as an OSC write.

### Organ rendering

The 800x480 touchscreen layout will:

- Display nine full-height drawbars in one horizontal bank
- Preserve the canonical Hammond order and colors
- Show the footage for each drawbar
- Give black and brown drawbars visible outlines against the dark background
- Make the complete shaft a generous touch target
- Show the pulled portion extending downward from the zero position

Encoder fallback will provide:

- Turning in selection mode changes the focused drawbar
- Short press enters value adjustment
- Turning adjusts the focused drawbar in `1 dB` steps
- Short press returns to drawbar selection
- Long press or back exits the surface

The touchscreen is the primary Organ interface, but the surface must remain
usable and escapable on encoder-only Shadowboxes.

## Phase 3: Time Domain Scope migration

Move scope entry from a tagged selected parameter in `EDIT` to the
`TimeDomainScope` instance surface.

Its resolver will bind:

- The sample-rate or other editable control parameter
- The scope message-out stream
- Any other required display state

Reuse the current sample buffer, time-window calculation, rendering, and OSC
update behavior. The migration primarily relocates ownership from
`selected_param` and generic `EDIT` state into a surface session.

The former parameter-triggered route was removed after live instance-surface
verification.

## Phase 4: Tuner migration

The Tuner surface will bind:

- Pitch or note state
- Cents state
- Any reference-frequency or calibration parameter
- Any viewer or enable control currently acting as an anchor

This phase proves that an instance surface can primarily be a viewer rather
than a bank of controls.

The former `pitch_display` parameter-editor route was removed after live
instance-surface verification.

## Phase 5: Analog Sequencer surface

`AnalogSequencer` is a separate RNBO export and will receive its own instance
surface. It must not be modeled as an extension of the Trigger Sequencer merely
because both interfaces display steps.

Before implementation, inventory the export's actual contract:

- Pattern or stage parameters
- Per-stage values
- Length or active-stage count
- Playhead state
- Direction, clock, range, probability, glide, or other global controls
- Any TTID or scale controls that genuinely belong on this surface

The resolver will bind these by semantic role, and the visual design will be
based on the complete Analog Sequencer contract.

The existing Trigger Sequencer remains unchanged:

```text
steps parameter + editor: step16 -> parameter editor
```

This distinction will be documented and tested explicitly.

## Phase 6: Complete the dispatch separation

After the instance surfaces have been verified, simplify dispatch around the
new boundary:

```text
PARAM_LIST    -> parameter editor dispatch
INSTANCE_MENU -> instance surface dispatch
```

Parameter editors retained:

- Numeric
- Boolean
- Enum
- TTID
- Trigger Sequencer / `step16`
- Other genuinely single-parameter presentations

Instance surfaces:

- Organ
- Analog Sequencer
- Time Domain Scope
- Tuner
- ListSequencer

Remove obsolete Scope, Tuner, and Analog Sequencer branches from generic
`EDIT` only after their compatibility routes are no longer required.

## Test plan

### Registry and lifecycle tests

- Registry resolution uses canonical patcher name rather than instance label
- Unsupported exports do not gain a surface
- Missing required bindings cause a safe fallback
- Binding refresh survives replacement of parameter dictionaries
- Surface state survives compatible discovery refreshes
- Surface exit handles removed or replaced instances
- Each surface reports the correct render cadence
- Trigger Sequencer remains a parameter editor

### Navigation tests

- The surface item appears in the correct instance menu
- Opening a surface does not modify `param_cursor`
- `PARAMETERS` remains accessible
- Back navigation returns to the same instance
- Instance replacement closes or re-resolves the surface safely

### Organ tests

- Every supported parameter spelling maps to the correct footage
- Parameters are ordered canonically regardless of discovery order
- Every footage receives the correct color
- Missing or duplicate footage rejects the Organ surface
- Top maps to `-96 dB` and bottom maps to `0 dB`
- Drag capture remains on the initial drawbar
- Touch motion produces immediate local feedback
- OSC updates are coalesced
- Encoder navigation can reach and adjust all nine drawbars

### Existing-surface migration tests

- Time Domain Scope retains its sample history and time-window behavior
- Tuner retains pitch and cents updates
- Analog Sequencer uses its own export contract
- Trigger Sequencer retains its single-parameter `step16` behavior
- Scope and Tuner metadata no longer dispatches their obsolete parameter editors

## Live validation on `wren`

Live validation will occur after implementation and deployment authorization:

1. Confirm the exact Organ parameter names, ranges, and steps.
2. Load or select the Organ instance.
3. Confirm standard order and colors visually.
4. Test `-96 dB` at the top and `0 dB` at the bottom for every drawbar.
5. Confirm continuous drag and RNBO readback.
6. Confirm MIDI notes continue sounding while drawbars are manipulated.
7. Verify Scope, Tuner, Analog Sequencer, and Trigger Sequencer separately.

## Landing sequence

1. Commit the surface contract, registry, navigation, lifecycle, and tests.
2. Commit the complete Organ vertical slice.
3. Deploy the Organ slice to `wren` for touchscreen validation.
4. Migrate Time Domain Scope and Tuner.
5. Implement the Analog Sequencer surface from its verified parameter contract.
6. Remove obsolete parameter-anchored compatibility routes.
7. Update `docs/uispec.md`, `docs/architecture.md`, and `docs/walkthrough.md`.

## Completion criteria

Instance-surface support is complete when:

- Surface availability is derived from canonical export identity plus validated
  runtime bindings.
- Organ provides a responsive nine-drawbar touchscreen interface with correct
  direction, order, color, continuous dB mapping, and readback.
- Analog Sequencer, Time Domain Scope, Tuner, and ListSequencer operate as instance surfaces.
- Trigger Sequencer and TTID remain cleanly parameter-scoped.
- The ordinary parameter list remains a reliable fallback for every instance.
- Automated tests and live `wren` validation cover navigation, editing,
  refresh, and failure behavior.

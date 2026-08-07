Shadowbox Walkthrough

This document describes the current end-to-end flow from an RNBO export to a working Shadowbox editor.

1. Runtime model

Shadowbox talks to RNBO Runner over two channels:
- OSCQuery for discovery and periodic snapshots
- OSC for commands and live message/state updates

At runtime, the main concepts are:
- Patcher: a loadable RNBO asset under `/rnbo/patchers/<name>`
- Set: a whole-system runtime state and saved recall target published under Runner `sets`
- Set preset: a parameter-state preset for the currently loaded set, published under `sets/presets`
- Instance: a live RNBO runtime object under `/rnbo/inst/<n>`
- Instance preset: a preset entry published by one live instance under its `presets` branch
- Parameter: an editable value under an instance `params` branch
- State: a read-only runtime value published by an instance

2. Discovery flow

On startup and on refresh, `shadowbox/rnbo.py` reads the OSCQuery tree and normalizes it into a snapshot.

The snapshot currently includes:
- instances
- patchers
- saved set capabilities, set names, and startup configuration controls
- set presets when Runner publishes `sets/presets`
- instance presets
- parameters
- read-only instance state
- audio and MIDI routing
- system audio and status information

Shadowbox currently discovers read-only instance state from:
- `/rnbo/inst/<id>/state/...`
- `/rnbo/inst/<id>/messages/out/...`
- `/rnbo/inst/<id>/messages/out/state/...`

These message paths are important for RNBO outports that Runner republishes through OSCQuery.

3. Metadata-driven UI hints

Shadowbox uses parameter metadata as its general UI hint mechanism.

Metadata may be used for:
- custom editor selection
- display formatting such as units or decimal precision
- edit behavior such as input step size or integer-style editing
- runtime state key overrides for specialized live editors

Common metadata keys:
- `editor`
- `unit`, `units`
- `display_precision`
- `display_as`
- `edit_step`
- `edit_as`
- `bool`, `is_bool`, `boolean`
- `playhead_state`, `pitch_state`, `cents_state`
- `ui_role`

Custom editors are selected through the `editor` metadata key.

Current specialized editors:
- `ttid` via `{"editor":"ttid"}`
- `step16` via `{"editor":"step16"}`

Instance-surface resolvers may use editor metadata such as `pitch_display` or
`scope` as a binding hint without dispatching a parameter editor.

Interfaces that represent a complete export use the static instance-surface
registry under `shadowbox/surfaces/`. A surface is offered only when both the
canonical exported patcher `name` and its full live parameter/state contract
match. Mutable instance labels do not select a surface, and the normal
`PARAMETERS` entry remains available.

Current registered instance exports:
- `Organ`
- `AnalogSequencer`
- `TimeDomainScope`
- `Tuner`
- `ListSequencer`
- `ListVelSequencer`

The current Organ export on `wren` publishes continuous `-96..0 dB` tonewheel
controls. The Organ surface maps `-96 dB` to the top/off position and `0 dB`
to the bottom/full-on position in canonical Hammond footage order.

If metadata is missing or malformed, Shadowbox falls back to numeric behavior. The only non-metadata exception is enums published explicitly by RNBO as a value list. An enum whose complete advertised choices are exactly `Off` and `On` is shown as an inline switch in the parameter browser and toggles without opening the enum chooser. Shadowbox preserves and sends the original advertised strings. Other enums, including arbitrary two-choice enums, continue to use the chooser.

In practice, the metadata must appear in the published OSCQuery tree so that `rnbo.py` can parse it from the parameter's `meta` node. Shadowbox also accepts direct scalar child nodes for hints that RNBO exports separately instead of bundling them into `meta`, including `editor`, `display_name`, `ui_role`, and RNBO's native `steps` value. For `steps`, Shadowbox uses RNBO's endpoint-inclusive interval `(max - min) / (steps - 1)` for encoder and touch editing. Native stepped parameters advance one adjacent step per encoder detent without continuous-control acceleration, and grids with integral minima and intervals are displayed without decimal places.

Routing ports follow the same pattern for display labels. Publishing metadata such as `{"label":"Main Input"}` or a direct `display_name` child on an input/output lets Shadowbox show a friendly routing name while preserving the underlying port path and raw node name for control.

One practical use of this contract is recovering integer-style UI behavior from float-like RNBO Runner exports. For example, metadata such as `{"display_precision":0,"edit_step":1,"edit_as":"int","display_as":"int"}` lets Shadowbox present and edit a value as integer-like even when the transport value is published as a float.

4. Step16 editor contract

The `step16` editor is designed for a 16-step binary sequence stored in one parameter and a separate runtime playhead value.

Expected published structure:
- editable param: `/rnbo/inst/<id>/params/<name>`
- param metadata: `{"editor":"step16"}`
- runtime playhead: `/rnbo/inst/<id>/messages/out/current_stage`

Expected semantics:
- the editable parameter is a 16-bit mask in the range `0..65535`
- bit 0 corresponds to step 1 in the UI
- `current_stage` is a read-only integer-like value in the range `1..16`

Optional metadata overrides:
- `playhead_state`: alternate state key for a legacy or custom zero-based playhead

Shadowbox behavior:
- step input moves the focus step
- short press toggles the focused step and sends the updated mask immediately
- long press exits the editor without reverting already committed edits

The editor renders each step with three independent flags:
- active
- focused
- playing

5. Live state updates

Periodic discovery is enough for static structure, but not for fast-moving runtime state such as a sequencer playhead.

To support live updates, `shadowbox/shadowbox.py` starts a local OSC listener and registers it with RNBO Runner using:
- `/rnbo/listeners/add`

Incoming OSC messages matching:
- `/rnbo/inst/<id>/messages/out/...`
- `/rnbo/inst/<id>/messages/out/state/...`

are routed into the UI's cached instance state through:
- `ui.apply_instance_state_update(instance_id, path, value)`

This allows editors such as `step16` to update their runtime display without waiting for the normal refresh cycle.

5a. Tuner instance-surface contract

The Tuner instance surface is a live viewer for two runtime state values,
typically note name/number and pitch deviation in cents. `pitch_display`
metadata is retained as an optional binding hint; it no longer dispatches a
parameter editor.

Expected published structure:
- viewer param: `/rnbo/inst/<id>/params/<name>`
- param metadata: `{"editor":"pitch_display"}`
- runtime pitch value: `/rnbo/inst/<id>/messages/out/pitch_name`
- runtime cents value: `/rnbo/inst/<id>/messages/out/pitch_cents`

Optional metadata overrides:
- `pitch_state`: alternate state key for pitch
- `cents_state`: alternate state key for cents

Shadowbox behavior:
- the `Tuner` instance surface opens the live display-only screen when its pitch and cents state contract resolves
- incoming OSC state updates keep the screen current in real time
- instance-surface navigation exits to the instance menu
- the tagged anchor remains an ordinary parameter under `PARAMETERS`; it no longer dispatches the tuner viewer

5b. Time Domain Scope instance-surface contract

The TimeDomainScope instance surface is a live oscilloscope-style viewer for
scalar amplitude samples. It uses a parameter such as `SamplingRate` tagged
with scope metadata as its editable binding, so turning the encoder adjusts
that parameter while the waveform remains visible. The metadata no longer
dispatches a parameter editor.

Expected published structure:
- editable sample-rate param: `/rnbo/inst/<id>/params/SamplingRate`
- param metadata: `{"editor":"scope"}`
- runtime sample value: `/rnbo/inst/<id>/messages/out/scope`

Optional metadata overrides:
- `scope_state`: alternate state key for the incoming sample stream

Shadowbox behavior:
- the `TimeDomainScope` instance surface opens the live waveform editor when its sample-rate and scope state contract resolves
- `/scope` values are treated as amplitudes in the `-1.0..1.0` range and clipped to that range
- incoming samples are drawn left-to-right with the newest sample at the right edge, like a scrolling oscilloscope trace
- the displayed time window is derived from the number of visible samples and the current parameter value
- encoder turns continue to update the tagged parameter while the waveform is visible
- instance-surface navigation exits to the instance menu
- the tagged sample-rate parameter remains an ordinary numeric editor under `PARAMETERS`

5c. ListSequencer instance-surface contract

`ListSequencer` stores sequence fields behind OSC message inports because RNBO
parameters do not support lists. Shadowbox therefore discovers these controls
from `/rnbo/inst/<id>/messages/in` and never places them in the parameter model.

Expected ordered inports:
- `Steps`
- `StepsSecondary`
- `PrimaryRotation`
- `SecondaryRotation`
- `Oct`
- `Velocity`
- `Duration`

Expected readback outports are the matching names with an `Ack` suffix, such as
`StepsAck`. On surface entry, Shadowbox sends `[-999]` to each list inport and
uses the corresponding ACK value to populate a space-separated draft.

Touch behavior:
- selecting a field assigns it to the compact `1..9 / SPC 0 DEL` keypad
- Steps and Secondary Steps accept only binary tokens
- Primary Rotation, Secondary Rotation, and Octave expose a contextual sign control
- `SEND` parses the complete draft and transmits one atomic OSC list
- long press or back returns to the instance menu

Optional USB numeric-keypad behavior:
- on the home screen, `Enter` starts the global Runner transport and `0` stops it
- `0..9` enter digits
- numpad `+` enters a space
- numpad `.` deletes one character
- numpad `-` toggles the sign of the current token
- numpad `Enter` sends the selected field
- numpad `/` and `*` select the previous and next fields
- `Tab` cycles to the next field

The keypad is configured with `SHADOWBOX_KEYPAD_DEVICE`. Shadowbox exclusively
grabs the configured evdev device while running so its keys do not appear on
the Linux console behind the framebuffer interface. Outside the home-screen
transport shortcuts, ListSequencer, ListVelSequencer, and the regular numeric
parameter editor, these keypad events are ignored.

5d. ListVelSequencer instance-surface contract

`ListVelSequencer` publishes eight velocity lists as OSC message inports
`1row` through `8row`, with matching `1rowAck` through `8rowAck` state
outports. Each row also publishes a `1map` through `8map` parameter that maps
the row to a MIDI pitch.

The surface presents eight selectable rows using the ListSequencer list-entry
model. Each row label includes its current pitch-map value, while the editable
draft contains that row's velocity sequence. On entry, Shadowbox sends
`[-999]` to all eight row inports and hydrates clean drafts from their ACK
values. `SEND ROW` sends only the selected velocity list and rejects values
outside `0..127`. Pitch maps remain editable through the ordinary
`PARAMETERS` menu.

The compact touch keypad and optional USB numeric keypad use the same digit,
space, delete, send, and row-selection behavior as ListSequencer. ListVel rows
are unsigned and therefore do not expose the contextual sign control.

In the regular numeric parameter editor, the same keypad provides direct value
entry. Digits begin a fresh draft, numpad `.` enters a decimal point, Backspace
or numpad `+` deletes, numpad `-` toggles the sign when negative values are
valid, and numpad `Enter` commits the range-clamped value. Encoder or touch
adjustment cancels an unfinished keypad draft.

6. System control workflows

System controls coordinate Runner-wide or host-level behavior. They are not
instance surfaces and do not change the contract of ordinary parameter,
routing, or performance-MIDI paths.

6a. Chromatic and scalar transpose

An RNBO instance participates in ensemble transpose by publishing either or
both of these exact parameter names:

- `ChromaticTranspose`: an integer offset in semitones
- `ScalarTranspose`: an integer offset in scale steps

Shadowbox discovers every matching live parameter by exact name. Mutable
instance labels do not opt an instance in. Each parameter's published range is
respected; Shadowbox skips an out-of-range target instead of clamping it.

To configure standalone transpose:

1. Open `SYSTEM -> TRANSPOSE`.
2. Set `AUTHORITY` to `LOCAL`. Existing installations begin at `UNCONFIGURED`,
   and neither touch, MIDI, nor semantic OSC fans out values until local
   authority is selected explicitly.
3. Optionally edit the `CHROMATIC` or `SCALAR` row directly. The editor uses the
   intersection of the ranges published by all compatible targets.
4. To use a MIDI keyboard, choose its ALSA input under `CONTROLLER`, then set
   `FUNCTION` to `CHROMATIC TRANSPOSE` or `SCALAR TRANSPOSE`.

The designated MIDI input maps note pitch to an absolute offset:

```text
offset = MIDI note - 60
```

Middle C, MIDI note 60, selects `0`; note 61 selects `+1`; note 59 selects
`-1`. Only positive-velocity note-on messages change the latched offset.
Velocity otherwise has no effect, note-off has no effect, and all MIDI
channels are accepted from the designated port.

This is a sidecar control path. Shadowbox does not relay the controller's
ordinary performance MIDI to RNBO, so designation does not insert Shadowbox
into the performance path. The controller is remembered by ALSA client and
port name rather than its transient numeric address. A remembered disconnected
port is shown as `OFFLINE` and is eligible to reconnect when the same named port
returns.

The transpose screen shows each canonical offset and the number of matching
compatible targets. `MIXED` means at least one observed target differs from the
canonical value or cannot accept it. In local mode, a newly discovered target
receives the retained value once; routine discovery does not continually
overwrite a later direct external edit.

`SHADOWSCORE` records managed-authority intent but does not currently forward
requests or fan out local values. It never falls back to `LOCAL` automatically.
Source-aware local OSC can use port `13333` and these addresses:

- `/shadowbox/transpose/chromatic`
- `/shadowbox/transpose/scalar`

The first argument is the offset; an optional second string is displayed as
the source. Bare writes to RNBO parameter paths have no reliable provenance.

Authority, offsets, controller identity, controller function, and the last
source label are persisted in `~/rnbo-ui/shadowbox_state.json` under
`transpose_control`.

6b. Global Runner transport

`SYSTEM -> TRANSPORT` appears only when OSCQuery publishes both global Runner
controls:

- `/rnbo/jack/transport/rolling`
- `/rnbo/jack/transport/bpm`

Selecting `STATE` toggles the published rolling value. Selecting `TEMPO` opens
an editor constrained to `20.0..300.0 BPM` with one-BPM encoder steps. These
actions control musical transport only; they do not stop or restart JACK and
do not introduce ShadowScore player or arrangement state.

7. RNBO authoring guidelines

For metadata-driven UI integration, the RNBO side should follow these rules:
- publish editable controls as parameters
- publish runtime-only values as message out/state
- use metadata to describe UI intent, including specialized editors, display hints, and edit behavior
- keep UI navigation state out of the patch

For the `TriggerSequencer` `step16` editor, the recommended split is:
- param: sequence mask
- out: current_stage (1..16)

The remaining normalized Trigger Sequencer parameter names are `MaxSteps`
(an enum displayed as 1..16 with underlying values 0..15) and
`TriggerDuration`. Shadowbox consumes those names and enum choices directly
from the live OSCQuery tree rather than hard-coding parameter aliases.

For the tuner-style pitch display, the recommended split is:
- param: viewer/dummy parameter with `{"editor":"pitch_display"}`
- out: pitch_name
- out: pitch_cents

8. Current limitations

- RNBO parameter values are currently treated as numeric values, so bitmask parameters may appear as floats in OSCQuery even when used as integers semantically
- Shadowbox can coerce these to integers for editor logic, but the RNBO side should still quantize the parameter range appropriately
- Unit metadata is only displayable if it is actually exposed through OSCQuery

9. Relevant files

- `shadowbox/rnbo.py`: OSCQuery discovery and metadata parsing
- `shadowbox/discovery.py`: background discovery coordination
- `shadowbox/ui.py`: UI state machine and editor behavior
- `shadowbox/renderer.py`: visual rendering
- `shadowbox/render_scheduler.py`: dirty-state and per-surface frame scheduling
- `shadowbox/shadowbox.py`: runtime loop, refresh logic, and live OSC listener
- `shadowbox/keypad.py`: optional USB numeric-keypad input
- `shadowbox/transpose_control.py`: ALSA controller discovery, note parsing, and exact-name transpose target resolution
- `shadowbox/surfaces/`: instance-surface registry and contract resolvers
- `shadowbox/editors/step16.py`: `step16` editor logic
- `docs/uispec.md`: UI behavior and editor rules

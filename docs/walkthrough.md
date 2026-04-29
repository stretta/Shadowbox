Shadowbox Walkthrough

This document describes the current end-to-end flow from an RNBO export to a working Shadowbox editor.

1. Runtime model

Shadowbox talks to RNBO Runner over two channels:
- OSCQuery for discovery and periodic snapshots
- OSC for commands and live message/state updates

At runtime, the main concepts are:
- Patcher: a loadable RNBO asset under `/rnbo/patchers/<name>`
- Instance: a live RNBO runtime object under `/rnbo/inst/<n>`
- Parameter: an editable value under an instance `params` branch
- State: a read-only runtime value published by an instance

2. Discovery flow

On startup and on refresh, `shadowbox/rnbo.py` reads the OSCQuery tree and normalizes it into a snapshot.

The snapshot currently includes:
- instances
- patchers
- presets
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
- `pitch_display` via `{"editor":"pitch_display"}`

If metadata is missing or malformed, Shadowbox falls back to numeric behavior. The only non-metadata exception is enums published explicitly by RNBO as a value list.

In practice, the metadata must appear in the published OSCQuery tree so that `rnbo.py` can parse it from the parameter's `meta` node. Shadowbox also accepts direct scalar child nodes for some hints, such as `editor`, `display_name`, and `ui_role`, when RNBO exports them separately instead of bundling them into `meta`.

Routing ports follow the same pattern for display labels. Publishing metadata such as `{"label":"Main Input"}` or a direct `display_name` child on an input/output lets Shadowbox show a friendly routing name while preserving the underlying port path and raw node name for control.

One practical use of this contract is recovering integer-style UI behavior from float-like RNBO Runner exports. For example, metadata such as `{"display_precision":0,"edit_step":1,"edit_as":"int","display_as":"int"}` lets Shadowbox present and edit a value as integer-like even when the transport value is published as a float.

4. Step16 editor contract

The `step16` editor is designed for a 16-step binary sequence stored in one parameter and a separate runtime playhead value.

Expected published structure:
- editable param: `/rnbo/inst/<id>/params/<name>`
- param metadata: `{"editor":"step16"}`
- runtime playhead: `/rnbo/inst/<id>/messages/out/step16_playhead`

Expected semantics:
- the editable parameter is a 16-bit mask in the range `0..65535`
- bit 0 corresponds to step 1 in the UI
- the playhead is a read-only integer-like value in the range `0..15`

Optional metadata overrides:
- `playhead_state`: alternate state key for the playhead

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

5a. Pitch display editor contract

The `pitch_display` editor is a live viewer for two runtime state values, typically note name/number and pitch deviation in cents.

Expected published structure:
- viewer param: `/rnbo/inst/<id>/params/<name>`
- param metadata: `{"editor":"pitch_display"}`
- runtime pitch value: `/rnbo/inst/<id>/messages/out/pitch_name`
- runtime cents value: `/rnbo/inst/<id>/messages/out/pitch_cents`

Optional metadata overrides:
- `pitch_state`: alternate state key for pitch
- `cents_state`: alternate state key for cents

Shadowbox behavior:
- opening the parameter enters a live display-only screen
- incoming OSC state updates keep the screen current in real time
- short press or long press exits back to the parameter list

5b. Time domain scope editor contract

The `scope` editor is a live oscilloscope-style viewer for scalar amplitude samples. It is intended for a parameter such as `SamplingRate` tagged with scope metadata, so turning the encoder adjusts that parameter while the waveform remains visible.

Expected published structure:
- editable sample-rate param: `/rnbo/inst/<id>/params/SamplingRate`
- param metadata: `{"editor":"scope"}`
- runtime sample value: `/rnbo/inst/<id>/messages/out/scope`

Optional metadata overrides:
- `scope_state`: alternate state key for the incoming sample stream

Shadowbox behavior:
- opening the tagged parameter enters a live waveform editor
- `/scope` values are treated as amplitudes in the `-1.0..1.0` range and clipped to that range
- incoming samples are drawn left-to-right with the newest sample at the right edge, like a scrolling oscilloscope trace
- the displayed time window is derived from the number of visible samples and the current parameter value
- encoder turns continue to update the tagged parameter while the waveform is visible
- short press exits back to the parameter list; long press exits and restores the original parameter value

6. RNBO authoring guidelines

For metadata-driven UI integration, the RNBO side should follow these rules:
- publish editable controls as parameters
- publish runtime-only values as message out/state
- use metadata to describe UI intent, including specialized editors, display hints, and edit behavior
- keep UI navigation state out of the patch

For `step16`, the recommended split is:
- param: sequence mask
- out: step16_playhead

For the tuner-style pitch display, the recommended split is:
- param: viewer/dummy parameter with `{"editor":"pitch_display"}`
- out: pitch_name
- out: pitch_cents

7. Current limitations

- RNBO parameter values are currently treated as numeric values, so bitmask parameters may appear as floats in OSCQuery even when used as integers semantically
- Shadowbox can coerce these to integers for editor logic, but the RNBO side should still quantize the parameter range appropriately
- Unit metadata is only displayable if it is actually exposed through OSCQuery

8. Relevant files

- `shadowbox/rnbo.py`: OSCQuery discovery and metadata parsing
- `shadowbox/ui.py`: UI state machine and editor behavior
- `shadowbox/renderer.py`: visual rendering
- `shadowbox/shadowbox.py`: runtime loop, refresh logic, and live OSC listener
- `shadowbox/editors/step16.py`: `step16` editor logic
- `docs/uispec.md`: UI behavior and editor rules

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
- `/rnbo/inst/<id>/messages/out/state/...`

This second path is important for RNBO message outports that Runner republishes through OSCQuery.

3. Metadata-driven editors

Custom editors are selected through parameter metadata.

Current specialized editors:
- `ttid` via `{"editor":"ttid"}`
- `step16` via `{"editor":"step16"}`

If metadata is missing or malformed, Shadowbox falls back to the generic editor path.

In practice, the metadata must appear in the published OSCQuery tree so that `rnbo.py` can parse it from the parameter's `meta` node.

4. Step16 editor contract

The `step16` editor is designed for a 16-step binary sequence stored in one parameter and a separate runtime playhead value.

Expected published structure:
- editable param: `/rnbo/inst/<id>/params/<name>`
- param metadata: `{"editor":"step16"}`
- runtime playhead: `/rnbo/inst/<id>/messages/out/state/playhead`

Expected semantics:
- the editable parameter is a 16-bit mask in the range `0..65535`
- bit 0 corresponds to step 1 in the UI
- the playhead is a read-only integer-like value in the range `0..15`

Shadowbox behavior:
- rotate moves the focus step
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
- `/rnbo/inst/<id>/messages/out/state/...`

are routed into the UI's cached instance state through:
- `ui.apply_instance_state_update(instance_id, path, value)`

This allows editors such as `step16` to update their runtime display without waiting for the normal refresh cycle.

6. RNBO authoring guidelines

For custom editor integration, the RNBO side should follow these rules:
- publish editable controls as parameters
- publish runtime-only values as message out/state
- use metadata to request specialized editors
- keep UI navigation state out of the patch

For `step16`, the recommended split is:
- param: sequence mask
- out/state: playhead

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

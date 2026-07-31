# Ensemble Transpose Controls Development Plan

## Purpose

Shadowbox needs a narrow class of standardized real-time system controls for
RNBO exports that share the parameters `ChromaticTranspose` and
`ScalarTranspose`. Both parameters are bipolar integer offsets with `0` as the
neutral value.

The first use case is a standalone Shadowbox with no ShadowScore server. A USB
MIDI keyboard can be designated as a control surface instead of a normal
performance-MIDI device. MIDI note 60 (middle C) selects offset `0`; adjacent
notes select adjacent positive or negative offsets.

This feature is not a general MIDI mapping matrix. It coordinates a small,
documented vocabulary of semantic controls across compatible local RNBO
instances.

## Verified Current Boundaries

- OSCQuery is the source of truth for live RNBO instances and their parameters.
- Parameter MIDI learn currently stores CC mappings per patcher and parameter
  name. It does not support note-keyboard system controls.
- Shadowbox receives live RNBO parameter updates on its existing local OSC
  listener and writes parameters directly to the Runner on UDP port 1234.
- Instance MIDI routing is published through the Runner's JACK/OSCQuery tree.
- `wren` provides ALSA sequencer utilities (`aconnect` and `aseqdump`) but the
  Shadowbox virtual environment does not contain `mido`, `rtmidi`, `jack`, or
  `alsaseq` Python packages.
- The `SYSTEM` menu already owns deliberately curated host-level integrations
  such as audio, networking, and software maintenance.

## Terminology

### Control source

The physical or software actor that requested a value change, for example:

- Shadowbox touchscreen
- a designated local MIDI controller
- ShadowScore
- GraphEditor
- unattributed external OSC

### Control authority

The component allowed to canonicalize and distribute the value.

- `standalone`: this Shadowbox owns the canonical local offsets.
- `shadowscore`: ShadowScore owns the canonical offsets; Shadowbox mirrors
  confirmed state and sends requests rather than asserting local state.

Source and authority are distinct. In managed operation a local MIDI keyboard
may be the source of a request while ShadowScore remains the authority.

### Canonical local offset

In standalone mode only, Shadowbox retains the desired value for each
standardized control and distributes it to compatible local instances. This
state is device-local and must never be promoted automatically into a managed
ShadowScore system.

## Functional Contract

### Standard controls

| Control | RNBO parameter | Unit | Neutral value |
| --- | --- | --- | --- |
| Chromatic transpose | `ChromaticTranspose` | semitones | `0` |
| Scalar transpose | `ScalarTranspose` | scale steps | `0` |

Discovery uses exact parameter names. Shadowbox does not infer participation
from mutable instance labels.

### MIDI note mapping

- Note-on selects an absolute value: `offset = note_number - 60`.
- MIDI note 60 is always exactly `0`.
- Velocity is ignored except that a note-on with velocity zero is treated as
  note-off.
- Note-off does nothing; the selected value is latched.
- Values outside a target parameter's published range are not sent to that
  target. The UI reports partial or mixed target state rather than silently
  clamping.
- The initial implementation accepts all MIDI channels from the designated
  device. Channel filtering can be added without changing the note mapping.

### Controller designation

`SYSTEM -> TRANSPOSE` exposes connected ALSA MIDI input ports and allows one
port to be assigned one of these roles:

- `None`
- `Chromatic Transpose`
- `Scalar Transpose`

The assignment is stored by stable client and port names, not transient ALSA
client numbers. A configured but disconnected controller remains visible and
is reattached when the matching port returns.

The reader observes only the explicitly designated control port. It is not an
inline MIDI relay. Normal performance-MIDI continues directly to RNBO and
therefore gains no Shadowbox scheduling or translation latency.

Where the same hardware port is also routed to an RNBO MIDI input, Shadowbox
must show that routing conflict. Automatic JACK/ALSA disconnection requires a
verified stable correspondence between the ALSA sequencer port and Runner JACK
source names; until that correspondence is available, designation must not
guess at or rewrite unrelated routes.

### Standalone canonical state

In standalone mode:

1. Touchscreen, encoder, local MIDI, or source-aware local OSC submits an
   absolute offset.
2. Shadowbox records the value, source, and monotonic receipt time.
3. Shadowbox writes the value to every compatible local parameter.
4. RNBO parameter echoes confirm target state but do not create new commands.
5. A newly discovered compatible instance receives the retained offset once.
6. Direct instance parameter writes may produce a `Mixed` display, but are not
   automatically promoted into canonical system commands.

Repeated discovery must not continually rewrite every target. Shadowbox tracks
which instance/parameter paths have received the current generation so routine
refreshes cannot fight GraphEditor or other direct instance edits.

### Managed authority

Managed mode requires an explicit ShadowScore authority protocol. It must not
be inferred solely from network availability or from observing matching
parameter writes.

When managed:

- Shadowbox mirrors ShadowScore-confirmed values.
- Local touch and MIDI become requests addressed to ShadowScore.
- Shadowbox does not fan local cached state directly to RNBO instances.
- Loss of the server freezes the last confirmed display and marks authority
  offline.
- Shadowbox never promotes itself automatically after a timeout.
- `Take Local Control` is a deliberate, user-visible authority transition.
- Rejoining managed mode accepts ShadowScore's canonical value; local cached
  state is not pushed upstream silently.

The ShadowScore request/confirmation protocol is a separate cross-repository
phase and is not approximated by the standalone implementation.

## OSC and Provenance Contract

A bare RNBO parameter update contains a value but no reliable sender identity.
Shadowbox may label such a change `External OSC`, but must not guess whether it
came from ShadowScore or GraphEditor.

Reliable attribution requires a Shadowbox-owned semantic ingress. The proposed
addresses are:

- `/shadowbox/transpose/chromatic`
- `/shadowbox/transpose/scalar`

Each command carries an integer value and may carry a source identifier and
interaction identifier. The exact OSC argument schema will be coordinated with
ShadowScore and GraphEditor before managed mode is implemented.

The UI presents:

- current canonical value, when standalone or confirmed by the authority;
- authority (`LOCAL` or `SHADOWSCORE`);
- last known source;
- controller connection state;
- compatible target count; and
- `Mixed` when observed targets disagree with the canonical value.

Source means the latest accepted command, not permanent ownership. Repeated
source-aware OSC commands may be shown as active automation, but timing alone
is not used to invent provenance.

## Persistence

Extend `~/rnbo-ui/shadowbox_state.json` with a versioned `transpose_control`
object containing:

- authority mode;
- designated ALSA client name;
- designated ALSA port name;
- controller role;
- canonical chromatic offset;
- canonical scalar offset; and
- last locally known source labels where useful for display.

Unknown and older state remains loadable. Persisted local offsets are applied
only in standalone mode.

## Implementation Phases

### Phase 1: Standalone domain and ALSA input

- Add a pure ensemble-control model for standardized parameter discovery,
  note-to-offset conversion, target fanout, target confirmation, and mixed
  state.
- Add an ALSA sequencer port discovery parser around `aconnect -i -l`.
- Add a reconnecting `aseqdump` reader for note-on events from the designated
  port.
- Keep the reader outside the normal performance-MIDI path.
- Unit-test parsing, reconnect identity, note semantics, parameter range
  handling, fanout generations, and no-op note-off behavior.

### Phase 2: Shadowbox system UI and persistence

- Add `SYSTEM -> TRANSPOSE`.
- Show authority, chromatic and scalar values, controller, role, target state,
  and source.
- Add controller and role pickers.
- Add direct local editing/reset of both offsets.
- Persist assignments and canonical standalone values.
- Ensure touchscreen and encoder navigation remain equivalent.

### Phase 3: Runtime integration

- Drain MIDI control events in the main loop.
- Fan accepted values directly to compatible RNBO parameter paths.
- Apply the retained generation once to newly appearing targets.
- Classify RNBO echoes as confirmation rather than commands.
- Surface disconnect, unsupported range, and mixed-state status without
  blocking discovery or rendering.

### Phase 4: Live standalone validation

- Deploy to `wren`.
- Confirm service stability with no MIDI device connected.
- Connect a class-compliant MIDI keyboard and designate it in the system UI.
- Verify middle C produces `0`, adjacent notes produce exact signed offsets,
  velocity is ignored, and note-off does not change the value.
- Verify all compatible local instances update and unrelated parameters do not.
- Verify a newly added compatible instance receives the retained value once.
- Verify ordinary performance-MIDI routes do not traverse Shadowbox and show no
  added note latency.
- Verify unplug/replug restores the controller by stable name.

### Phase 5: Source-aware OSC and ShadowScore authority

- Finalize the semantic OSC request and confirmation schema with
  ShadowscoreServer and GraphEditor.
- Implement explicit managed authority, heartbeat/status, request forwarding,
  confirmation, and offline presentation.
- Add a deliberate local-takeover and managed-rejoin workflow.
- Test multiple Shadowboxes against one ShadowScore authority, including
  network loss and reconnection without split brain.

## Testing Gates

- Pure unit tests for every parser and state transition.
- UI tests for encoder and direct-touch navigation.
- Full existing Shadowbox test suite before each commit.
- Read-only inspection of outgoing git range before any push.
- Live service state, restart count, journal, OSCQuery parameter readback, and
  physical controller behavior on `wren` before declaring the feature tested.

## Initial Delivery Boundary

The first implementation delivery covers Phases 1 through 4: authoritative
standalone state, local UI, ALSA note input, RNBO fanout, persistence, and live
`wren` validation. Phase 5 requires coordinated changes outside this repository
and will not be simulated with an implicit or competing local authority.

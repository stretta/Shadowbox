# ShadowScore Client Display

## Scope

This project adds a dedicated Shadowbox instance surface for one local
`ShadowScoreClient` export. It is an instrument display: it explains what the
client is playing now without becoming an ensemble dashboard or a raw
diagnostics screen.

Shadowbox owns export recognition, outport binding, local display state, and
the 800x480 presentation. The first phase does not require ShadowscoreServer.
Future server context may add player, block, and section labels, but the local
musical display must continue working when the server is unavailable.

## Local contract

The surface resolves only when the canonical export name is
`ShadowScoreClient` and exactly one of each required outport is present:

- `current_stage`: the client's current zero-based playback stage.
- `playback_debug`: the complete chord witness in the form
  `[30, stage, note_count, pitch, duration, velocity, ...]`.
- `midi_debug`: the most recently emitted MIDI event in the live Runner form
  `[pitch, velocity, duration_ms]`.
- `shadowscore_ack`: transaction lifecycle readback. Current clients may
  prefix lifecycle opcodes with the receiver opcode `90`, so both
  `[92, ...]` and `[90, 92, ...]` shapes are accepted.

Bindings use the canonical export name and exact outport leaf names, not the
mutable instance label or a fixed instance number. Missing or duplicate
required outports reject the custom surface and leave ordinary instance tools
available.

## First display

The first 800x480 layout is read-only and gives visual priority to:

1. The current chord as note-name tiles with velocity and stage duration. A
   rest latches the last non-rest chord in a subdued style instead of erasing
   it, while a `REST` label and rest-event count prevent it from appearing
   current.
2. The current zero-based stage.
3. A compact recent-event ribbon built from `playback_debug` updates while the
   surface is open. Chords show density; zero-note events show rests.
4. A small lifecycle summary (`READY`, `ACTIVE`, `REJECTED`, or `COMMITTED`)
   and the last actual MIDI triad.

The surface deliberately does not infer future events from the local outport
snapshots. It also does not claim that the stale value of `midi_debug` denotes
current sound: the label identifies it as the last emitted MIDI event.

Smaller displays receive a compact textual version of the same current chord,
stage, and lifecycle state.

## State and refresh rules

- The current values remain Runner/OSCQuery-owned and are refreshed through
  the existing discovery and OSC listener paths.
- Recent-event history is transient Shadowbox UI state. It begins with the
  currently published `playback_debug` value, records distinct subsequent
  playback updates, and is discarded when the surface closes.
- The last valid non-rest chord is separately latched for the lifetime of the
  open surface. Rest events increment a visible count and never replace that
  useful musical context.
- The surface is event-driven. It redraws when a bound outport changes and
  does not add polling or continuous animation.
- Malformed diagnostic lists render as unavailable instead of being partially
  interpreted.

## Server context

The canonical transport client adds a restrained context line containing the
server's acknowledged play/stop state, active section, and sync health. This
does not turn the surface into an ensemble dashboard: the local chord, stage,
MIDI, and transaction lifecycle remain primary, and the surface falls back to
an explicit `LOCAL · SERVER DISCONNECTED` label.

Assigned-player detail, section progress, pending replacement state, and a
trustworthy long-running event history remain later work. Event history should
come from a sequenced collector rather than reconstructing chronology from
polled OSCQuery snapshots. See
[shadowscore-transport-client-plan.md](./shadowscore-transport-client-plan.md)
for transport authority and control behavior.

## Transfer feedback checkpoint

The local-first surface now expands `shadowscore_ack` into structured transfer
feedback while the surface is open. It remains event-driven and does not depend
on ShadowscoreServer availability.

- `BEGIN_REPLACE` records the transaction id and expected row count.
- Subsequent `NOTE` acknowledgements retain that total and display live
  `RECEIVING current/expected` progress.
- Rejections display the protocol reason (`NOTE COUNT`, `ROW ORDER`, `ROW
  RANGE`, `STALE TRANSACTION`, `PROTOCOL`, or `CHECKSUM`) and the retained row
  count.
- Current and legacy compact READY shapes both render as READY rather than
  falling back to WAITING.
- The 800x480 status panel shows the transaction id beneath the lifecycle line;
  compact displays receive a shortened lifecycle/progress line.
- READY and ACTIVE remain separate states. Receiving or rejected data is never
  presented as playable.

Server-level retry attempt numbers and coordinator decisions remain a possible
later enrichment. The local RNBO acknowledgement stays the authoritative
client-side witness.

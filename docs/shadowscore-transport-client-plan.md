# ShadowScore Authoritative Transport Client

## Goal

Make Shadowbox an acknowledged client of ShadowscoreServer's authoritative
transport while retaining direct RNBO Runner transport as a visible standalone
and compatibility fallback.

The server owns ensemble intent, payload readiness, arrangement position,
assigned-player cohort checks, clock and phase coordination, and sync recovery.
Shadowbox owns hardware interaction, responsive pending feedback, local fallback,
and presentation of both server intent and local RNBO witnesses.

## Current server contract

Shadowbox resolves and observes the canonical `ShadowScoreTransport` object:

```text
GET  /api/v1/objects/resolve?path=shadow_score%20transport
GET  /api/v1/objects/transport
POST /api/v1/objects/transport
GET  /api/v1/objects/transport/events
```

Operations use the implemented envelope, not the obsolete development-plan
prototype:

```json
{
  "request_id": "caller-generated-id",
  "client_id": "shadowbox-wren",
  "operation": "play",
  "args": {}
}
```

Supported operations are `play`, `stop`, `return_to_start`, `locate_beats`,
`locate_fraction`, `set_tempo`, `previous_section`, `next_section`, and
`re_sync`. Shadowbox must also honor the returned capability flags.

The revisioned object publishes `is_playing`, arrangement position and
duration, bars/beats/ticks, tempo, time signature, active section, server and
clock authority, arrangement details, sync health, and capabilities.

## Authority and fallback invariants

1. A connected canonical object makes the server authoritative.
2. Server-mode commands never first write local Runner transport.
3. Shadowbox renders a server command only after its acknowledged object or a
   newer observer snapshot arrives. `STARTING` and `STOPPING` are pending
   intent, not playback truth.
4. An ambiguous timeout clears pending intent and refreshes observation; it
   must not trigger an automatic local command or blind retry.
5. Direct `/rnbo/jack/transport/rolling` and BPM remain available when no
   canonical object is connected and are labeled `LOCAL`.
6. `/transport/external` remains a compatibility notification for direct local
   hardware movement. It is never sent in addition to a canonical operation.
7. `READY`, `ACTIVE`, server `is_playing`, advancing local stage, emitted MIDI,
   and audible output remain distinct witnesses.

## User interface

### Home card

- `PLAY`, `STOP`, `STARTING`, or `STOPPING` from acknowledged/pending state.
- Server mode shows BPM, active section, and concise sync health.
- Fallback mode shows BPM and `LOCAL`.

### System Transport

Server mode exposes state and authority, tempo, active section, BBT position,
sync health, previous/next section, return to start, and capability-gated
re-sync. Local mode retains state and tempo only.

A later five-inch checkpoint may add an arrangement scrubber. It must commit
`locate_fraction` only on release and remain pending while the server activates
the destination payload and repositions the cohort. Encoder-first displays
use section navigation instead of fine continuous seek.

### Local ShadowScoreClient surface

The instance surface remains instrument-like and local-first. Optional server
context is a restrained strip showing server play/stop, active section, and
sync state. Local chord, rest, stage, MIDI, and transfer lifecycle remain the
primary content and continue working without the server.

## Runtime design

- A background observer maintains the canonical SSE stream with reconnect and
  URL fallback.
- A separate command worker prevents server operations from blocking input or
  rendering.
- The main UI thread drains typed connection, snapshot, command, and error
  results.
- Older revisions are discarded.
- URL discovery reuses `SHADOWBOX_SHADOWSCORE_URL`, loopback port `8790`, the
  registration state, and the hardware-peer configuration.

## Delivery checkpoints

### Checkpoint 1: Authority foundation

- Canonical SSE observer and command worker.
- Acknowledged Play, Stop, and Tempo.
- Explicit `SHADOWSCORE` versus `LOCAL` presentation.
- Unit tests for the wire envelope, SSE parsing, revision handling, pending
  state, and fallback behavior.

### Checkpoint 2: Arrangement access

- Section, position, and sync status.
- Previous/Next, Return to Start, and Re-sync.
- Optional server context on the local ShadowScoreClient surface.

### Checkpoint 3: Touch locate

- Five-inch arrangement scrubber with release-only commit.
- Pending and failure presentation for coordinated seek.
- Physical verification across section boundaries and while already playing.

### Checkpoint 4: Live acceptance

- Identity-verified deployment to Wren.
- Service and checksum freshness.
- Canonical GET/SSE reachability from the Shadowbox host.
- Play/Stop/Tempo and section commands converge on one authoritative object.
- Transaction-matched ACTIVE payloads and direct local stage/playback witnesses.
- Sync status agrees with server playback diagnostics.
- Musician verification of controls and audible physical output.

## Current status

Checkpoints 1, 2, and 4 are implemented, deployed, and physically accepted on
Wren. Checkpoint 3 is also implemented, deployed, and physically accepted with
a dedicated five-inch scrubber, release-only `locate_fraction` commit, pending
acknowledgement, and authoritative failure recovery. Musician testing confirmed
cross-section seeks while stopped and running, including continued audible
playback after the running seek. All four delivery checkpoints are complete.

On 2026-08-19, live acceptance on Wren confirmed canonical Play with HTTP 200,
seven assigned targets prepared and transaction-matched ACTIVE, an advancing
authoritative BBT position, direct advancing stage witnesses from all seven
RNBO clients, and settled aligned sync. Four stale Finch/Heron assignments were
reconciled to the confirmed live instances before that successful start.
Shadowbox remained active with no service restarts or new journal errors.

Transport command failures now extract the server's JSON error detail instead
of showing only the HTTP status; readiness failures are summarized on the
front panel as the number of clients not ready or not active. Musician testing
confirmed that the front-panel position visibly advances and that the ACTIVE
note stream is audible through the physical output path. Checkpoint 4 is
complete.

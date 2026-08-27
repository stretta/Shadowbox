# Consolidated Transport Surface

## Goal

Replace the five-inch touch transport menu with a purpose-built performance
surface. The surface keeps acknowledged ShadowscoreServer state authoritative
while presenting controls according to the musician's task instead of the
shape of the API.

Encoder-first displays retain the existing selectable transport rows.

## Shared transport shell

The touch surface always keeps these controls visible when available:

- acknowledged Play/Stop and pending Start/Stop state;
- Tempo;
- authoritative position and active section;
- restrained authority and sync state;
- contextual recovery controls.

Healthy sync is quiet. Re-sync is a secondary control when supported and
becomes visually recommended only when the authoritative object recommends it.
Commands remain pending until a returned object or newer observation
acknowledges them.

Tempo is inline on the five-inch surface. The center of its card is a relative
scrubber: horizontal movement previews a whole-BPM offset from the gesture's
starting value and release sends exactly one `set_tempo`. The left and right
edges step one BPM. A stationary tap opens the existing full editor. Pending
and failed changes follow the same authoritative acknowledgement rules as the
other transport commands.

## Arrangement view

Arrangement view is implemented in this checkout. It makes the section-marked
timeline the central control. Touch drag updates only a local BBT/section
preview. Release sends exactly one `locate_fraction`; command acknowledgement
returns the timeline to the moving authoritative position. Previous Section,
Next Section, Return to Start, and Re-sync remain secondary controls on the
same page.

The existing standalone locate screen remains available as an internal path,
but direct five-inch transport use no longer requires opening a second page to
scrub.

## Blocks view

Blocks view is implemented in this checkout. It does not translate a
meso-block button into an inferred
`locate_fraction`. A block launch is a different musical intention from an
arrangement seek and uses the server's semantic launch operation.

Shadowbox exposes Blocks view only when the authoritative transport object
publishes:

- a stable list of launchable meso-block ids and display labels;
- the active block and any requested, preparing, or queued block;
- per-block availability and a concise unavailable reason;
- launch timing policy such as immediate, next beat, next bar, or end of block;
- the `can_launch_meso_blocks` capability;
- `set_arrangement_mode` with `run` and `hold` modes;
- the `launch_meso_block` operation with `block_id` and optional occurrence
  `macro_index`;
- authoritative `playback_session.elapsed_seconds`.

The operation must own payload preparation, participating-cohort checks,
activation, phase policy, acknowledgement, and failure. Selecting Blocks asks
the server for Hold and changes the view only after acknowledgement; selecting
Arrange asks for Run. The grid preserves server ids and labels, disables
unavailable entries, reflects active/requested state, and paginates eight
blocks at a time. Blocks uses elapsed session time in place of BBT and adds
`arrangement_mode: "hold"` when starting playback without changing the shared
Tempo, authority, or error semantics.

## Acceptance

- The direct-touch Transport page shows Play/Stop, Tempo, position, section,
  timeline, and relevant navigation without a drilldown.
- Timeline preview does not change authoritative state before release.
- One release produces one `locate_fraction` request.
- Tempo drag previews locally and produces one `set_tempo` request on release.
- Tempo edge buttons step exactly one BPM; tapping the value opens the full
  editor.
- Pending and failed commands never masquerade as acknowledged playback state.
- A successful running locate resumes display from the advancing server
  position rather than preserving the preview value.
- Blocks is absent unless `can_launch_meso_blocks` is true.
- Arrange/Blocks mode changes wait for acknowledged Run/Hold state.
- Available blocks launch only through `launch_meso_block`; unavailable blocks
  cannot emit a launch command.
- Blocks shows authoritative active/requested state and elapsed session time.
- Play initiated from Blocks requests held arrangement mode.
- Local fallback presents only the controls it actually owns.
- Encoder-first layouts retain the existing row navigation.

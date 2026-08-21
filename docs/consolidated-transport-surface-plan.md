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

## Blocks view contract

Blocks view must not translate a meso-block button into an inferred
`locate_fraction`. A block launch is a different musical intention from an
arrangement seek and needs a semantic server operation.

Before Shadowbox exposes Blocks view, the authoritative transport object should
publish:

- a stable list of launchable meso-block ids and display labels;
- the active block and any requested, preparing, or queued block;
- per-block availability and a concise unavailable reason;
- launch timing policy such as immediate, next beat, next bar, or end of block;
- a capability such as `can_launch_meso_blocks`;
- a direct operation such as `launch_meso_block` with `block_id`.

The operation must own payload preparation, participating-cohort checks,
activation, phase policy, acknowledgement, and failure. When that contract is
available, the five-inch surface can offer `ARRANGE` and `BLOCKS` views without
changing the shared Play/Stop, Tempo, authority, or error semantics.

## Acceptance

- The direct-touch Transport page shows Play/Stop, Tempo, position, section,
  timeline, and relevant navigation without a drilldown.
- Timeline preview does not change authoritative state before release.
- One release produces one `locate_fraction` request.
- Pending and failed commands never masquerade as acknowledged playback state.
- A successful running locate resumes display from the advancing server
  position rather than preserving the preview value.
- Local fallback presents only the controls it actually owns.
- Encoder-first layouts retain the existing row navigation.

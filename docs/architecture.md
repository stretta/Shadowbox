Shadowbox Architecture

See also:
- `docs/uispec.md` for UI behavior and interaction rules
- `docs/walkthrough.md` for an end-to-end RNBO export and custom editor walkthrough

Primary concepts:
- Instance = a live RNBO runtime object under `/rnbo/inst/<n>`
- Patcher = a loadable RNBO asset under `/rnbo/patchers/<name>`
- Shadowbox is instance-centric at runtime; patchers are used only for lifecycle actions such as add or replace

Module responsibilities:

`encoder.py`
- Hardware input adapter for the rotary encoder or Waveshare HAT controls
- Produces normalized UI events such as step, short press, and long press

`display/`
- Display backend abstraction for OLED and TFT hardware
- Hides device-specific drawing and initialization details from the rest of the app

`renderer.py`
- Pure view layer
- Renders the current UI state to the display
- Should not fetch runner data, mutate backend state, or implement navigation rules

`surfaces/`
- Internal static registry for interfaces representing a complete RNBO instance
- Resolves semantic parameter/state bindings from canonical export identity plus the current live contract
- Rejects missing, duplicate, or incompatible bindings so the ordinary parameter interface remains the safe fallback

`ui.py`
- Primary state machine
- Owns navigation, selection state, editor modes, and action emission
- Builds menus from discovered capabilities instead of hardcoded backend assumptions
- Declares whether the current screen should opt into turbo rendering for animation-heavy views
- Distinguishes:
  - list navigation
  - modal editors
  - instance surfaces
  - instance lifecycle flows

`rnbo.py`
- OSC and OSCQuery adapter
- Fetches the OSCQuery tree and converts it into a normalized snapshot for the UI
- Discovers:
  - instances
  - patchers
  - set capabilities and startup configuration when published
  - saved set names and set load/save paths when published
  - set presets for the currently loaded set when published
  - instance presets
  - parameters
  - OSC message inports and outport state
  - JACK audio and MIDI routing
  - instance lifecycle command paths
  - system audio/status information
- May also provide a small curated set of host-level `SYSTEM` data when that information is not instance-owned and is outside the published OSCQuery tree

`discovery.py`
- Runs Runner and network discovery outside the input/render loop
- Coalesces duplicate requests, rejects stale results, and preserves the last good UI snapshot after transient failures
- Keeps WiFi listing and rescan work separate from ordinary Runner discovery

`shadowbox.py`
- Runtime coordinator
- Wires hardware input, UI state machine, renderer, and RNBO client together
- Executes UI actions against RNBO
- Owns refresh timing, idle dim/sleep behavior, post-action refresh/restart flows, and live OSC state listener registration
- Applies discovery results on the main thread and drives dirty-state rendering

`render_scheduler.py`
- Skips unchanged static frames
- Coalesces burst updates and caps animation-heavy screens at their declared frame rates
- Retains `legacy` scheduling as an explicit rollout/diagnostic mode

`performance.py`
- Provides opt-in, low-rate timing and event summaries through `SHADOWBOX_PERF_LOG`

`keypad.py`
- Optionally opens a configured USB keyboard event device alongside the primary encoder/touch input
- Uses an exclusive evdev grab so numeric-keypad input does not leak to the Linux console behind the framebuffer UI
- Emits context-neutral numeric-keypad events; `ui.py` routes them to the home-screen transport shortcuts, ListSequencer, ListVelSequencer, or the regular numeric parameter editor and ignores them elsewhere
- Reconnects after keypad unplug/replug without restarting Shadowbox

`transpose_control.py`
- Discovers ALSA MIDI input ports through `aconnect -i -l` and follows one designated port by stable client/port name
- Runs a reconnecting `aseqdump` reader and emits only positive-velocity note-on events for the system transpose control path
- Resolves compatible targets by the exact RNBO parameter names `ChromaticTranspose` and `ScalarTranspose`
- Computes shared editable ranges and target agreement without relaying ordinary performance MIDI

Data flow:
1. `discovery.py` runs `rnbo.py` discovery work in background workers
2. `shadowbox.py` applies completed, current-generation results on the main thread
3. `ui.py` exposes derived state for navigation and requests a render when visible state changes
4. User input is converted into UI events by `encoder.py`, optional `keypad.py`, and the designated transpose MIDI monitor
5. `ui.py` turns those events into UI actions
6. `shadowbox.py` executes those actions via `rnbo.py`
7. `renderer.py` draws only when `render_scheduler.py` determines a dirty or animated frame is due
8. Live OSC state updates enter the same UI cache and render-invalidation path

Design rules:
- OSCQuery is the source of truth for instance-scoped runtime structure
- The authoritative runtime view is the currently published live tree, especially live instances under `/rnbo/inst/<n>`
- Published set metadata, view metadata, or layout metadata are not by themselves proof that a live instance exists
- Shadowbox must not synthesize missing runtime instances or reconstruct a graph from non-runtime metadata
- Set load/save/startup controls must map directly to published Runner `sets`/config paths rather than a Shadowbox-owned persistence layer
- Curated set shortcuts are allowed only when they map directly to a verified backend capability with well-defined semantics; for example, `NEW SET` may map to loading a published backend template set
- The UI should be capability-driven; if a backend command or branch is not published, Shadowbox should not invent it
- System controls must remain separate from per-instance controls
- Standardized transpose coordination is system-scoped: exact-name `ChromaticTranspose` and `ScalarTranspose` targets may share a canonical value only under explicit standalone authority
- Existing installations begin with transpose authority unconfigured; network presence or absence never implies an authority transition
- A designated ALSA MIDI note controller is observed beside the performance path and never becomes an inline MIDI relay
- Global transport is exposed only when Runner publishes both `/rnbo/jack/transport/rolling` and `/rnbo/jack/transport/bpm`; it controls musical transport without restarting JACK
- `SYSTEM` may include a narrow, explicitly documented set of host-level status or maintenance features outside OSCQuery when they are not owned by an instance
- Modal selection and edit screens should pause background refresh so discovery does not fight the user
- Parameter editors remain selected from explicit parameter metadata; instance surfaces are selected only from the canonical export name plus successful runtime binding resolution
- Instance surfaces may bind parameters, OSC message inports, and outport state as distinct roles; list-valued controls must remain OSC inports rather than being represented as parameters
- Active surface bindings are re-resolved after discovery snapshots and store stable names/paths rather than depending on old parameter dictionaries
- Terminology should stay consistent:
  - use `Instance` for live runtime objects
  - use `Patcher` for loadable assets
  - avoid `Patch` unless quoting external documentation
  - identify instances by RNBO runtime instance id, not by patcher name or display label

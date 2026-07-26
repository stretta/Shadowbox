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

`shadowbox.py`
- Runtime coordinator
- Wires hardware input, UI state machine, renderer, and RNBO client together
- Executes UI actions against RNBO
- Owns refresh timing, idle dim/sleep behavior, post-action refresh/restart flows, and live OSC state listener registration
- Applies a shared base render cadence and a higher turbo cadence for screens that explicitly opt in through `ui.py`

`keypad.py`
- Optionally opens a configured USB keyboard event device alongside the primary encoder/touch input
- Uses an exclusive evdev grab so numeric-keypad input does not leak to the Linux console behind the framebuffer UI
- Emits only ListSequencer-specific semantic events; `ui.py` ignores them outside that instance surface
- Reconnects after keypad unplug/replug without restarting Shadowbox

Data flow:
1. `rnbo.py` reads OSCQuery and produces a snapshot
2. `ui.py` applies the snapshot and exposes derived state for navigation
3. `renderer.py` draws the current UI state
4. User input is converted into UI events by `encoder.py`
5. `ui.py` turns those events into UI actions
6. `shadowbox.py` executes those actions via `rnbo.py`
7. The app refreshes discovery as needed and repeats

Design rules:
- OSCQuery is the source of truth for instance-scoped runtime structure
- The authoritative runtime view is the currently published live tree, especially live instances under `/rnbo/inst/<n>`
- Published set metadata, view metadata, or layout metadata are not by themselves proof that a live instance exists
- Shadowbox must not synthesize missing runtime instances or reconstruct a graph from non-runtime metadata
- Set load/save/startup controls must map directly to published Runner `sets`/config paths rather than a Shadowbox-owned persistence layer
- Curated set shortcuts are allowed only when they map directly to a verified backend capability with well-defined semantics; for example, `NEW SET` may map to loading a published backend template set
- The UI should be capability-driven; if a backend command or branch is not published, Shadowbox should not invent it
- System controls must remain separate from per-instance controls
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

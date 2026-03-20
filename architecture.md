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
- Hardware input adapter for the rotary encoder and button
- Produces normalized UI events such as rotate, short press, and long press

`display/`
- OLED driver abstraction
- Hides device-specific drawing and initialization details from the rest of the app

`renderer.py`
- Pure view layer
- Renders the current UI state to the display
- Should not fetch runner data, mutate backend state, or implement navigation rules

`ui.py`
- Primary state machine
- Owns navigation, selection state, editor modes, and action emission
- Builds menus from discovered capabilities instead of hardcoded backend assumptions
- Distinguishes:
  - list navigation
  - modal editors
  - instance lifecycle flows

`rnbo.py`
- OSC and OSCQuery adapter
- Fetches the OSCQuery tree and converts it into a normalized snapshot for the UI
- Discovers:
  - instances
  - patchers
  - presets
  - parameters
  - JACK audio and MIDI routing
  - instance lifecycle command paths
  - system audio/status information

`shadowbox.py`
- Runtime coordinator
- Wires hardware input, UI state machine, renderer, and RNBO client together
- Executes UI actions against RNBO
- Owns refresh timing, idle dim/sleep behavior, post-action refresh/restart flows, and live OSC state listener registration

Data flow:
1. `rnbo.py` reads OSCQuery and produces a snapshot
2. `ui.py` applies the snapshot and exposes derived state for navigation
3. `renderer.py` draws the current UI state
4. User input is converted into UI events by `encoder.py`
5. `ui.py` turns those events into UI actions
6. `shadowbox.py` executes those actions via `rnbo.py`
7. The app refreshes discovery as needed and repeats

Design rules:
- OSCQuery is the source of truth for runtime structure
- The UI should be capability-driven; if a backend command or branch is not published, Shadowbox should not invent it
- System controls must remain separate from per-instance controls
- Modal selection and edit screens should pause background refresh so discovery does not fight the user
- Terminology should stay consistent:
  - use `Instance` for live runtime objects
  - use `Patcher` for loadable assets
  - avoid `Patch` unless quoting external documentation

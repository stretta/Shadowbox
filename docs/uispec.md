Shadowbox UI Specification (draft)

1. Purpose

Shadowbox is a hardware UI for RNBO Runner that:
- discovers structure via OSCQuery
- presents that structure using a single encoder and button
- allows editing of parameters and routing that are explicitly published
- does not invent structure that is not present in the published data

The UI is organized around RNBO instances.

2. Source of Truth

- Instance-scoped runtime data comes from OSCQuery
- Shadowbox may store local UI state such as cursor position or startup preferences
- Shadowbox must not invent patch, graph, preset, or routing structures that are not published
- `SYSTEM` may expose a small curated set of host-level status or maintenance actions that are not owned by any instance and may come from local OS/integration data instead of OSCQuery
- Non-OSCQuery `SYSTEM` features must be explicit, minimal, and documented; they must not be generalized into arbitrary host inspection

Definitions:
- Instance = one live published RNBO instance under `/rnbo/inst/<n>`
- Patcher = a loadable RNBO asset published under `/rnbo/patchers/<name>`
- Node = avoid this term in the UI and implementation unless quoting backend terminology; when it appears in backend descriptions, it refers to an instance
- Patch = avoid this term in the UI and implementation because it is ambiguous across RNBO authoring, patchers, and live instances
- Parameter = editable node under an instance `params` branch
- Preset = published preset entry for an instance
- Audio routing = published JACK audio connections for an instance
- MIDI routing = published JACK MIDI connections for an instance
- System = global RNBO/JACK/device information not owned by a single instance

3. Menu Hierarchy

TOP
INSTANCES
SYSTEM

INSTANCES
<INSTANCE>
<INSTANCE>
...
ADD INSTANCE
REMOVE INSTANCE

<INSTANCE>
PARAMETERS
PRESETS
AUDIO
MIDI

AUDIO
INPUTS
OUTPUTS

MIDI
INPUTS
OUTPUTS

SYSTEM
STATUS
AUDIO
NETWORK
STARTUP
MAINT

Rules:
- Instances are discovered from OSCQuery, not hardcoded
- Instance labels should use published alias/name when available
- `ADD INSTANCE` should appear in the `INSTANCES` menu only if the backend exposes a supported command path for creating an instance from a patcher
- `SYSTEM` is always present
- Outside `SYSTEM`, only published branches appear; empty branches may render as empty lists, but no synthetic content should be added

4. Navigation Model

Input:
- One encoder (delta)
- One button

Behavior:
- Encoder moves selection
- Button press enters submenu or confirms selection
- Navigation uses a stack

Back Behavior:
- First item in any submenu is `..` and returns to parent
- Long press acts as a universal back/cancel shortcut
- No hidden gestures beyond short press, long press, and encoder rotation

Navigation rules:
- List and menu screens should prefer visible `..` navigation
- Long press should always return to the previous context
- In deferred modal editors, long press cancels uncommitted edits
- In live modal editors, long press exits without reverting already committed changes
- In list screens, long press is a shortcut for back and does not replace `..`

5. Data Model (Conceptual)

MenuNode:
- label
- kind
- children
- reference

Instance:
- id or index
- label
- params
- presets
- audio routing
- midi routing

Parameter:
- name
- OSC path
- type
- value
- metadata

Preset:
- name
- load path

RoutingPort:
- label
- direction
- current connections
- available targets
- OSC path

6. Instance Discovery

Instances are derived from the OSCQuery `inst` branch.

For each instance, Shadowbox should prefer:
1. published alias if available
2. published instance name
3. numeric instance id

The UI should treat each instance as an independent control scope.

6a. Instance Lifecycle

If the backend exposes instance lifecycle commands, Shadowbox should present explicit lifecycle actions.

Expected model:
- user chooses `INSTANCES`
- user chooses `ADD INSTANCE`
- Shadowbox presents the list of available patchers
- selecting a patcher creates a new instance through the published backend command

If the backend exposes indexed load/unload commands, Shadowbox should also support:
- `REPLACE INSTANCE`
  - user starts from an existing instance
  - Shadowbox presents the list of available patchers
  - selecting a patcher replaces the contents of that instance slot through the published backend command
- `REMOVE INSTANCE`
  - user may start either from an existing instance menu or from the `INSTANCES` menu
  - in the `INSTANCES` menu, `REMOVE INSTANCE` opens a picker of loaded instances
  - selecting an instance leads to a confirmation screen
  - Shadowbox issues the published unload/remove command for that instance
  - destructive actions should require an explicit confirmation step

Rules:
- patcher browsing is distinct from instance browsing
- patchers are templates/types; instances are live runtime objects
- `ADD INSTANCE`, `REPLACE INSTANCE`, and `REMOVE INSTANCE` must each correspond to a published backend capability
- if a lifecycle capability is not published, Shadowbox must not invent it in the UI
- when the backend uses the word `node`, Shadowbox may map that action into instance lifecycle language in the UI
- raw instance `config` and `control` branches should remain hidden unless a specific published capability is promoted into the curated UI

7. Parameters

Parameters come from the instance `params` branch.

Parameter type is determined from published metadata and attributes.

Supported editor types:
- numeric
- bool
- enum
- ttid
- step16
- pitch_display

Parameter rules:
- Only editable published parameters are shown
- Helper nodes such as normalized/index/meta may be hidden
- Display should favor readable parameter names over raw transport detail

Editor behavior:
- Continuous numeric editors may update live while rotating
- Deferred discrete editors preview locally while rotating and commit on short press
- Long press in a deferred editor cancels and restores the original value
- Some custom editors may commit changes immediately during editing
- Long press in a live editor exits the editor and does not revert already committed changes
- Bool parameters use a dedicated boolean editor
- Enum parameters use a list selector, regardless of option count
- TTID uses a specialized editor only when the parameter metadata explicitly includes `editor: "ttid"`
- `step16` uses a specialized live editor when the parameter metadata explicitly includes `editor: "step16"`; its default runtime state key is `step16_playhead` and may be overridden with `playhead_state`
- `pitch_display` uses a specialized live viewer when the parameter metadata explicitly includes `editor: "pitch_display"`; its default runtime state keys are `pitch_name` and `pitch_cents` and may be overridden with `pitch_state` and `cents_state`

8. Presets

Presets come from the instance `presets` branch.

Expected behavior:
- available preset names are read from the published preset entries list
- selecting a preset sends its name to the published preset load path

Shadowbox does not:
- create its own preset format
- infer preset groups that are not published
- cache preset state beyond minimal UI convenience

9. Audio Routing

Audio routing comes from the instance JACK branch.

Audio UI should expose:
- instance audio inputs
- instance audio outputs
- current connections
- available JACK targets/sources when published

Rules:
- routing is per instance
- current connections must reflect published state
- if multiple targets are allowed by the backend, the UI may constrain editing to a simple selection model if needed

10. MIDI Routing

MIDI routing mirrors audio routing where published.

MIDI UI should expose:
- instance MIDI inputs
- instance MIDI outputs
- current connections
- available JACK MIDI targets/sources

Rules:
- empty MIDI branches are valid
- absence of current connections is not the same as absence of ports

11. System

`SYSTEM` contains global controls and status not owned by a single instance.

Unlike instance browsing and editing, `SYSTEM` may include a tightly scoped set of curated host-level information or actions that are sourced outside OSCQuery when they are not instance-owned and cannot be expressed through the published RNBO tree.

Initial system areas:
- status
- audio device selection
- network status
- startup behavior
- maintenance actions

Rules:
- System must remain clearly separate from per-instance editing and routing
- Per-instance structure, lifecycle, parameters, presets, and routing remain OSCQuery/published-command driven
- Non-OSCQuery `SYSTEM` entries must be explicitly chosen product features, not a generic escape hatch for backend gaps
- Host-derived `SYSTEM` data should stay read-only unless there is a deliberately integrated control path for that feature

12. Rendering Contract

Each screen defines only:
- visible items
- selected index
- optional value or routing display

Each screen responds to:
- encoder movement
- button press
- long press

Screens must not:
- modify published hierarchy
- invent new structural categories
- bypass navigation rules

Display rendering rules:
- Navigation behavior and screen semantics are shared across display types
- Visual presentation may differ by display class
- OLED rendering should prioritize compactness, legibility, and graphical simplicity
- TFT rendering may use richer typography, banners, spacing, and other display-specific visual treatment
- Display-specific styling must not change the underlying navigation model or screen meaning

13. Constraints

- UI must stay small and readable on OLED hardware
- hierarchy should reflect published OSCQuery structure as directly as possible
- local persistence should be limited to UI convenience, not mirrored domain state
- no feature expansion without corresponding published data

14. Explicit Non-Goals

Shadowbox will not:
- invent a synthetic graph tree unrelated to published instances
- create or manage its own preset system
- expose editing for unpublished backend capabilities
- expose raw instance `config` or `control` branches as generic menu sections
- support workflows requiring multiple simultaneous controls
- become a general RNBO administration panel

15. Open Questions

- Whether `REPLACE INSTANCE` should preserve routing automatically or rely on backend behavior
- Whether routing should support only single-target selection or multi-connection editing
- Whether aliases should be editable if published, or display-only
- Whether `INSTANCES` should remain named `INSTANCES` or be labeled `GRAPHS` in the final UI while still mapping to instances internally

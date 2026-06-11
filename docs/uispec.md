Shadowbox UI Specification (draft)

1. Purpose

Shadowbox is a hardware UI for RNBO Runner that:
- discovers structure via OSCQuery
- presents that structure using a simple step/press input model
- allows editing of parameters and routing that are explicitly published
- does not invent structure that is not present in the published data

The UI is organized around live RNBO instances, with a user-facing top level that separates sets, instances, and system concerns.

2. Source of Truth

- Instance-scoped runtime data comes from OSCQuery
- Shadowbox may store limited local UI state such as cursor position or saved audio-device selection
- Shadowbox must not invent patch, set, preset, routing, or graph structures that are not published
- `SYSTEM` may expose a small curated set of host-level status or maintenance actions that are not owned by any instance and may come from local OS/integration data instead of OSCQuery
- Non-OSCQuery `SYSTEM` features must be explicit, minimal, and documented; they must not be generalized into arbitrary host inspection

Definitions:
- Instance = one live published RNBO instance under `/rnbo/inst/<n>`
- Patcher = a loadable RNBO asset published under `/rnbo/patchers/<name>`
- Set = the user-facing term for the current whole-system runtime state and its saved variants, backed by Runner-published `sets` paths
- Set Preset = a Runner-managed snapshot of parameter state for the currently loaded set, published under the backend `sets/presets` branch
- Graph = avoid this term in user-facing UI copy; it may still appear in backend or implementation descriptions when referring to RNBO Runner internals or graph-editor compatibility
- Node = avoid this term in the UI and implementation unless quoting backend terminology; when it appears in backend descriptions, it refers to an instance
- Patch = avoid this term in the UI and implementation because it is ambiguous across RNBO authoring, patchers, and live instances
- Parameter = editable node under an instance `params` branch
- Preset = published preset entry for an instance
- Audio routing = published JACK audio connections for an instance
- MIDI routing = published JACK MIDI connections for an instance
- System = global RNBO/JACK/device information not owned by a single instance

3. Menu Hierarchy

TOP
SETS
INSTANCES
SYSTEM

SETS
CURRENT SET
NEW SET
LOAD SET
SAVE SET
STARTUP

LOAD SET
<SAVED SET>
<SAVED SET>
...

STARTUP
RESTORE LAST
LOAD NAMED SET
OFF

LOAD NAMED SET
<SAVED SET>
<SAVED SET>
...

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
ABOUT
MAINT

Rules:
- Instances are discovered from OSCQuery, not hardcoded
- `SETS` is a user-facing top-level label and must not imply a separate Shadowbox-owned graph model
- `SETS` is backed by published Runner `sets` and startup capabilities when those paths are available
- `CURRENT SET` reflects the currently published live set state and current set identity only
- `NEW SET` may appear as a curated action only when the backend publishes a loadable template set and Shadowbox implements the action by invoking the published set load path
- `NEW SET` must not imply a separate Shadowbox-owned graph creation or clear command
- `LOAD SET` loads a published set by name through the published backend set load path
- `SAVE SET` saves the current published live set through the published backend set save path
- `STARTUP` edits published Runner startup configuration only; it does not implement local boot restore logic
- Instance labels should use published alias/name when available
- `ADD INSTANCE` should appear in the `INSTANCES` menu only if the backend exposes a supported command path for creating an instance from a patcher
- `SYSTEM` is always present
- Outside `SYSTEM`, only published branches appear; empty branches may render as empty lists, but no synthetic content should be added

4. Navigation Model

Input:
- One normalized step control
- One normalized press control

Behavior:
- Step input moves selection
- Button press enters submenu or confirms selection
- Navigation uses a stack

Back Behavior:
- First item in any submenu is `..` and returns to parent
- Long press acts as a universal back/cancel shortcut
- No hidden gestures beyond short press, long press, and step movement

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

Set curation rule:
- Shadowbox may promote a small number of set actions into friendlier UI labels when they map to a verified published backend capability with stable semantics
- The canonical example is `NEW SET`, which is valid only when it is implemented through the published backend set load path
- Shadowbox must not expose `CLEAR SET` as a synthetic action unless the backend publishes an equally explicit and verified command or backend-set-backed behavior for it

7. Parameters

Parameters come from the instance `params` branch.

Parameter type and UI behavior are determined from published metadata and attributes.

Supported parameter presentations:
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
- Metadata is the general mechanism for parameter UI hints, not only custom editor selection

Recognized metadata categories:
- Editor selection: `editor`
- Display hints: `unit`, `units`, `display_precision`, `display_as`
- Edit behavior: `edit_step`, `edit_as`, `bool`, `is_bool`, `boolean`
- Runtime state wiring: `playhead_state`, `pitch_state`, `cents_state`, `ui_role`
- Routing display: `label` for friendly input/output names

Metadata behavior rules:
- `editor` selects a specialized editor only for supported custom screens such as `ttid`, `step16`, and `pitch_display`
- `unit` and `units` provide a display suffix only
- `display_precision` controls decimal formatting only and does not imply input step size
- `edit_step` controls step increment only and does not imply display formatting
- `display_as` and `edit_as` are semantic UI hints; for example, `int` means the value should be rendered or edited as integer-like even if the published transport value is float-like
- Boolean hints in metadata explicitly opt a parameter into the bool editor
- `ui_role` helps runtime state lookups match a published state value to a UI-specific role such as a custom editor feed
- `label` overrides the displayed name for published routing inputs/outputs without changing their control path
- If metadata is absent or malformed, Shadowbox does not infer bool or integer intent from range or transport type; it falls back to numeric behavior, except that RNBO enum parameters still use the enum selector
- Shadowbox can read metadata either from the parameter's `meta` node or from direct scalar child nodes published into the OSCQuery tree, such as `editor`, `display_name`, or `ui_role`

Editor behavior:
- Continuous numeric editors may update live while rotating
- Deferred discrete editors preview locally while rotating and commit on short press
- Long press in a deferred editor cancels and restores the original value
- Some custom editors may commit changes immediately during editing
- Long press in a live editor exits the editor and does not revert already committed changes
- Boolean parameters can toggle directly from the parameter list when explicitly marked as bool; they stay opt-in via metadata and do not need the deeper edit screen in the first pass
- Enum parameters use a list selector when RNBO publishes an explicit enum value list
- TTID uses a specialized editor only when the parameter metadata explicitly includes `editor: "ttid"`
- `step16` uses a specialized live editor when the parameter metadata explicitly includes `editor: "step16"`; its default runtime state key is `step16_playhead` and may be overridden with `playhead_state`
- `pitch_display` uses a specialized live viewer when the parameter metadata explicitly includes `editor: "pitch_display"`; its default runtime state keys are `pitch_name` and `pitch_cents` and may be overridden with `pitch_state` and `cents_state`
- Numeric parameters may be presented as integer-style controls only when metadata such as `display_as: "int"` or `edit_as: "int"` is present, even if RNBO Runner publishes the raw value as float-like

8. Presets

Presets come from the instance `presets` branch.

Expected behavior:
- available preset names are read from the published preset entries list
- selecting a preset sends its name to the published preset load path

If the backend publishes preset save or rename capabilities, Shadowbox should reuse the same naming UI used for set save and rename actions rather than introducing a separate preset-specific editor.

Shadowbox does not:
- create its own preset format
- infer preset groups that are not published
- cache preset state beyond minimal UI convenience

8a. Set Presets

Set presets come from the set preset branch `/rnbo/inst/control/sets/presets`.

Expected behavior:
- available set preset names are read from the published set preset load range
- selecting a set preset sends its name to the published set preset load path
- set preset save, rename, and delete operations are only shown when their published paths exist

Set presets are distinct from:
- saved sets, which manage whole set/session recall
- instance presets, which come from each live instance `presets` branch

8b. Shared Naming UI

Naming should be handled by one shared modal flow that can be invoked by:
- `SAVE SET`
- `RENAME SET` if a published rename capability is added
- `SAVE SET PRESET` for set presets if a published set preset-save capability exists
- `RENAME SET PRESET` for set presets if a published set preset-rename capability exists
- `SAVE PRESET` if a published preset-save capability exists
- `RENAME PRESET` if a published preset-rename capability exists

Rules:
- The naming UI is only shown for published save/rename capabilities; Shadowbox must not invent local preset or set storage
- Saving and renaming should feel identical apart from the action label and the initial text value
- The current generated fallback name remains useful as the initial draft for `SAVE SET`, but it should be editable before commit and always remain available as an explicit regenerate action
- Renaming should preload the current item name
- The naming flow must work on the existing step/press input model without hidden gestures

Proposed invocation model:
- choosing `SAVE SET` opens `NAME EDITOR` instead of immediately dispatching the generated fallback name
- choosing `SAVE PRESET` does the same when that published capability exists
- choosing `RENAME SET`, `SAVE SET PRESET`, `RENAME SET PRESET`, or `RENAME PRESET` opens `NAME EDITOR` seeded with the current item name as appropriate
- on confirm, Shadowbox dispatches the published command with the final text value
- on cancel, no backend command is sent

Proposed editor structure:
- header shows the action context, such as `SAVE SET`, `SAVE SET PRESET`, `RENAME SET`, `RENAME SET PRESET`, `SAVE PRESET`, or `RENAME PRESET`
- first row shows the current draft name, with an insertion cursor
- second row is a compact character wheel or palette
- final row exposes explicit actions: `SAVE` or `RENAME`, `GENERATE NAME`, `ADD DATE`, `DELETE CHAR`, `CANCEL`

Interaction model:
- step movement changes the currently focused character or action
- short press commits the current choice
- long press cancels the naming flow and returns to the previous screen

Recommended editing behavior:
1. The editor opens with a prefilled draft and the insertion point at the end
2. Rotating while the insertion point is active cycles through a constrained character set
3. Short press accepts the current character and advances to the next position
4. Selecting `GENERATE NAME` replaces the current draft with a fresh suggested name
5. Selecting `ADD DATE` appends a compact date or datetime token to the current draft
6. Selecting `DELETE CHAR` removes the previous character
7. Selecting `SAVE` or `RENAME` submits the draft

Generated-name guidance:
- `SAVE SET` should open with a generated suggestion derived from the current set name when available, otherwise a neutral base such as `set`
- `SAVE PRESET` should open with a generated suggestion derived from the current preset or instance label when available, otherwise a neutral base such as `preset`
- generated names may include a timestamp suffix to keep one-click saves unique
- `GENERATE NAME` should remain available even when the user has already edited the draft, so they can quickly reset to a fresh suggestion
- `ADD DATE` should be available independently because date stamping is useful even when the base name is handwritten

Recommended character set:
- uppercase letters
- lowercase letters
- digits
- space
- `-` and `_`

Recommended constraints:
- trim leading and trailing whitespace on submit
- collapse repeated internal spaces
- reject an empty final name
- keep names within a compact display-safe limit such as 24 characters
- if the backend reports a conflict, return to the naming UI with the attempted name preserved
- when `GENERATE NAME` or `ADD DATE` would exceed the display-safe limit, Shadowbox may trim the base portion before applying the suffix rather than dropping the suffix silently

Conflict handling:
- For save actions, if the target name already exists and the backend distinguishes overwrite from create, Shadowbox should show a confirmation screen before overwriting
- For rename actions, if the requested name already exists, Shadowbox should reject the action and return to the editor with a brief conflict message
- If the backend does not publish enough information to distinguish these cases, Shadowbox should send the requested name and reflect the backend result on refresh rather than guessing

Rendering guidance:
- OLED should use a minimal single-line text preview and a compact bottom-row action list
- TFT may show a larger text preview and a clearer per-character cursor treatment
- The visual treatment may differ by display, but both displays must preserve the same navigation semantics

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
- parameter MIDI learn and clear actions when RNBO publishes learn/report state

Rules:
- empty MIDI branches are valid
- absence of current connections is not the same as absence of ports
- learned CC mappings should be displayed beside mapped parameters without replacing the parameter label or value
- saved instance MIDI mapping profiles may be reapplied when an instance is added or replaced, but only for parameters that still match by name

11. System

`SYSTEM` contains global controls and status not owned by a single instance.

Unlike instance browsing and editing, `SYSTEM` may include a tightly scoped set of curated host-level information or actions that are sourced outside OSCQuery when they are not instance-owned and cannot be expressed through the published RNBO tree.

Initial system areas:
- status
- audio device selection
- network status and direct Ethernet rescue setup
- about screen
- maintenance actions

Rules:
- System must remain clearly separate from per-instance editing and routing
- Per-instance structure, lifecycle, parameters, presets, and routing remain OSCQuery/published-command driven
- Non-OSCQuery `SYSTEM` entries must be explicitly chosen product features, not a generic escape hatch for backend gaps
- Host-derived `SYSTEM` data should stay read-only unless there is a deliberately integrated control path for that feature
- `NETWORK` may include a local `DIRECT ETHERNET SETUP` action that manages a fixed fallback address on `eth0` for headless recovery
- Direct Ethernet setup must be tightly scoped: touch only the configured Ethernet interface and only the configured fallback subnet

Live runtime authority:
- Shadowbox reflects the currently published live runtime state
- Live instances under `/rnbo/inst/<n>` are authoritative for what exists now
- Published set metadata, view metadata, or layout metadata do not by themselves establish that an instance exists
- Shadowbox must not reconstruct or imply missing live instances from saved set metadata
- Multiple instances of the same patcher are valid and must remain distinct by runtime instance id
- Loading or saving a set means invoking published Runner set operations and then rediscovering the resulting live runtime state

12. Rendering Contract

Each screen defines only:
- visible items
- selected index
- optional current index or current value marker
- optional value or routing display

Each screen responds to:
- step movement
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
- Where a menu has both a cursor position and a current state, the cursor and current state must remain visually distinct
- Menu rows should follow one shared semantic styling model:
- selected row = cursor/highlight only
- current row = bold or semibold
- secondary state such as occupied/shared/dirty = italic
- current plus secondary state = bold italic
- action rows such as save/rename may use a distinct action weight, but they must not be styled as current unless they actually represent the current live choice

13. Constraints

- UI must stay small and readable on OLED hardware
- hierarchy should reflect published OSCQuery structure as directly as possible
- local persistence should be limited to UI convenience, not mirrored domain state
- local persistence must not be presented as set or session restoration
- no feature expansion without corresponding published data

14. Explicit Non-Goals

Shadowbox will not:
- invent a synthetic set or graph tree unrelated to published instances
- create or manage its own preset system
- expose editing for unpublished backend capabilities
- expose raw instance `config` or `control` branches as generic menu sections
- support workflows requiring multiple simultaneous controls
- become a general RNBO administration panel

15. Open Questions

- Whether `REPLACE INSTANCE` should preserve routing automatically or rely on backend behavior
- Whether routing should support only single-target selection or multi-connection editing
- Whether aliases should be editable if published, or display-only

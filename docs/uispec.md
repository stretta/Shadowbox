Shadowbox UI Specification

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
- Shadowbox must not invent patch, set, set preset, instance preset, routing, or graph structures that are not published
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
- Instance Preset = published preset entry for an instance
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
LOAD SET

CURRENT SET
SAVE
SAVE AS...
SET PRESETS
AUDIO OVERVIEW
MIDI OVERVIEW

LOAD SET
<SAVED SET>
<SAVED SET>
...

SET PRESETS
<SET PRESET>
<SET PRESET>
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
<INSTANCE SURFACE, WHEN COMPATIBLE>
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
TRANSPORT
STARTUP
NETWORK
HDMI
UPDATE
REBOOT
ABOUT
MAINT

Rules:
- Instances are discovered from OSCQuery, not hardcoded
- `SETS` is a user-facing top-level label and must not imply a separate Shadowbox-owned graph model
- `SETS` is backed by published Runner `sets` and startup capabilities when those paths are available
- `CURRENT SET` reflects the currently published live set state and current set identity only; it is the place for saving the current set, viewing routing overviews, and entering set presets
- `NEW SET` may appear as a curated action only when the backend publishes a loadable template set and Shadowbox implements the action by invoking the published set load path
- `NEW SET` must not imply a separate Shadowbox-owned graph creation or clear command
- `LOAD SET` opens the saved-set load screen and loads a published set by name through the published backend set load path
- `SET PRESETS` appears inside `CURRENT SET` when the backend publishes set preset capabilities; it must not replace `LOAD SET`
- `SAVE` and `SAVE AS...` in `CURRENT SET` save the current published live set through the published backend set save path
- `STARTUP` edits published Runner startup configuration only; it does not implement local boot restore logic
- Instance labels preserve a unique published `name_alias`; aliases duplicated
  case-insensitively receive a `-<runtime-id>` suffix, instances without an
  alias display as `<export-name>-<runtime-id>`, and instances without either
  value display as `instance <runtime-id>`
- Registered instance surfaces are selected by the canonical exported patcher `name`, never by the mutable instance label
- A registered surface appears as the first instance-menu item only when the live instance satisfies that surface's required parameter and state contract
- `PARAMETERS` remains available for every instance even when an instance surface is present
- Instance surfaces use their own navigation and focus state; opening one must not alter parameter-list selection
- Back, short press where not otherwise assigned, and long press return from an instance surface to that instance's menu
- The Organ surface maps the canonical nine footages to the export's continuous `-96..0 dB` tonewheel parameters; top is `-96 dB`/off and bottom is `0 dB`/full-on
- The ListSequencer surface binds its seven ordered list fields directly to OSC message inports: Steps, Secondary Steps, Primary Rotation, Secondary Rotation, Octave, Velocity, and Duration
- ListSequencer renders those fields as single-line, full-height values prefixed by `Stp`, `Stp2`, `Rot`, `Rot2`, `Oct`, `Vel`, and `Dur`; each field has a `ROT` action that freshly reads the sequencer list, moves its first item to the end, and sends the complete rotated list back
- ListSequencer uses a compact `1..9 / SPC 0 DEL` keypad, a contextual sign control for signed fields, and an explicit `SEND` action so incomplete multi-digit entries are never transmitted
- ListSequencer hydrates fields through matching `<InportName>Ack` outports after sending the export's `-999` read request; ACK state is not represented as a parameter
- The ListVelSequencer surface binds eight ordered velocity-list rows to `1row` through `8row`, requires the corresponding `1map` through `8map` pitch parameters and `1mute` through `8mute` mute parameters, shows each row's current pitch beside its row number, and provides compact `M` and `ROT` buttons for muting or freshly reading and forward-rotating each row
- ListVelSequencer uses the same compact keypad and ACK-backed `-999` hydration pattern as ListSequencer; `SEND ROW` transmits only the selected row as one atomic list and accepts MIDI velocity values from `0` through `127`
- ListVelSequencer pitch maps remain ordinary parameters under `PARAMETERS`; the instance surface displays their live values for row context without synthesizing another pitch editor
- The `ShadowScoreClient` surface is read-only and local-first: it requires exactly one `current_stage`, `playback_debug`, `midi_debug`, and `shadowscore_ack` outport, presents the current chord as the primary content, identifies `current_stage` as zero-based, and treats the live `midi_debug` shape as `[pitch, velocity, duration_ms]` while labeling it as the last emitted MIDI event rather than current sound
- ShadowScoreClient recent-event history is transient UI state derived from distinct valid `playback_debug` updates while the surface is open; it must not infer future score events or require ShadowscoreServer connectivity
- A zero-note `playback_debug` event must not erase the last useful chord display: retain the last non-rest chord with subdued styling, identify it explicitly as `LAST CHORD`, show the current `REST` count, and continue advancing the live stage and recent-event ribbon
- The AnalogSequencer surface keeps its 16-column stage layout and adds compact `LOW` and `HIGH` MIDI-note rails in the footer. Those editor-only bounds default to MIDI 24 through 72, scale touch and encoder pitch edits across the selected interval, and clip existing stage values only when the user changes a boundary; they do not alter the RNBO parameter range or add snapshot state.
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
- Navigable direct-touch headers below the home screen provide Back on the left and Home on the right; Home clears the nested navigation context and returns directly to the top-level cards
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
- instance presets
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

1. a unique published alias, unchanged
2. a duplicated published alias plus `-<runtime-id>`
3. published instance name plus `-<runtime-id>`
4. `instance <runtime-id>`

Duplicate aliases are compared case-insensitively. These labels are
presentation only; actions, refresh, and selection continue to use the raw
Runner instance id.

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
- `editor` selects a specialized parameter editor only for supported custom screens such as `ttid` and `step16`; surface resolvers may also use metadata such as `pitch_display` or `scope` as a binding hint
- `unit` and `units` provide a display suffix only
- `display_precision` controls decimal formatting only and does not imply input step size
- `edit_step` controls step increment only and does not imply display formatting
- `display_as` and `edit_as` are semantic UI hints; for example, `int` means the value should be rendered or edited as integer-like even if the published transport value is float-like
- Boolean hints in metadata explicitly opt a parameter into the bool editor
- `ui_role` helps runtime state lookups match a published state value to a UI-specific role such as a custom editor feed
- `label` overrides the displayed name for published routing inputs/outputs without changing their control path
- If metadata is absent or malformed, Shadowbox does not infer bool or integer intent from range or transport type; it falls back to numeric behavior, except for explicitly published RNBO enum value lists
- Shadowbox can read metadata either from the parameter's `meta` node or from direct scalar child nodes published into the OSCQuery tree, such as `editor`, `display_name`, or `ui_role`

Editor behavior:
- Continuous numeric editors may update live while rotating
- Deferred discrete editors preview locally while rotating and commit on short press
- Long press in a deferred editor cancels and restores the original value
- Some custom editors may commit changes immediately during editing
- Long press in a live editor exits the editor and does not revert already committed changes
- Boolean parameters toggle directly from the parameter list when explicitly marked as bool and render as inline switches on the touch UI
- An enum whose complete advertised value list is exactly `Off` and `On` also renders and behaves as an inline switch; Shadowbox sends the original advertised string value
- All other enum parameters use a list selector when RNBO publishes an explicit enum value list; arbitrary two-choice enums are not inferred to be booleans
- TTID uses a specialized editor only when the parameter metadata explicitly includes `editor: "ttid"`
- `step16` uses a specialized live editor when the parameter metadata explicitly includes `editor: "step16"`; its default runtime state key is the one-based `current_stage` outport and may be overridden with `playhead_state` for legacy or custom zero-based feeds
- Numeric parameters may be presented as integer-style controls only when metadata such as `display_as: "int"` or `edit_as: "int"` is present, even if RNBO Runner publishes the raw value as float-like

8. Instance Presets

Instance presets come from the instance `presets` branch.

Expected behavior:
- available instance preset names are read from the published preset entries list
- selecting an instance preset sends its name to the published preset load path

If the backend publishes instance preset save or rename capabilities, Shadowbox should reuse the same naming UI used for set save and rename actions rather than introducing a separate preset-specific editor.

Shadowbox does not:
- create its own instance preset format
- infer instance preset groups that are not published
- cache instance preset state beyond minimal UI convenience

8a. Set Presets

Set presets come from the set preset branch `/rnbo/inst/control/sets/presets`.

Expected behavior:
- available set preset names are read from the published set preset load range
- selecting a set preset sends its name to the published set preset load path
- set preset save, rename, and delete operations are only shown when their published paths exist
- set presets are reached from `CURRENT SET > SET PRESETS`
- saved sets are reached from `SETS > LOAD SET`

Set presets are distinct from:
- saved sets, which manage whole set/session recall
- instance presets, which come from each live instance `presets` branch

Shadowbox must keep saved-set loading and set-preset loading as separate screens. `LOAD SET` talks to the published set load path; `SET PRESETS` talks to the published `sets/presets` load path for the currently loaded set.

8b. Shared Naming UI

Naming should be handled by one shared modal flow that can be invoked by:
- `SAVE SET`
- `RENAME SET` if a published rename capability is added
- `SAVE SET PRESET` for set presets if a published set preset-save capability exists
- `RENAME SET PRESET` for set presets if a published set preset-rename capability exists
- `SAVE PRESET` if a published preset-save capability exists
- `RENAME PRESET` if a published preset-rename capability exists

Rules:
- The naming UI is only shown for published save/rename capabilities; Shadowbox must not invent local set, set preset, or instance preset storage
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
- `SAVE SET PRESET` should open with a generated suggestion derived from the current set preset or set name when available, otherwise a neutral base such as `preset`
- `SAVE PRESET` should open with a generated suggestion derived from the current instance preset or instance label when available, otherwise a neutral base such as `preset`
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
- acknowledged ShadowscoreServer transport with explicit local RNBO Runner fallback
- set startup configuration when Runner publishes startup load/save controls
- standalone chromatic/scalar transpose coordination and designated MIDI controller selection
- network status, WiFi network selection, and direct Ethernet rescue setup
- persistent HDMI mirror enable/disable on the Waveshare 5-inch DSI build
- persistent, opt-in touch feedback on the Waveshare 5-inch DSI build
- software update status and a fast-forward update action for git checkouts
- guarded full-system reboot, with Cancel selected by default
- about screen
- maintenance actions

Rules:
- The home screen presents `SETS`, `INSTANCES`, `SYSTEM`, and a state-aware global transport action card; the last card reads `PLAY` when stopped, `STOP` when running, or `STARTING` / `STOPPING` while a server command awaits acknowledgement
- In server mode the touch home card shows BPM, active section, and concise sync health; in fallback mode it shows BPM and `LOCAL`. Selecting the context pill opens the shared tempo editor and returns to the home screen on exit
- On the home screen only, numeric-keypad `Enter` explicitly starts transport and `0` explicitly stops it; these are not toggle commands
- System must remain clearly separate from per-instance editing and routing
- Per-instance structure, lifecycle, parameters, instance presets, and routing remain OSCQuery/published-command driven
- Non-OSCQuery `SYSTEM` entries must be explicitly chosen product features, not a generic escape hatch for backend gaps
- Host-derived `SYSTEM` data should stay read-only unless there is a deliberately integrated control path for that feature
- `TRANSPORT` is a global control surface, not an instance parameter editor. It uses the canonical ShadowscoreServer object when connected and otherwise writes only the published Runner `/rnbo/jack/transport/rolling` and `/rnbo/jack/transport/bpm` paths
- When both sources are available, Transport shows radio-style `LOCAL` and `SCORE` authority controls. The per-set choice is locked while either transport is running or a Score command is pending. Local-instance sets without a `ShadowScoreClient` initially choose Local
- Transport authority is independent of the Score-only Arrange/Blocks workflow. Moving between Local and Score must preserve the acknowledged arrangement mode and block state and must not issue `set_arrangement_mode`
- Server mode exposes active section, bars/beats/ticks position, sync health, Previous/Next Section, Return to Start, and capability-gated Re-sync; UI state follows acknowledged objects and rejects older revisions
- On the five-inch direct-touch UI, `TRANSPORT` is a consolidated performance surface with Play/Stop, Tempo, authoritative position and section, a section-marked arrangement scrubber, and secondary section navigation on one page. The scrubber is interactive only when the server advertises `can_locate`. Dragging changes a local preview; exactly one `locate_fraction` command is committed on release. Pending and failed seeks must never be rendered as acknowledged position
- The consolidated Tempo card uses relative horizontal drag for whole-BPM preview and commits exactly one `set_tempo` on release. Its edge buttons step one BPM. A stationary tap opens the full tempo editor. Pending or failed changes must return to acknowledged server tempo rather than preserving an unacknowledged preview
- When the server advertises `can_launch_meso_blocks`, the five-inch Transport
  surface exposes `ARRANGE` and `BLOCKS`. Switching to Blocks requests
  `set_arrangement_mode {mode:"hold"}`; switching to Arrange requests
  `{mode:"run"}`. The selected view changes only after acknowledgement
- Blocks renders the server-published `block_launcher.blocks` inventory,
  preserves block ids and labels, disables entries whose `launchable` value is
  not true, and reflects authoritative active/requested state. Selecting an
  available block sends `launch_meso_block` with its `block_id` and includes
  `macro_index` only when exactly one occurrence index is published; it must
  never translate block launch into `locate_fraction`
- Blocks replaces BBT position with the authoritative `playback_session`
  elapsed clock. Play from Blocks includes `arrangement_mode: "hold"`, and
  pagination exposes at most eight blocks per page on the five-inch grid
- Encoder-first displays retain Previous/Next Section and Return to Start rather than offering fine continuous locate
- `TRANSPORT` must not start/stop JACK, restart the audio engine, or recreate ShadowScore arrangement/player controls
- `STARTUP` must invoke only the startup configuration controls published by Runner; Shadowbox must not maintain a competing startup-set preference
- `TRANSPOSE` must begin unconfigured on installations without saved authority; only explicit `LOCAL` authority may retain and fan out canonical device-local offsets
- `SHADOWSCORE` transpose authority must never fall back automatically to local authority after connectivity loss
- designated transpose MIDI input is a sidecar control path centered on MIDI note 60 and must not relay normal performance MIDI
- `NETWORK` may include a local `DIRECT ETHERNET SETUP` action that manages a fixed fallback address on `eth0` for headless recovery
- Direct Ethernet setup must be tightly scoped: touch only the configured Ethernet interface and only the configured fallback subnet
- A rejected secured-WiFi connection must return to password entry for the same network; retrying must update a profile created by the failed attempt instead of reusing its stale secret
- `HDMI` must appear only on the supported DSI build, change only the fixed mirror setting, and require a full reboot before the new setting takes effect
- `TOUCH FEEDBACK` belongs to the DSI `HDMI` screen, defaults to Off, applies immediately without changing release-to-activate touch semantics, and renders only transient control depression and release bloom on the shared DSI/HDMI framebuffer
- `REBOOT` must use a dedicated confirmation screen whose initial selection cancels the action
- `UPDATE` may check the checkout's configured upstream branch and run only a fast-forward update path; dirty or diverged local checkouts must not be applied from the unit UI

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
- In the color touch audio-device list, the reported current device additionally has a contrasting tinted row, solid accent bar, and check-mark `CURRENT` badge. The badge replaces that row's chevron, remains independent of cursor/press feedback, and does not imply JACK health. Other rows retain their existing navigation styling.
- The same `CURRENT` treatment applies to sample rate, buffer size, Load Set, and set/instance preset lists. It identifies the current setting or loaded identity, not whether subsequent edits have been saved; existing dirty-set italics and status remain separate.
- The color touch Wi-Fi list marks connected networks with `CONNECTED`; a remembered SSID without connected state must not receive this badge. This indicates network association, not internet access.
- Color touch audio/MIDI routing assignment and destination lists use `CONNECTED` badges, a quieter row tint, and outlined badges because several simultaneous connections are valid. These indicate published connections, not signal activity. Add/remove/disconnect actions and unconnected destinations retain their existing styling and behavior.
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
- create or manage its own set preset or instance preset system
- expose editing for unpublished backend capabilities
- expose raw instance `config` or `control` branches as generic menu sections
- support workflows requiring multiple simultaneous controls
- become a general RNBO administration panel

15. Open Questions

- Whether `REPLACE INSTANCE` should preserve routing automatically or rely on backend behavior
- Whether routing should support only single-target selection or multi-connection editing
- Whether aliases should be editable if published, or display-only

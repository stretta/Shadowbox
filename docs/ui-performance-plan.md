# Shadowbox UI Performance Plan

## Implementation status

The runtime portions of this plan are implemented:

- opt-in performance summaries through `SHADOWBOX_PERF_LOG`;
- background Runner and network coordination in `shadowbox/discovery.py`;
- dirty-state and mode-aware scheduling in `shadowbox/render_scheduler.py`;
- bounded/cached scope rendering and duplicate-frame suppression for the DSI
  framebuffer;
- automated performance, discovery, scope, touch, and framebuffer coverage;
- the `tools/sample_ui_performance.py` hardware measurement helper.

`SHADOWBOX_RENDER_SCHEDULER=legacy|dirty` remains available for rollout and
diagnostics, with `dirty` as the default. The hardware targets and soak steps
below remain a validation checklist rather than a claim about every supported
device. The remainder of this document preserves the original phased design
rationale, so its future-tense implementation language is historical.

## Purpose

This plan addresses the sustained CPU load and periodic responsiveness stalls observed on the 800x480 Waveshare DSI Shadowbox UI. The work should preserve live editor behavior while removing blocking discovery from the UI thread and avoiding unnecessary full-frame rendering.

The implementation should be delivered as narrow, independently reversible commits: measure first, separate discovery domains, add render invalidation, optimize live editors, and then validate on hardware.

## Original behavior and diagnosis

- `shadowbox/shadowbox.py` runs periodic discovery every three seconds.
- `RNBOClient.discover()` builds a full snapshot, and `discover_system()` calls `discover_host_network()`.
- Host-network discovery enumerates Wi-Fi networks through `tools/wifi_network.sh list`, even when the active screen only needs RNBO state.
- These discovery operations run synchronously on the main UI thread.
- The renderer clears, redraws, packs, and writes the complete framebuffer at a fixed cadence, even when the visible state has not changed.
- Live editors add drawing work. TimeDomainScope can render hundreds of waveform points on every frame.
- Scope editors pause periodic discovery, but Pitch Display and Step16 intentionally allow it so their live state remains current.
- The OSC listener already delivers live instance state and parameter updates, so those editors should not require a complete discovery pass for animation.

The live `wren` investigation showed approximately 44-56% CPU in the Shadowbox Python process on the affected editor screen, compared with approximately 37% after returning to the default UI. The journal also showed Wi-Fi list subprocesses at the three-second discovery cadence. System load, memory, temperature, and throttling were otherwise healthy.

## Performance goals

- No normal UI-thread operation should block for more than 50 ms.
- Touch-to-visible-response p95 should remain below 100 ms.
- Ordinary RNBO refresh must not execute `wifi_network.sh` or `nmcli`.
- Static screens should consume less than 10-15% of one CPU core after settling.
- Live editors should consume less than 30-35% of one CPU core while preserving useful visual update rates.
- Scope, Pitch Display, and Step16 must continue to show live state without cursor jumps or lost edits.
- Audio, JACK, and RNBO service behavior must remain unchanged.

## Phase 1: Add performance measurement

Add an opt-in performance probe before changing runtime behavior.

### Implementation

- Add `SHADOWBOX_PERF_LOG=1` for periodic summary metrics in the journal.
- Measure:
  - main-loop iteration latency;
  - input-to-render latency;
  - render duration;
  - framebuffer `show()` duration;
  - discovery duration by discovery type;
  - requested, coalesced, completed, failed, and stale discovery jobs;
  - frames rendered by UI mode.
- Emit summaries at a low rate rather than logging every frame.
- Add a tool under `tools/` that samples Shadowbox CPU from `/proc`, records load and temperature, and counts network-helper invocations in the journal.
- Record baselines for TOP, TimeDomainScope, Pitch Display, Step16, and Brick Panel.

### Tests

- Metrics remain disabled by default.
- Enabling metrics does not change scheduling behavior.
- Metric aggregation and reset behavior are deterministic under a fake clock.

### Commit boundary

`Add Shadowbox UI performance instrumentation`

## Phase 2: Separate discovery domains and remove blocking work

Replace the single all-purpose discovery operation with independent runner, live-state, and host-network paths.

### Discovery responsibilities

- `discover_runner()`:
  - OSCQuery tree;
  - instances and parameters;
  - patchers and lifecycle capabilities;
  - presets, sets, routing, audio configuration, and runner status.
- OSC listener:
  - live parameter values;
  - scope samples;
  - pitch/tuner values;
  - Step16 playhead and other published state.
- `discover_host_network()`:
  - host interfaces and addresses;
  - cached Wi-Fi connection state;
  - Wi-Fi list only when requested by a network screen;
  - active scan only after an explicit RESCAN action.

### Discovery coordinator

Add a background `DiscoveryCoordinator` owned by `shadowbox.py`.

- Accept typed requests such as `runner`, `network_status`, `wifi_list`, and `wifi_rescan`.
- Attach a reason and monotonically increasing generation to each request.
- Coalesce duplicate pending requests.
- Return results through `SimpleQueue`.
- Apply results to `ShadowboxUI` only on the main thread.
- Discard stale generations.
- Preserve the last good snapshot after an error.
- Surface failures as non-blocking status rather than freezing navigation.
- Allow only one active runner discovery and one active network operation at a time.

Replace synchronous `rnbo.discover()` calls in the interaction loop, including refreshes after preset, routing, instance, and audio actions. Startup discovery may remain synchronous during the first implementation because it already runs behind the startup screen; it can move to the coordinator once the normal path is stable.

### Network caching policy

- Lightweight interface/address status may refresh slowly in the background.
- Normal runner discovery never enumerates Wi-Fi networks.
- `NETWORK` displays the last cached network status and requests an asynchronous update.
- `WIFI_NETWORKS` displays the cached list immediately and requests a background cached-list refresh.
- RESCAN performs the only active Wi-Fi scan and reports progress asynchronously.

### Tests

- Runner discovery never calls host-network helpers.
- Slow discovery cannot delay input processing.
- Duplicate requests are coalesced.
- Stale results cannot overwrite newer UI state.
- Worker failures retain the last good state.
- Wi-Fi listing occurs only for network requests.
- RESCAN remains explicit and asynchronous.

### Commit boundary

`Move Shadowbox discovery off the UI thread`

## Phase 3: Add render invalidation and mode-aware scheduling

Replace unconditional fixed-rate full-frame rendering with dirty-state scheduling.

### Implementation

- Give the UI a render revision or `request_render(reason)` mechanism.
- Request a render after:
  - touch or encoder input;
  - an applied discovery result;
  - an OSC state or parameter update that affects the active screen;
  - status/busy changes;
  - dim, sleep, or wake transitions;
  - an animation tick for a screen that explicitly requires animation.
- Do not call `renderer.draw()` or `display.show()` while visible state is unchanged.
- Preserve immediate input handling independently of display cadence.
- Keep a maximum fallback refresh interval only for screens with time-based indicators.

### Initial mode policy

- Static menus: render only when dirty.
- TimeDomainScope: render when samples arrive, capped at 12-15 FPS.
- Pitch Display: render on pitch/cents OSC updates, capped at 15-20 FPS.
- Step16: render on playhead/state updates, capped at 15-20 FPS.
- Brick Panel: explicit animation cadence, initially capped at 30 FPS.
- Busy and status animations: 8-10 FPS.

Provide a temporary `SHADOWBOX_RENDER_SCHEDULER=legacy|dirty` switch for hardware rollout and rollback. Remove the legacy path after the new scheduler has been proved on supported displays.

### Tests

- Static screens do not render repeatedly without state changes.
- Input schedules an immediate render.
- Snapshot and OSC updates schedule one render.
- Burst updates are coalesced into the next allowed frame.
- Each animated mode respects its configured frame cap.
- Dim, sleep, wake, startup status, and software-update progress still render correctly.

### Commit boundary

`Render Shadowbox only when visible state changes`

## Phase 4: Optimize live editors and the DSI backend

Profile again after Phases 2 and 3. Implement only optimizations supported by the new measurements.

### TimeDomainScope

- Store samples in a bounded `deque`.
- Avoid copying and normalizing the full history on every render.
- Convert only the visible display-width sample window.
- Cache calculated pixel points until samples, bounds, sample rate, or layout change.
- Coalesce incoming samples and render the newest available state at the scope frame cap.
- Consider updating only the scope framebuffer rows if full-frame packing remains a significant cost.

### Pitch Display and Step16

- Confirm the OSC listener supplies every value needed for live display.
- Remove their dependency on periodic full runner discovery.
- Coalesce bursts of OSC messages into one render.
- Ensure live updates do not overwrite editor focus, cursor position, or unsaved parameter values.

### DSI framebuffer

- Track whether the canvas changed before calling `_pack_frame()`.
- Skip framebuffer writes for identical frames.
- Measure packing, conversion, and mmap write time independently.
- Add dirty-rectangle or dirty-row writes only if fewer frames and editor caching do not meet the CPU target.

### Tests

- Scope history remains bounded and reaches the full visible width.
- Cached scope points invalidate for every relevant input.
- Live editors display the newest coalesced state.
- Identical frames do not reach the framebuffer.
- RGB565 and 32-bit framebuffer formats remain correct.

### Commit boundary

`Reduce live editor and DSI rendering cost`

## Phase 5: Regression and hardware rollout

### Local verification

- Run the complete test suite.
- Run performance tests with fake display backends and a fake clock.
- Exercise all UI modes, startup recovery, software updates, network operations, preset actions, routing changes, dim, sleep, and wake.
- Compare results with the Phase 1 baseline.

### Hardware rollout

1. Deploy to a non-critical 5-inch DSI Shadowbox when one is available.
2. Exercise every editor for several minutes.
3. Verify touch responsiveness and visual update quality.
4. Confirm RNBO audio and JACK behavior are unchanged.
5. Deploy to `wren`.
6. Reproduce the original editor workflow.
7. Collect the same CPU, latency, frame, discovery, load, temperature, and restart metrics.
8. Confirm there are no periodic Wi-Fi helper calls outside network screens.
9. Confirm `shadowbox.service` remains active with no unexpected restarts.

### Rollback

- Keep each phase as a separate commit.
- Retain the async-discovery and render-scheduler compatibility switches during rollout.
- Revert the affected phase rather than modifying RNBO, JACK, or audio services.
- Remove compatibility switches only after the new behavior has been stable on multiple supported displays.

### Commit boundary

`Add Shadowbox UI performance regression coverage`

## Non-goals

- Optimizing `rnbooscquery` CPU or memory use.
- Changing RNBO patch DSP behavior.
- Changing JACK or audio device configuration.
- Generalizing Shadowbox into an arbitrary host-monitoring system.
- Implementing partial framebuffer updates before measurement shows they are necessary.

## Completion criteria

The package is complete when:

- all normal discovery and network operations are non-blocking;
- live editors receive current state without full periodic discovery;
- unchanged static screens do not redraw continuously;
- performance targets are met on the 800x480 DSI target;
- the original sluggish-editor workflow cannot reproduce a visible periodic pause;
- full local tests pass;
- a hardware soak completes without audio disruption, UI state corruption, or unexpected service restarts.

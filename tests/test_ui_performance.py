import time
import unittest
from types import SimpleNamespace

from shadowbox.discovery import DiscoveryCoordinator, DiscoveryResult
from shadowbox.performance import PerformanceProbe
from shadowbox.render_scheduler import RenderScheduler


class _Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


class _RNBO:
    def __init__(self):
        self.runner_calls = 0
        self.network_calls = 0
        self.wifi_calls = []

    def discover_runner(self):
        self.runner_calls += 1
        return {"runner": self.runner_calls}

    def discover_network_status(self):
        self.network_calls += 1
        return {"wifi_name": "wlan0"}

    def discover_wifi_networks(self, *, active_scan=False):
        self.wifi_calls.append(active_scan)
        return {"wifi_networks": []}


class PerformanceProbeTests(unittest.TestCase):
    def test_disabled_probe_is_empty(self):
        probe = PerformanceProbe(enabled=False, clock=_Clock())
        probe.observe("render", 0.1)
        probe.increment("frames")
        self.assertEqual(probe.snapshot(), {"timings": {}, "counts": {}})

    def test_aggregation_and_reset_are_deterministic(self):
        clock = _Clock()
        probe = PerformanceProbe(enabled=True, clock=clock)
        probe.observe("render", 0.010)
        probe.observe("render", 0.030)
        probe.increment("frames", 2)
        summary = probe.snapshot(reset=True)
        self.assertEqual(summary["timings"]["render"], {"count": 2, "avg_ms": 20.0, "max_ms": 30.0})
        self.assertEqual(summary["counts"]["frames"], 2)
        self.assertEqual(probe.snapshot(), {"timings": {}, "counts": {}})


class DiscoveryCoordinatorTests(unittest.TestCase):
    def test_typed_discovery_and_explicit_rescan(self):
        rnbo = _RNBO()
        coordinator = DiscoveryCoordinator(rnbo)
        coordinator.start()
        try:
            coordinator.request("runner", "test")
            coordinator.request("network_status", "test")
            coordinator.request("wifi_list", "test")
            coordinator.request("wifi_rescan", "test")
            deadline = time.monotonic() + 1.0
            results = []
            while len(results) < 4 and time.monotonic() < deadline:
                results.extend(coordinator.drain())
                time.sleep(0.005)
            self.assertEqual({item.kind for item in results}, {"runner", "network_status", "wifi_list", "wifi_rescan"})
            self.assertEqual(rnbo.runner_calls, 1)
            self.assertEqual(rnbo.wifi_calls, [False, True])
        finally:
            coordinator.stop()

    def test_stale_generation_is_detected(self):
        coordinator = DiscoveryCoordinator(_RNBO())
        coordinator.request("runner", "first")
        coordinator.request("runner", "second")
        self.assertTrue(coordinator.is_stale(DiscoveryResult("runner", "first", 1)))


class RenderSchedulerTests(unittest.TestCase):
    def test_static_screen_renders_only_when_dirty(self):
        clock = _Clock()
        scheduler = RenderScheduler(clock=clock)
        ui = SimpleNamespace(state=SimpleNamespace(ui_mode="TOP", busy=False, status_message=""), selected_param=None)
        self.assertTrue(scheduler.should_render(ui))
        scheduler.rendered()
        clock.now += 10
        self.assertFalse(scheduler.should_render(ui))
        scheduler.request("input", input_event=True)
        self.assertTrue(scheduler.should_render(ui))

    def test_brick_panel_is_capped_at_30_fps(self):
        clock = _Clock()
        scheduler = RenderScheduler(clock=clock)
        ui = SimpleNamespace(state=SimpleNamespace(ui_mode="BRICK_PANEL", busy=False, status_message=""), selected_param=None)
        scheduler.rendered()
        scheduler.request("animation")
        clock.now = 0.01
        self.assertFalse(scheduler.should_render(ui))
        clock.now = 1 / 30
        self.assertTrue(scheduler.should_render(ui))

    def test_input_bypasses_busy_animation_cap(self):
        clock = _Clock()
        scheduler = RenderScheduler(clock=clock)
        ui = SimpleNamespace(state=SimpleNamespace(ui_mode="TOP", busy=True, status_message="working"), selected_param=None)
        scheduler.rendered(now=0.0, animation_advanced=True)
        clock.now = 0.01
        scheduler.request("input", input_event=True)
        self.assertTrue(scheduler.should_render(ui))
        scheduler.rendered()

        clock.now = 0.02
        scheduler.request("input", input_event=True)
        self.assertTrue(scheduler.should_render(ui))
        self.assertFalse(scheduler.animation_due(ui))

    def test_input_frame_does_not_advance_animation_clock(self):
        clock = _Clock()
        scheduler = RenderScheduler(clock=clock)
        ui = SimpleNamespace(state=SimpleNamespace(ui_mode="TOP", busy=True, status_message="working"), selected_param=None)
        scheduler.rendered(now=0.0, animation_advanced=True)
        clock.now = 0.01
        scheduler.request("input", input_event=True)
        scheduler.rendered(animation_advanced=False)
        self.assertEqual(scheduler.last_animation, 0.0)

    def test_sustained_input_is_event_driven(self):
        clock = _Clock()
        scheduler = RenderScheduler(clock=clock)
        ui = SimpleNamespace(state=SimpleNamespace(ui_mode="TOP", busy=False, status_message=""), selected_param=None)
        clock.now = 0.01
        scheduler.request("input", input_event=True)
        self.assertTrue(scheduler.should_render(ui))

    def test_input_latency_uses_presentation_time(self):
        clock = _Clock()
        scheduler = RenderScheduler(clock=clock)
        clock.now = 1.0
        scheduler.request("input", input_event=True)
        clock.now = 1.075

        self.assertAlmostEqual(scheduler.rendered(), 0.075)


if __name__ == "__main__":
    unittest.main()

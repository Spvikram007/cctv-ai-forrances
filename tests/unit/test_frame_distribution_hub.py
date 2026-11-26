"""
Comprehensive Unit Tests for Shared Frame Distribution Hub (Milestone W4.2).
Validates all 12 Required Architecture Scenarios:
1. Multiple subscribers viewing the same camera (verify 1 upstream worker).
2. Multiple cameras with independent distribution.
3. Verify one upstream RTSP worker per camera.
4. Slow subscriber and queue overflow (drop-oldest eviction).
5. Subscriber disconnect and reconnect.
6. Last subscriber disconnect and idle cleanup.
7. New subscriber arriving during the idle grace period (aborting timer).
8. Concurrent subscription and cancellation across threads.
9. Camera RTSP failure and recovery (StreamManager disconnect signal).
10. Recording and AI consumers continue receiving frames via StreamManager callbacks.
11. Desktop PySide6 consumers remain functional.
12. Shutdown without leaked threads or blocked workers (hub.stop_all()).
"""

import time
import threading
import pytest
import numpy as np

from web.gateway.hub import FrameDistributionHub, ClientSubscription
from engines.video_engine.stream_manager import stream_manager


def test_client_subscription_unit_behaviors():
    """Unit validation of ClientSubscription bounded queue and drop-oldest eviction."""
    sub = ClientSubscription(channel_id="test_unit_ch", client_id="unit_client_1", max_queue_size=3)
    assert sub.is_active is True
    assert sub.channel_id == "test_unit_ch"
    assert sub.client_id == "unit_client_1"

    f1 = np.zeros((10, 10, 3), dtype=np.uint8)
    f2 = np.ones((10, 10, 3), dtype=np.uint8)
    f3 = np.ones((10, 10, 3), dtype=np.uint8) * 2
    f4 = np.ones((10, 10, 3), dtype=np.uint8) * 3

    assert sub.push_frame(f1, 10.0) is True
    assert sub.push_frame(f2, 20.0) is True
    assert sub.push_frame(f3, 30.0) is True
    assert sub.total_frames_dropped == 0
    assert sub.total_frames_delivered == 3

    # 4th push triggers drop-oldest (f1 evicted)
    assert sub.push_frame(f4, 40.0) is False
    assert sub.total_frames_dropped == 1
    assert sub.total_frames_delivered == 4

    # Non-blocking pop latest
    latest = sub.get_latest_frame_nowait()
    assert latest is not None
    assert np.array_equal(latest[0], f4)
    assert latest[1] == 40.0

    # Queue is now empty after get_latest_frame_nowait
    assert sub.get_latest_frame_nowait() is None
    assert sub.get_frame(timeout=0.05) is None

    # Close subscription
    sub.close()
    assert not sub.is_active
    assert sub.push_frame(f1, 50.0) is False
    assert sub.get_frame(timeout=0.05) is None


# SCENARIO 1: Multiple subscribers viewing the same camera (verify 1 upstream worker)
def test_scenario_01_multiple_subscribers_single_camera():
    hub = FrameDistributionHub(default_grace_period_sec=0.5)
    channel_id = "test_scen1_ch"

    try:
        sub1 = hub.subscribe(channel_id, client_id="client_scen1_A")
        sub2 = hub.subscribe(channel_id, client_id="client_scen1_B")
        sub3 = hub.subscribe(channel_id, client_id="client_scen1_C")

        # Verify exactly ONE upstream worker in StreamManager
        with stream_manager._lock:
            workers = [w for w in stream_manager._workers if w == channel_id]
            assert len(workers) == 1, f"Expected exactly 1 worker for channel {channel_id}, got {len(workers)}"

        # Verify all 3 subscribers receive broadcast frames
        f1 = sub1.get_frame(timeout=2.0)
        f2 = sub2.get_frame(timeout=2.0)
        f3 = sub3.get_frame(timeout=2.0)

        assert f1 is not None and isinstance(f1[0], np.ndarray)
        assert f2 is not None and isinstance(f2[0], np.ndarray)
        assert f3 is not None and isinstance(f3[0], np.ndarray)

        stats = hub.get_channel_stats(channel_id)
        assert stats is not None
        assert stats["active_subscribers"] == 3
        assert stats["total_frames_broadcast"] > 0
    finally:
        hub.stop_all()
        stream_manager.stop_stream(channel_id)


# SCENARIO 2: Multiple cameras with independent distribution
def test_scenario_02_multiple_cameras_independent_distribution():
    hub = FrameDistributionHub(default_grace_period_sec=0.5)
    cam_alpha = "test_scen2_alpha"
    cam_beta = "test_scen2_beta"

    try:
        sub_alpha = hub.subscribe(cam_alpha, client_id="sub_alpha_1")
        sub_beta = hub.subscribe(cam_beta, client_id="sub_beta_1")

        # Wait for both streams to produce frames
        f_alpha = sub_alpha.get_frame(timeout=2.0)
        f_beta = sub_beta.get_frame(timeout=2.0)

        assert f_alpha is not None
        assert f_beta is not None

        stats_alpha = hub.get_channel_stats(cam_alpha)
        stats_beta = hub.get_channel_stats(cam_beta)
        assert stats_alpha is not None
        assert stats_beta is not None
        if stats_alpha and stats_beta:
            assert stats_alpha["channel_id"] == cam_alpha
            assert stats_beta["channel_id"] == cam_beta
            assert stats_alpha["active_subscribers"] == 1
            assert stats_beta["active_subscribers"] == 1

        all_stats = hub.get_all_stats()
        assert all_stats["active_channels"] == 2
    finally:
        hub.stop_all()
        stream_manager.stop_stream(cam_alpha)
        stream_manager.stop_stream(cam_beta)


# SCENARIO 3: Verify one upstream RTSP worker per camera
def test_scenario_03_verify_one_upstream_worker_per_camera():
    hub = FrameDistributionHub(default_grace_period_sec=0.5)
    cam_x = "test_scen3_camX"
    cam_y = "test_scen3_camY"

    try:
        # Cam X: 3 subscribers
        sx1 = hub.subscribe(cam_x, client_id="cx_1")
        sx2 = hub.subscribe(cam_x, client_id="cx_2")
        sx3 = hub.subscribe(cam_x, client_id="cx_3")

        # Cam Y: 2 subscribers
        sy1 = hub.subscribe(cam_y, client_id="cy_1")
        sy2 = hub.subscribe(cam_y, client_id="cy_2")

        with stream_manager._lock:
            x_workers = [w for w in stream_manager._workers if w == cam_x]
            y_workers = [w for w in stream_manager._workers if w == cam_y]
            assert len(x_workers) == 1, "Cam X must have exactly 1 worker"
            assert len(y_workers) == 1, "Cam Y must have exactly 1 worker"

        # Drain at least one frame from each to confirm data flow
        assert sx1.get_frame(timeout=2.0) is not None
        assert sy1.get_frame(timeout=2.0) is not None
    finally:
        hub.stop_all()
        stream_manager.stop_stream(cam_x)
        stream_manager.stop_stream(cam_y)


# SCENARIO 4: Slow subscriber and queue overflow (drop-oldest eviction)
def test_scenario_04_slow_subscriber_and_queue_overflow():
    hub = FrameDistributionHub(default_grace_period_sec=0.5)
    channel_id = "test_scen4_slow_fast"

    try:
        fast_client = hub.subscribe(channel_id, client_id="fast_client_scen4", max_queue_size=15)
        slow_client = hub.subscribe(channel_id, client_id="slow_client_scen4", max_queue_size=2)

        # Allow worker to produce frames for ~0.3s (approx 7-8 frames at 25 fps)
        time.sleep(0.35)

        # Slow client has not read: queue should be at max capacity 2, dropped frames > 0
        assert len(slow_client._queue) <= 2
        assert slow_client.total_frames_dropped > 0, "Slow client should have dropped frames"

        # Fast client reads without delay: should have received new frames and 0 drops
        frame = fast_client.get_frame(timeout=1.0)
        assert frame is not None
        assert fast_client.total_frames_dropped == 0

        # Slow client now reads: gets latest frame without crashing or deadlock
        slow_frame = slow_client.get_frame(timeout=1.0)
        assert slow_frame is not None
    finally:
        hub.stop_all()
        stream_manager.stop_stream(channel_id)


# SCENARIO 5: Subscriber disconnect and reconnect
def test_scenario_05_subscriber_disconnect_and_reconnect():
    hub = FrameDistributionHub(default_grace_period_sec=2.0)
    channel_id = "test_scen5_recon"

    try:
        sub_initial = hub.subscribe(channel_id, client_id="client_recon_1")
        f1 = sub_initial.get_frame(timeout=2.0)
        assert f1 is not None

        # Disconnect client
        hub.unsubscribe(channel_id, "client_recon_1")
        assert not sub_initial.is_active

        # Reconnect with a new client id within grace period
        sub_reconnected = hub.subscribe(channel_id, client_id="client_recon_2")
        assert sub_reconnected.is_active is True

        f2 = sub_reconnected.get_frame(timeout=2.0)
        assert f2 is not None
        assert isinstance(f2[0], np.ndarray)

        # Worker remained the same active worker
        with stream_manager._lock:
            assert channel_id in stream_manager._workers
    finally:
        hub.stop_all()
        stream_manager.stop_stream(channel_id)


# SCENARIO 6: Last subscriber disconnect and 30s idle cleanup (tested with short grace)
def test_scenario_06_last_subscriber_disconnect_idle_cleanup():
    # Use 0.4s grace period for rapid deterministic test
    hub = FrameDistributionHub(default_grace_period_sec=0.4)
    channel_id = "test_scen6_idle"

    try:
        sub = hub.subscribe(channel_id, client_id="temp_client")
        assert sub.get_frame(timeout=2.0) is not None

        with stream_manager._lock:
            assert channel_id in stream_manager._workers

        # Disconnect last subscriber
        hub.unsubscribe(channel_id, "temp_client")

        # Immediately after unsubscribe, grace timer is running, worker still alive
        with stream_manager._lock:
            assert channel_id in stream_manager._workers

        # Wait for grace period to expire (0.4s + margin = 0.6s)
        time.sleep(0.65)

        # Worker should now be stopped and cleaned up from StreamManager
        with stream_manager._lock:
            worker = stream_manager._workers.get(channel_id)
            assert worker is None, "Upstream worker should be stopped after idle grace period."
    finally:
        hub.stop_all()
        stream_manager.stop_stream(channel_id)


# SCENARIO 7: New subscriber arriving during the idle grace period (aborting timer)
def test_scenario_07_new_subscriber_during_grace_period_cancels_timer():
    # Grace period 0.8s
    hub = FrameDistributionHub(default_grace_period_sec=0.8)
    channel_id = "test_scen7_abort_timer"

    try:
        sub1 = hub.subscribe(channel_id, client_id="client_first")
        assert sub1.get_frame(timeout=2.0) is not None

        # Disconnect client 1
        hub.unsubscribe(channel_id, "client_first")

        # Wait 0.2s (timer is active, remaining ~0.6s)
        time.sleep(0.2)

        # Client 2 arrives before timer expires: should cancel idle shutdown
        sub2 = hub.subscribe(channel_id, client_id="client_second")
        assert sub2.get_frame(timeout=2.0) is not None

        # Wait past original 0.8s deadline (e.g., 0.9s from disconnect)
        time.sleep(0.7)

        # Upstream worker must STILL be running because timer was aborted
        with stream_manager._lock:
            worker = stream_manager._workers.get(channel_id)
            assert worker is not None, "Worker should not have stopped; grace timer should have been aborted."
            assert worker.is_alive()
    finally:
        hub.stop_all()
        stream_manager.stop_stream(channel_id)


# SCENARIO 8: Concurrent subscription and cancellation across threads
def test_scenario_08_concurrent_subscriptions_and_cancellations():
    hub = FrameDistributionHub(default_grace_period_sec=1.0)
    channel_id = "test_scen8_concurrency"
    errors = []

    def worker_action(thread_idx: int):
        try:
            cid = f"thread_client_{thread_idx}"
            sub = hub.subscribe(channel_id, client_id=cid, max_queue_size=5)
            # Fetch a few frames
            frames_got = 0
            for _ in range(5):
                f = sub.get_frame(timeout=0.5)
                if f is not None:
                    frames_got += 1
                time.sleep(0.01)
            hub.unsubscribe(channel_id, cid)
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=worker_action, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10.0)

    assert len(errors) == 0, f"Thread concurrency errors encountered: {errors}"
    hub.stop_all()
    stream_manager.stop_stream(channel_id)


# SCENARIO 9: Camera RTSP failure and recovery (StreamManager disconnect signal)
def test_scenario_09_camera_stream_failure_and_recovery():
    hub = FrameDistributionHub(default_grace_period_sec=1.0)
    channel_id = "test_scen9_failure"

    try:
        sub = hub.subscribe(channel_id, client_id="client_fail_test")
        f = sub.get_frame(timeout=2.0)
        assert f is not None

        # Simulate camera stream failure / external worker termination
        stream_manager.stop_stream(channel_id)

        # Subscriber attempts to read: gracefully returns None on timeout, does not crash
        no_frame = sub.get_frame(timeout=0.1)
        # May get residual or None
        assert no_frame is None or isinstance(no_frame[0], np.ndarray)

        # Recovery: re-ensuring upstream restarts worker smoothly
        dist = hub._distributors.get(channel_id)
        assert dist is not None
        restarted = dist.ensure_upstream_running()
        assert restarted is True

        new_frame = sub.get_frame(timeout=2.0)
        assert new_frame is not None
    finally:
        hub.stop_all()
        stream_manager.stop_stream(channel_id)


# SCENARIO 10: Recording and AI consumers continue receiving frames via StreamManager callbacks
def test_scenario_10_recording_and_ai_consumers_coexist():
    hub = FrameDistributionHub(default_grace_period_sec=0.5)
    channel_id = "test_scen10_ai_rec"

    ai_frames_received = []
    rec_frames_received = []

    def ai_inference_callback(ch_id: str, frame: np.ndarray, ts: float):
        ai_frames_received.append((ch_id, ts))

    def recording_callback(ch_id: str, frame: np.ndarray, ts: float):
        rec_frames_received.append((ch_id, ts))

    try:
        # Start stream with recording callback
        stream_manager.start_stream(
            channel_id=channel_id,
            rtsp_url=f"test://simulated_{channel_id}",
            frame_callback=recording_callback,
            is_test_stream=True,
        )

        # Register AI inference callback
        stream_manager.register_frame_callback(channel_id, ai_inference_callback)

        # Now attach web hub subscriber to the same stream
        web_sub = hub.subscribe(channel_id, client_id="web_viewer_1")

        # Allow frames to distribute to all 3 consumers
        time.sleep(0.3)

        web_frame = web_sub.get_frame(timeout=1.0)
        assert web_frame is not None, "Web subscriber should receive frames"
        assert len(ai_frames_received) > 0, "AI callback should receive frames concurrently"
        assert len(rec_frames_received) > 0, "Recording callback should receive frames concurrently"

        # Unsubscribing web client leaves recording and AI untouched
        hub.unsubscribe(channel_id, "web_viewer_1")
        initial_ai_count = len(ai_frames_received)
        time.sleep(0.15)
        assert len(ai_frames_received) > initial_ai_count, "AI callback should continue running after web client disconnects"
    finally:
        hub.stop_all()
        stream_manager.stop_stream(channel_id)


# SCENARIO 11: Desktop PySide6 consumers remain functional
def test_scenario_11_desktop_pyside6_consumer_lifecycle_protection():
    """
    Validates that when desktop starts a stream first:
    1. Hub connects to existing worker without replacing it.
    2. When web clients disconnect, hub does NOT stop the upstream worker.
    """
    hub = FrameDistributionHub(default_grace_period_sec=0.2)
    channel_id = "test_scen11_desktop_protect"

    try:
        # Desktop initiates stream (e.g. user opens LiveView in PySide6)
        desktop_worker = stream_manager.start_stream(
            channel_id=channel_id,
            rtsp_url=f"test://simulated_{channel_id}",
            is_test_stream=True,
        )
        assert desktop_worker.is_alive()

        # Web browser user opens same camera
        web_sub = hub.subscribe(channel_id, client_id="browser_user_1")
        web_frame = web_sub.get_frame(timeout=2.0)
        assert web_frame is not None

        # Desktop directly fetches frame from StreamManager buffer
        desktop_frame = stream_manager.get_latest_frame(channel_id)
        assert desktop_frame is not None

        # Web browser user closes tab
        hub.unsubscribe(channel_id, "browser_user_1")

        # Wait past grace period
        time.sleep(0.4)

        # CRITICAL ASSERTION: The stream was NOT started by hub, so hub must NOT stop it!
        with stream_manager._lock:
            worker = stream_manager._workers.get(channel_id)
            assert worker is not None, "Desktop stream worker must NOT be killed by hub idle shutdown!"
            assert worker.is_alive()

        # Desktop continues to receive frames
        latest_desktop = stream_manager.get_latest_frame(channel_id)
        assert latest_desktop is not None
    finally:
        hub.stop_all()
        stream_manager.stop_stream(channel_id)


# SCENARIO 12: Shutdown without leaked threads or blocked workers (hub.stop_all())
def test_scenario_12_shutdown_without_leaked_threads():
    hub = FrameDistributionHub(default_grace_period_sec=5.0)
    ch1 = "test_scen12_ch1"
    ch2 = "test_scen12_ch2"

    try:
        sub1 = hub.subscribe(ch1, client_id="sub_1")
        sub2 = hub.subscribe(ch1, client_id="sub_2")
        sub3 = hub.subscribe(ch2, client_id="sub_3")

        # Verify all active
        assert sub1.is_active is True
        assert sub2.is_active is True
        assert sub3.is_active is True

        # Perform global shutdown
        hub.stop_all()

        # Verify all subscriptions marked inactive
        assert not sub1.is_active
        assert not sub2.is_active
        assert not sub3.is_active
        assert len(hub._distributors) == 0

        # Subscriptions should cleanly unblock without hanging
        assert sub1.get_frame(timeout=0.05) is None
        assert sub2.get_frame(timeout=0.05) is None
        assert sub3.get_frame(timeout=0.05) is None
    finally:
        stream_manager.stop_stream(ch1)
        stream_manager.stop_stream(ch2)


# SCENARIO 13: Adversarial immutability & cross-subscriber isolation
def test_scenario_13_shared_frame_immutability_protection():
    """
    Adversarial immutability tests:
    1. Verifies that distributed frames are C-level immutable read-only buffers.
    2. Verifies that flags.writeable cannot be restored on the frame or its base.
    3. Verifies that .base and .base.base cannot be mutated.
    4. Verifies that two subscribers receiving the same frame cannot affect each other.
    5. Verifies that explicit copy() allows safe local mutation without corrupting shared buffer.
    """
    hub = FrameDistributionHub(default_grace_period_sec=0.5)
    channel_id = "test_scen13_immutability"

    try:
        sub_a = hub.subscribe(channel_id, client_id="sub_a")
        sub_b = hub.subscribe(channel_id, client_id="sub_b")

        fa_tuple = sub_a.get_frame(timeout=2.0)
        fb_tuple = sub_b.get_frame(timeout=2.0)
        assert fa_tuple is not None and fb_tuple is not None
        fa, tsa = fa_tuple
        fb, tsb = fb_tuple

        # 1. Direct writeable flag is False
        assert fa.flags.writeable is False
        assert fb.flags.writeable is False

        # 2. Adversarial attempt to force writeable = True on the frame
        with pytest.raises(ValueError, match="cannot set WRITEABLE flag to True"):
            fa.flags.writeable = True

        # 3. Direct mutation attempt
        with pytest.raises(ValueError, match="assignment destination is read-only"):
            fa[0, 0] = [255, 0, 0]

        # 4. Adversarial attempt to mutate via .base
        if hasattr(fa, "base") and fa.base is not None:
            with pytest.raises((ValueError, TypeError)):
                fa.base[0] = 255

            with pytest.raises(ValueError, match="cannot set WRITEABLE flag to True"):
                fa.base.flags.writeable = True

        # 5. Adversarial attempt to mutate via .base.base (underlying memoryview)
        if hasattr(fa, "base") and hasattr(fa.base, "base") and fa.base.base is not None:
            with pytest.raises(TypeError, match="cannot modify read-only memory"):
                fa.base.base[0] = 255

        # 6. Verify cross-subscriber data integrity: Sub B's frame is completely untouched
        original_pixel = fb[0, 0].copy()
        assert np.array_equal(fa[0, 0], original_pixel)

        # 7. Safe boundary copy: consumer needing writable frame makes explicit copy
        writable_copy = fa.copy()
        assert writable_copy.flags.writeable is True
        writable_copy[0, 0] = [123, 45, 67]
        # Shared frame fa and fb remain pristine
        assert not np.array_equal(fa[0, 0], [123, 45, 67])
        assert not np.array_equal(fb[0, 0], [123, 45, 67])
    finally:
        hub.stop_all()
        stream_manager.stop_stream(channel_id)


# SCENARIO 14: Bidirectional stream ownership (Order B: Hub starts -> Desktop attaches -> Hub leaves -> Desktop continues)
def test_scenario_14_bidirectional_stream_ownership_hub_first():
    """
    Validates Order B:
    1. Web hub starts the upstream stream worker.
    2. Desktop consumer attaches interest (add_consumer).
    3. Web client disconnects and hub grace period elapses.
    4. Upstream worker MUST NOT be stopped; desktop continues monitoring.
    5. Stream halts only after desktop releases interest.
    """
    hub = FrameDistributionHub(default_grace_period_sec=0.2)
    channel_id = "test_scen14_hub_first"

    try:
        # Step 1: Web client subscribes (starts upstream worker)
        web_sub = hub.subscribe(channel_id, client_id="web_client_lead")
        assert web_sub.get_frame(timeout=2.0) is not None

        with stream_manager._lock:
            worker = stream_manager._workers.get(channel_id)
            assert worker is not None and worker.is_alive()

        # Step 2: Desktop attaches to the active stream
        stream_manager.add_consumer(channel_id, "desktop_live_view")
        assert "desktop_live_view" in stream_manager.get_stream_consumers(channel_id)

        # Step 3: Web client disconnects
        hub.unsubscribe(channel_id, "web_client_lead")

        # Wait past hub idle grace period (0.2s + 0.3s margin)
        time.sleep(0.5)

        # Step 4: Stream worker MUST remain alive because desktop is still attached!
        with stream_manager._lock:
            worker = stream_manager._workers.get(channel_id)
            assert worker is not None, "Stream worker must NOT be stopped while desktop consumer is active!"
            assert worker.is_alive()

        # Desktop can continuously fetch newest frames
        frame = stream_manager.get_latest_frame(channel_id)
        assert frame is not None

        # Step 5: Desktop finishes and detaches
        stream_manager.remove_consumer(channel_id, "desktop_live_view")
        assert stream_manager.is_stream_in_use(channel_id, check_recent_poll=False) is False
        stream_manager.stop_stream(channel_id)

        with stream_manager._lock:
            assert channel_id not in stream_manager._workers
    finally:
        hub.stop_all()
        stream_manager.stop_stream(channel_id)


# SCENARIO 15: Recording attaches to a hub-owned stream
def test_scenario_15_recording_attaches_to_hub_owned_stream():
    """
    Validates that when recording attaches a callback to a hub-owned stream,
    the hub will not terminate the worker when web clients disconnect.
    """
    hub = FrameDistributionHub(default_grace_period_sec=0.2)
    channel_id = "test_scen15_rec_attach"
    rec_frames = []

    def recording_frame_sink(ch: str, frame: np.ndarray, ts: float):
        rec_frames.append(ts)

    try:
        # Web starts stream
        web_sub = hub.subscribe(channel_id, client_id="web_viewer")
        assert web_sub.get_frame(timeout=2.0) is not None

        # Recording attaches native callback
        stream_manager.register_frame_callback(channel_id, recording_frame_sink)

        # Web disconnects
        hub.unsubscribe(channel_id, "web_viewer")
        time.sleep(0.5)

        # Stream worker MUST be alive because recording callback is registered!
        with stream_manager._lock:
            worker = stream_manager._workers.get(channel_id)
            assert worker is not None and worker.is_alive()

        initial_count = len(rec_frames)
        time.sleep(0.15)
        assert len(rec_frames) > initial_count, "Recording must continue receiving frames"

        # Detach recording callback
        stream_manager.unregister_frame_callback(channel_id, recording_frame_sink)
    finally:
        hub.stop_all()
        stream_manager.stop_stream(channel_id)


# SCENARIO 16: AI analytics attaches to a hub-owned stream
def test_scenario_16_ai_analytics_attaches_to_hub_owned_stream():
    """
    Validates that when AI analytics attaches to a hub-owned stream,
    disconnecting web clients does not disrupt ongoing AI inference.
    """
    hub = FrameDistributionHub(default_grace_period_sec=0.2)
    channel_id = "test_scen16_ai_attach"
    ai_inferences = []

    def ai_inference_sink(ch: str, frame: np.ndarray, ts: float):
        ai_inferences.append(ts)

    try:
        web_sub = hub.subscribe(channel_id, client_id="web_viewer")
        assert web_sub.get_frame(timeout=2.0) is not None

        # AI analytics registers callback
        stream_manager.register_frame_callback(channel_id, ai_inference_sink)

        # Web disconnects
        hub.unsubscribe(channel_id, "web_viewer")
        time.sleep(0.5)

        with stream_manager._lock:
            worker = stream_manager._workers.get(channel_id)
            assert worker is not None and worker.is_alive()

        initial_ai = len(ai_inferences)
        time.sleep(0.15)
        assert len(ai_inferences) > initial_ai, "AI analytics must continue receiving frames"

        stream_manager.unregister_frame_callback(channel_id, ai_inference_sink)
    finally:
        hub.stop_all()
        stream_manager.stop_stream(channel_id)


# SCENARIO 17: Multiple native consumers coexist and detach independently
def test_scenario_17_multiple_native_consumers_coexist_and_detach_independently():
    """
    Validates multiple native consumers (Desktop, Recording, AI) coexisting with Web.
    Each consumer detaches independently; stream remains alive until the last consumer leaves.
    """
    hub = FrameDistributionHub(default_grace_period_sec=0.2)
    channel_id = "test_scen17_multi_native"

    rec_frames = []
    ai_frames = []

    def rec_cb(ch, f, ts):
        rec_frames.append(ts)

    def ai_cb(ch, f, ts):
        ai_frames.append(ts)

    try:
        # Web starts stream
        web_sub = hub.subscribe(channel_id, client_id="web_user")
        assert web_sub.get_frame(timeout=2.0) is not None

        # Desktop, Recording, and AI all attach
        stream_manager.add_consumer(channel_id, "desktop_wall")
        stream_manager.register_frame_callback(channel_id, rec_cb)
        stream_manager.register_frame_callback(channel_id, ai_cb)

        # 1. Web disconnects: stream must survive (3 native consumers active)
        hub.unsubscribe(channel_id, "web_user")
        time.sleep(0.4)
        assert stream_manager.is_stream_in_use(channel_id) is True

        # 2. Recording detaches: stream must survive (Desktop and AI active)
        stream_manager.unregister_frame_callback(channel_id, rec_cb)
        assert stream_manager.is_stream_in_use(channel_id) is True

        # 3. AI detaches: stream must survive (Desktop active)
        stream_manager.unregister_frame_callback(channel_id, ai_cb)
        assert stream_manager.is_stream_in_use(channel_id) is True

        # 4. Desktop detaches: now in_use becomes False
        stream_manager.remove_consumer(channel_id, "desktop_wall")
        assert stream_manager.is_stream_in_use(channel_id) is False

        # Clean termination
        stream_manager.stop_stream(channel_id)
        with stream_manager._lock:
            assert channel_id not in stream_manager._workers
    finally:
        hub.stop_all()
        stream_manager.stop_stream(channel_id)


# SCENARIO 18: Real production RecordingManager integration & lifecycle
def test_scenario_18_production_recording_manager_integration(tmp_path):
    """
    Validates integration with real production RecordingManager:
    1. Web client initiates stream.
    2. recording_manager.start_recording() attaches to the active stream.
    3. Web client disconnects and hub idle grace period elapses.
    4. Stream remains active because recorder is registered in StreamManager.
    5. recording_manager.stop_recording() finalizes recording and releases ownership.
    6. Stream is then stopped cleanly once all consumers have released.
    """
    from engines.recording_engine.recording_manager import recording_manager

    hub = FrameDistributionHub(default_grace_period_sec=0.2)
    channel_id = "test_scen18_prod_rec"
    output_dir = str(tmp_path / "rec_output")

    try:
        # Step 1: Web client starts stream
        web_sub = hub.subscribe(channel_id, client_id="web_rec_watcher")
        assert web_sub.get_frame(timeout=2.0) is not None

        # Step 2: Real RecordingManager starts recording
        rec_worker = recording_manager.start_recording(
            channel_id=channel_id,
            channel_name="Test Prod Camera",
            recording_type="CONTINUOUS",
            segment_duration_sec=10,
            output_dir=output_dir,
        )
        assert rec_worker.is_alive()
        assert f"recorder_{channel_id}" in stream_manager.get_stream_consumers(channel_id)

        # Step 3: Web client disconnects
        hub.unsubscribe(channel_id, "web_rec_watcher")

        # Wait past grace period
        time.sleep(0.5)

        # Step 4: Stream worker MUST remain alive because RecordingManager is actively recording!
        with stream_manager._lock:
            worker = stream_manager._workers.get(channel_id)
            assert worker is not None, "Stream worker must NOT be killed while RecordingManager is active!"
            assert worker.is_alive()

        # Step 5: RecordingManager stops recording
        recording_manager.stop_recording(channel_id)
        assert f"recorder_{channel_id}" not in stream_manager.get_stream_consumers(channel_id)

        # Step 6: Now that all consumers left, stream can be stopped cleanly
        stopped = stream_manager.stop_stream_if_idle(channel_id)
        assert stopped is True
        with stream_manager._lock:
            assert channel_id not in stream_manager._workers
    finally:
        hub.stop_all()
        recording_manager.stop_all()
        stream_manager.stop_stream(channel_id)


# SCENARIO 19: Direct get_latest_frame polling keeps stream alive
def test_scenario_19_direct_get_latest_frame_polling_keeps_stream_alive():
    """
    Validates that a native consumer polling get_latest_frame() directly
    (without an explicit registration tag) updates the fetch heartbeat and
    prevents stop_stream_if_idle() from terminating the active stream.
    """
    hub = FrameDistributionHub(default_grace_period_sec=0.2)
    channel_id = "test_scen19_direct_poll"

    try:
        # Web starts stream
        web_sub = hub.subscribe(channel_id, client_id="web_poll_watcher")
        assert web_sub.get_frame(timeout=2.0) is not None

        # Desktop polls get_latest_frame directly
        f_data = stream_manager.get_latest_frame(channel_id)
        assert f_data is not None

        # Web disconnects
        hub.unsubscribe(channel_id, "web_poll_watcher")

        # Desktop continues periodic polling (e.g., 30 FPS timer)
        time.sleep(0.1)
        f_data2 = stream_manager.get_latest_frame(channel_id)
        assert f_data2 is not None

        # Grace period elapses: Hub attempts _stop_upstream()
        time.sleep(0.3)

        # Stream worker MUST NOT be stopped because a frame fetch occurred within 3.0s!
        with stream_manager._lock:
            worker = stream_manager._workers.get(channel_id)
            assert worker is not None, "Stream worker must remain alive while actively polled by get_latest_frame!"
            assert worker.is_alive()

        # Now simulate desktop stopping all polling: wait > 3.0s
        time.sleep(3.2)

        # Now stop_stream_if_idle confirms no recent polls and cleanly stops
        stopped = stream_manager.stop_stream_if_idle(channel_id)
        assert stopped is True
        with stream_manager._lock:
            assert channel_id not in stream_manager._workers
    finally:
        hub.stop_all()
        stream_manager.stop_stream(channel_id)


# SCENARIO 20: Deterministic race-condition test: consumer attaches during idle cleanup
def test_scenario_20_deterministic_race_condition_attach_during_idle_cleanup():
    """
    Deterministic race-condition test for TOCTOU:
    Simulates high-contention concurrent threads where one thread calls
    stop_stream_if_idle() and another thread calls add_consumer().
    Because stop_stream_if_idle executes atomically under StreamManager._lock,
    no state corruption, deadlock, or erroneous stream teardown occurs.
    """
    hub = FrameDistributionHub(default_grace_period_sec=0.1)
    channel_id = "test_scen20_race"

    try:
        # Start stream via hub
        sub = hub.subscribe(channel_id, client_id="racer_web")
        assert sub.get_frame(timeout=2.0) is not None
        hub.unsubscribe(channel_id, "racer_web")

        race_errors = []
        barrier = threading.Barrier(2)

        def cleaner_thread():
            try:
                barrier.wait(timeout=2.0)
                # Attempt atomic stop
                stream_manager.stop_stream_if_idle(channel_id)
            except Exception as e:
                race_errors.append(e)

        def attacher_thread():
            try:
                barrier.wait(timeout=2.0)
                # Concurrently attach
                stream_manager.add_consumer(channel_id, "desktop_racer")
            except Exception as e:
                race_errors.append(e)

        t1 = threading.Thread(target=cleaner_thread)
        t2 = threading.Thread(target=attacher_thread)
        t1.start()
        t2.start()
        t1.join(timeout=3.0)
        t2.join(timeout=3.0)

        assert len(race_errors) == 0, f"Race condition errors: {race_errors}"

        # If attacher won the lock, worker is still alive with desktop_racer registered
        # If cleaner won the lock, desktop_racer is safely registered or can restart
        with stream_manager._lock:
            worker = stream_manager._workers.get(channel_id)
            consumers = stream_manager.get_stream_consumers(channel_id)
            if "desktop_racer" in consumers and worker:
                assert worker.is_alive()
                stream_manager.remove_consumer(channel_id, "desktop_racer")
                stream_manager.stop_stream_if_idle(channel_id)
    finally:
        hub.stop_all()
        stream_manager.stop_stream(channel_id)


# SCENARIO 21: Clean application shutdown with active subscribers and native consumers
def test_scenario_21_application_shutdown_with_active_subscribers():
    """
    Validates complete application shutdown sequence:
    1. Active web subscribers and desktop consumers running concurrently.
    2. hub.stop_all() terminates all client queues and unblocks consumers.
    3. stream_manager.stop_all() cleanly halts all upstream threads.
    4. Zero thread leaks, deadlocks, or residual state.
    """
    hub = FrameDistributionHub(default_grace_period_sec=5.0)
    ch1 = "test_scen21_ch1"
    ch2 = "test_scen21_ch2"

    try:
        sub1 = hub.subscribe(ch1, client_id="web_1")
        sub2 = hub.subscribe(ch2, client_id="web_2")
        stream_manager.add_consumer(ch1, "desktop_window_1")

        assert sub1.get_frame(timeout=2.0) is not None
        assert sub2.get_frame(timeout=2.0) is not None

        # Execute application shutdown sequence
        t0 = time.time()
        hub.stop_all()
        stream_manager.stop_all()
        elapsed = time.time() - t0

        # Shutdown must complete rapidly without blocking
        assert elapsed < 5.0
        assert not sub1.is_active
        assert not sub2.is_active

        with stream_manager._lock:
            assert len(stream_manager._workers) == 0
            assert len(stream_manager._consumers) == 0
    finally:
        hub.stop_all()
        stream_manager.stop_stream(ch1)
        stream_manager.stop_stream(ch2)

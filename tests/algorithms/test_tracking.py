import numpy as np
import pytest

from irisgreen_capability.sim import SimObject, SimWorld
from irisgreen_tracking import (
    BoxMeasurement,
    ConstantVelocityKalman,
    RegionTracker,
    SingleObjectTracker,
    TemplateMeasurer,
    TrackingLost,
    aim_camera_point,
)


def test_kalman_estimates_velocity_and_leads():
    kf = ConstantVelocityKalman()
    kf.start((100.0, 100.0))
    for step in range(1, 31):
        center, velocity, measured = kf.update((100.0 + 50.0 * step * 0.1, 100.0), 0.1)
    assert measured
    assert velocity[0] == pytest.approx(50.0, rel=0.1)
    assert abs(velocity[1]) < 5.0
    ahead = kf.lead(0.5)
    assert ahead[0] == pytest.approx(center[0] + 25.0, rel=0.15)


def test_kalman_coasts_then_forgets():
    kf = ConstantVelocityKalman(max_lost=2)
    kf.start((0.0, 0.0))
    assert kf.update(None, 0.1)[2] is False
    assert kf.update(None, 0.1)[2] is False
    assert kf.update(None, 0.1) is None and not kf.active
    assert kf.update(None, 0.1) is None  # nothing to coast on
    with pytest.raises(ValueError):
        ConstantVelocityKalman(meas_std=0)


def test_aim_leads_but_obeys_the_gates():
    assert aim_camera_point((100, 100), (100, 0), lead_s=0.5) == (150.0, 100.0)
    assert aim_camera_point((100, 100), (100, 0), lead_s=0.5, measured=False) is None
    assert aim_camera_point((100, 100), (10, 0), lead_s=0.5) == (100.0, 100.0)  # too slow to lead
    # lead is capped by max_lead_px and by max_lead_s
    assert aim_camera_point((0, 0), (1000, 0), lead_s=10.0, max_lead_px=120)[0] == pytest.approx(120.0)
    assert aim_camera_point((0, 0), (200, 0), lead_s=10.0, max_lead_s=0.5)[0] == pytest.approx(100.0)
    # a reversal drops the stale lead
    assert aim_camera_point((100, 100), (-200, 0), lead_s=0.5, previous_velocity=(200, 0)) == (100.0, 100.0)
    assert aim_camera_point((float("nan"), 1), (0, 0), lead_s=0.1) is None


class ScriptedMeasurer:
    def __init__(self, scores_and_boxes):
        self.script = list(scores_and_boxes)
        self.reverted = 0

    def start(self, frame, bbox):
        return BoxMeasurement(bbox, 1.0)

    def track(self, frame):
        bbox, score = self.script.pop(0)
        return BoxMeasurement(bbox, score)

    def reset(self):
        pass

    def revert(self):
        self.reverted += 1


def test_single_object_tracker_treats_low_scores_as_misses():
    measurer = ScriptedMeasurer([
        ((110, 100, 40, 40), 0.9),
        ((500, 500, 40, 40), 0.02),  # a jump to a distractor must be ignored
        ((130, 100, 40, 40), 0.9),
    ])
    tracker = SingleObjectTracker(measurer, min_score=0.1)
    tracker.start(np.zeros((10, 10), np.uint8), (100, 100, 40, 40))

    first = tracker.update(None, 0.1)
    assert first.measured
    missed = tracker.update(None, 0.1)
    assert not missed.measured and missed.center[0] < 200 and measurer.reverted == 1
    assert missed.bbox[2:] == (40, 40)  # keeps the size while coasting
    assert tracker.update(None, 0.1).measured


def test_single_object_tracker_needs_a_start():
    tracker = SingleObjectTracker(ScriptedMeasurer([]))
    with pytest.raises(RuntimeError):
        tracker.update(None, 0.1)


def test_template_measurer_follows_a_moving_textured_patch():
    world = SimWorld(objects=[SimObject(x=420.0, y=300.0, vx=60.0, vy=25.0)])
    tracker = SingleObjectTracker(TemplateMeasurer())
    obj = world.objects[0]
    tracker.start(world.render(), (obj.x, obj.y, obj.width, obj.height))
    worst = 0.0
    for _ in range(40):
        world.step(0.1)
        track = tracker.update(world.render(), 0.1)
        worst = max(worst, float(np.hypot(track.center[0] - obj.center[0], track.center[1] - obj.center[1])))
    assert worst < 6.0
    assert track.velocity[0] > 20  # moving right


def test_template_measurer_validates_the_box():
    world = SimWorld()
    with pytest.raises(ValueError):
        TemplateMeasurer().start(world.render(), (5, 5, 3, 3))
    with pytest.raises(RuntimeError):
        TemplateMeasurer().track(world.render())


def test_region_tracker_follows_translation_and_reports_loss():
    world = SimWorld(objects=[SimObject(x=300.0, y=250.0, vx=40.0, vy=0.0, width=160, height=120)])
    obj = world.objects[0]
    polygon = np.array([[obj.x, obj.y], [obj.x + 160, obj.y], [obj.x + 160, obj.y + 120], [obj.x, obj.y + 120]])
    tracker = RegionTracker()
    tracker.start(world.render(), polygon)
    for _ in range(5):
        world.step(0.1)
        poly = tracker.update(world.render())
    assert np.allclose(poly.mean(axis=0), [obj.x + 80, obj.y + 60], atol=3.0)

    with pytest.raises(TrackingLost):
        tracker.update(np.zeros((100, 100), np.uint8))  # camera size changed
    assert not tracker.active
    with pytest.raises(TrackingLost):
        tracker.start(world.render(), np.array([[0, 0], [5, 0], [5, 5]]))  # too small

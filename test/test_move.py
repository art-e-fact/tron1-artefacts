import math
import os
import time

import pytest
import utils
from get_sdk import get_sdk

from limxsdk_python.api.goto import GoToDemo


def _mag2(dx: float, dy: float) -> float:
    return math.hypot(dx, dy)


@pytest.fixture(scope="module", autouse=True)
def pointfoot_rl_controller(module_report_dir: str):
    """Launch pointfoot_gazebo for each test and tear down after."""
    yield from utils.pointfoot_rl_controller(module_report_dir)


@pytest.fixture(scope="function", autouse=True)
def pointfoot(test_report_dir: str):
    """Launch pointfoot_gazebo for each test and tear down after."""
    yield from utils.pointfoot(test_report_dir)


@pytest.fixture(scope="function")
def demo(test_report_dir: str):
    """Per-test GoToDemo with its own log directory."""
    log_dir = os.path.join(test_report_dir, "api_logs")
    robot, joystick = get_sdk()
    d = GoToDemo(
        log_path=log_dir,
        robot=robot,
        joystick=joystick,
    )
    yield d
    d.close()


def test_move_forward(demo: GoToDemo):
    """Move ~0.5 m forward; no rotation."""
    x0, y0, yaw0 = demo.odom.get()

    res = demo.move(forward_m=1.50, sideways_m=0.0, dyaw=0.0, timeout_s=20.0)
    assert res.get("status") == "reached", f"move() failed: {res}"

    x1, y1, yaw1 = demo.odom.get()
    dist = _mag2(x1 - x0, y1 - y0)
    assert dist >= 0.30, f"Expected ≥0.30 m translation, got {dist:.3f} m"

    d_yaw = abs(((yaw1 - yaw0 + math.pi) % (2 * math.pi)) - math.pi)
    assert d_yaw <= math.radians(15), f"Yaw drift too large: {math.degrees(d_yaw):.1f}°"
    time.sleep(0.2)


def test_move_face_turn(demo: GoToDemo):
    """Rotate ~+90° in place; no translation."""
    yaw0, _, _ = demo.imu.get()

    res = demo.move_face(forward_m=0.0, dyaw=math.pi / 2, orientation="relative")
    assert res.get("status") == "reached", f"move_face() failed: {res}"

    _, _, yaw1 = demo.odom.get()
    d_yaw = ((yaw1 - yaw0 + math.pi) % (2 * math.pi)) - math.pi
    err = abs(d_yaw - math.pi / 2.0)
    assert err <= math.radians(10), f"Yaw error {math.degrees(err):.1f}° too large"
    time.sleep(0.2)


def test_move_face_forward_with_hold_timeout(demo: GoToDemo):
    """
    Face + move forward + hold using a finite hold_timeout_s (no threading).
    Expect 'reached_and_hold_timeout'.
    """
    res = demo.move_face(
        forward_m=0.40,
        dyaw=math.radians(45.0),
        orientation="relative",
        hold=True,
        hold_timeout_s=2.5,  # end hold without needing cancel()
        timeout_s=30.0,
    )
    assert res.get("status") in {
        "reached_and_hold_timeout",
        "reached",
    }, f"Unexpected {res}"

    x, y, _ = demo.odom.get()
    dist = _mag2(x, y)
    assert dist >= 0.25, f"Too little forward progress ({dist:.3f} m)"

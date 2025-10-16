import logging
import math
import os
import shutil
import time
from contextlib import suppress

import pytest
import utils
from artefacts_toolkit_rosbag.image_topics import extract_video
from get_sdk import get_sdk

from limxsdk_python.api.goto import GoToDemo

logger = logging.getLogger("artefacts." + __name__)


def _mag2(dx: float, dy: float) -> float:
    return math.hypot(dx, dy)


@pytest.fixture(scope="function", autouse=True)
def record_bag(test_report_dir, pointfoot, gz_bridge, sdk_bridge):
    bag_dir = f"{test_report_dir}/bag"
    vid_dir = f"{test_report_dir}/vid_bag"
    bag_gen = utils.bag_recorder(
        [
            "/clock",
            "/imu",
            "/joint_states",
        ],
        directory=bag_dir,
        use_sim_time=True,
    )
    vid_gen = utils.bag_recorder(
        [
            "/pointfoot/fpv/image",
            "/pointfoot/bird/image",
            "/pointfoot/fpv/camera_info",
            "/pointfoot/bird/camera_info",
        ],
        directory=vid_dir,
    )
    proc, bag_path = next(bag_gen)
    proc2, vid_path = next(vid_gen)
    yield
    with suppress(StopIteration):
        next(bag_gen)
    with suppress(StopIteration):
        next(vid_gen)
    logger.debug(f"Making videos in {test_report_dir}/video")
    os.makedirs(f"{test_report_dir}/video")
    for topic_name, filename in [
        ("/pointfoot/fpv/image", "fpv"),
        ("/pointfoot/bird/image", "birdeye"),
    ]:
        logger.debug(f"videoing topic {topic_name}")
        extract_video(vid_path, topic_name, f"{test_report_dir}/video/{filename}")
    #     # time.sleep(2)
    logger.debug(f"Removing heavy video bag")
    shutil.rmtree(vid_dir, ignore_errors=True)


@pytest.fixture(scope="module", autouse=True)
def pointfoot_rl_controller(module_report_dir: str):
    """Launch pointfoot_gazebo for each test and tear down after."""
    yield from utils.pointfoot_rl_controller(module_report_dir)


@pytest.fixture(scope="function", autouse=True)
def pointfoot(test_report_dir: str):
    """Launch pointfoot_gazebo for each test and tear down after."""
    yield from utils.pointfoot(test_report_dir)


@pytest.fixture(scope="module", autouse=True)
def gz_bridge(module_report_dir, pointfoot):
    yield from utils.manual_gs_bridge(module_report_dir)


@pytest.fixture(scope="module", autouse=True)
def sdk_bridge(module_report_dir):
    yield from utils.sdk_bridge(module_report_dir)


@pytest.fixture(scope="function")
def demo(test_report_dir: str):
    """Per-test GoToDemo with its own log directory."""
    log_dir = os.path.join(test_report_dir, "api_logs.jsonl")
    robot, joystick = get_sdk()
    d = GoToDemo(
        log_path=log_dir,
        robot=robot,
        joystick=joystick,
    )
    yield d
    d.close()


def test_move_forward(demo: GoToDemo):
    x0, y0, yaw0 = demo.odom.get()

    res = demo.move(forward_m=5.00, sideways_m=0.0, dyaw=0.0, timeout_s=20.0)
    logger.debug(res)
    assert res.get("status") == "reached", f"move() failed: {res}"

    x1, y1, yaw1 = demo.odom.get()
    dist = _mag2(x1 - x0, y1 - y0)
    assert dist <= 5.05, f"Expected <=5.05 m translation, got {dist:.3f} m"

    d_yaw = abs(((yaw1 - yaw0 + math.pi) % (2 * math.pi)) - math.pi)
    assert d_yaw <= math.radians(15), f"Yaw drift too large: {math.degrees(d_yaw):.1f}°"
    time.sleep(0.2)


def test_move_face_turn(demo: GoToDemo):
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
    Face + move forward + hold using a finite hold_timeout_s.
    """
    res = demo.move_face(
        forward_m=3.50,
        dyaw=math.radians(45.0),
        orientation="relative",
        hold=True,
        hold_timeout_s=3.5,
        timeout_s=30.0,
    )
    assert res.get("status") in {
        "reached_and_hold_timeout",
        "reached",
    }, f"Unexpected {res}"

    x, y, _ = demo.odom.get()
    dist = _mag2(x, y)
    assert dist >= 0.25, f"Too little forward progress ({dist:.3f} m)"

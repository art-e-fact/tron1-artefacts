import logging
import math
import os
import shutil
import threading
import time
from contextlib import suppress

import pytest
import utils
from artefacts_toolkit_config.config import get_artefacts_params
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
    )
    vid_gen = utils.bag_recorder(
        [
            "/pointfoot/fpv/image",
            "/pointfoot/bird/image",
            "/pointfoot/fpv/camera_info",
            "/pointfoot/bird/camera_info",
        ],
        directory=vid_dir,
        # use_sim_time=True,
    )
    proc, bag_path = next(bag_gen)
    proc2, vid_path = next(vid_gen)
    yield
    with suppress(StopIteration):
        next(bag_gen)
    with suppress(StopIteration):
        next(vid_gen)
    logger.debug(f"Making videos in output")
    os.makedirs("output", exist_ok=True)
    for topic_name, filename in [
        ("/pointfoot/fpv/image", "fpv"),
        ("/pointfoot/bird/image", "birdeye"),
    ]:
        logger.debug(f"videoing topic {topic_name}")
        extract_video(vid_path, topic_name, f"output/{filename}")
    #     # time.sleep(2)
    logger.debug(f"Removing heavy video bag")
    shutil.rmtree(vid_dir, ignore_errors=True)


@pytest.fixture(scope="module", autouse=True)
def pointfoot_rl_controller(module_report_dir: str):
    """limxsdk RL coontroller."""
    yield from utils.pointfoot_rl_controller(module_report_dir)


@pytest.fixture(scope="function", autouse=True)
def pointfoot(test_report_dir: str):
    """Gz sim."""
    yield from utils.pointfoot(test_report_dir)


@pytest.fixture(scope="function", autouse=True)
def gz_bridge(test_report_dir, pointfoot):
    """ros_gz bridge."""
    yield from utils.manual_gs_bridge(test_report_dir)


@pytest.fixture(scope="module", autouse=True)
def sdk_bridge(module_report_dir):
    """SDK to ROS bridge."""
    yield from utils.sdk_bridge(module_report_dir)


@pytest.fixture(scope="function")
def demo():
    robot, joystick = get_sdk()
    d = GoToDemo(robot=robot, joystick=joystick)
    yield d
    d.close()
    time.sleep(0.05)


MOVE_CASES = [
    pytest.param(
        dict(forward_m=1.0, sideways_m=0.5, dyaw_deg=20, timeout_s=20.0),
        dict(min_progress=0.6, max_yaw_err_deg=25, expect={"reached"}),
        id="move:xy+ori",
    ),
]

MOVE_FACE_CASES = [
    # success forward+turn
    pytest.param(
        dict(
            forward_m=5.0,
            dyaw_deg=150,
            orientation="relative",
            hold=False,
            hold_timeout_s=None,
            timeout_s=35.0,
        ),
        dict(expect={"reached"}, dist_range=(4.8, 5.2)),
        id="face:xy+ori",
    ),
    # success pure turn
    pytest.param(
        dict(
            forward_m=0.0,
            dyaw_deg=90,
            orientation="relative",
            hold=False,
            hold_timeout_s=None,
            timeout_s=20.0,
        ),
        dict(expect={"reached"}, yaw_target_deg=90, max_yaw_err_deg=12),
        id="face:turn90",
    ),
    # success forward + hold with finite timeout
    pytest.param(
        dict(
            forward_m=3.5,
            dyaw_deg=45,
            orientation="relative",
            hold=True,
            hold_timeout_s=3.5,
            timeout_s=35.0,
        ),
        dict(expect={"reached", "reached_and_hold_timeout"}, min_progress=0.25),
        id="face:hold_timeout",
    ),
    # move timeout
    pytest.param(
        dict(
            forward_m=10.0,
            dyaw_deg=0,
            orientation="relative",
            hold=False,
            hold_timeout_s=None,
            timeout_s=0.5,
        ),
        dict(expect={"move_timeout", "align_timeout"}),
        id="face:move_timeout",
    ),
]


@pytest.mark.parametrize("args,checks", MOVE_CASES)
def test_move(demo: GoToDemo, args, checks):
    res = demo.move(
        forward_m=args["forward_m"],
        sideways_m=args["sideways_m"],
        dyaw=math.radians(args["dyaw_deg"]),
        timeout_s=args["timeout_s"],
    )
    assert res.get("status") in checks["expect"], f"move() status {res}"

    x, y, yaw = demo.odom.get()
    if "min_progress" in checks:
        assert (
            _mag2(x, y) >= checks["min_progress"]
        ), f"Too little progress: ({x:.3f},{y:.3f})"
    if "max_yaw_err_deg" in checks:
        yaw_err = abs(yaw - demo._ref_yaw)
        assert yaw_err <= math.radians(
            checks["max_yaw_err_deg"]
        ), f"Yaw err {math.degrees(yaw_err):.1f}° too large"


@pytest.mark.parametrize("args,checks", MOVE_FACE_CASES)
def test_move_face(demo: GoToDemo, args, checks):
    x0, y0, _ = demo.odom.get()
    yaw0, _, _, _, _ = demo.imu.get()

    res = demo.move_face(
        forward_m=args["forward_m"],
        dyaw=math.radians(args["dyaw_deg"]),
        orientation=args["orientation"],
        hold=args["hold"],
        hold_timeout_s=args["hold_timeout_s"],
        timeout_s=args["timeout_s"],
    )
    assert res.get("status") in checks["expect"], f"move_face() status {res}"

    x1, y1, _ = demo.odom.get()
    yaw1, _, _, _, _ = demo.imu.get()

    if "dist_range" in checks:
        lo, hi = checks["dist_range"]
        dist = _mag2(x1 - x0, y1 - y0)
        assert lo <= dist <= hi, f"Expected ~{(lo+hi)/2:.1f} m, got {dist:.3f} m"

    if "min_progress" in checks:
        dist = _mag2(x1 - x0, y1 - y0)
        assert (
            dist >= checks["min_progress"]
        ), f"Too little forward progress ({dist:.3f} m)"

    if "yaw_target_deg" in checks:
        d_yaw = ((yaw1 - yaw0 + math.pi) % (2 * math.pi)) - math.pi
        err = abs(d_yaw - math.radians(checks["yaw_target_deg"]))
        assert err <= math.radians(
            checks["max_yaw_err_deg"]
        ), f"Yaw error {math.degrees(err):.1f}° too large"


def test_move_face_hold_cancel(demo: GoToDemo):
    """Separate test because it needs a cancel thread."""

    def _cancel_after(delay_s: float):
        time.sleep(delay_s)
        demo.cancel()

    killer = threading.Thread(target=_cancel_after, args=(1.0,), daemon=True)
    killer.start()

    res = demo.move_face(
        forward_m=1.0,
        dyaw=0.0,
        orientation="relative",
        hold=True,
        hold_timeout_s=None,  # infinite unless cancelled
        timeout_s=25.0,
    )
    assert res.get("status") in {
        "reached_and_cancelled",
        "reached",
    }, f"Unexpected {res}"

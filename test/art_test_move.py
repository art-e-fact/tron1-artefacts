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


def _wrap_pi(a: float) -> float:
    return (a + math.pi) % (2 * math.pi) - math.pi


@pytest.fixture
def move_case():
    """Return (args, checks) for 'move' if present; skip if not."""
    artefacts_params = get_artefacts_params()
    if "move" not in artefacts_params:
        pytest.skip("No 'move' parameters for this run")
    cfg_move = dict(artefacts_params["move"])

    args = {
        "forward_m": float(cfg_move["forward_m"]),
        "sideways_m": float(cfg_move["sideways_m"]),
        "dyaw_deg": float(cfg_move["dyaw_deg"]),
        "timeout_s": float(cfg_move["timeout_s"]),
    }

    checks = dict(cfg_move.get("checks", {}))
    checks.setdefault("expect", {"reached"})
    if ("min_progress" not in checks) and (args["forward_m"] or args["sideways_m"]):
        checks["min_progress"] = 0.6
    checks.setdefault("max_yaw_err_deg", 25)
    return args, checks


@pytest.fixture
def move_face_case():
    """Return (args, checks) for 'move_face' if present; skip if not."""
    artefacts_params = get_artefacts_params()
    if "move_face" not in artefacts_params:
        pytest.skip("No 'move_face' parameters for this run")
    cfg_face = dict(artefacts_params["move_face"])

    args = {
        "forward_m": float(cfg_face["forward_m"]),
        "dyaw_deg": float(cfg_face["dyaw_deg"]),
        "hold": bool(cfg_face.get("hold", False)),
        "hold_timeout_s": cfg_face.get("hold_timeout_s", None),
        "timeout_s": float(cfg_face["timeout_s"]),
        "orientation": "relative",
    }

    checks = dict(cfg_face.get("checks", {}))
    if args["forward_m"] > 0 and not args["hold"] and "dist_range" not in checks:
        dist_m = args["forward_m"]
        checks["dist_range"] = (0.9 * dist_m, 1.1 * dist_m)

    if abs(args["dyaw_deg"]) > 0.0:
        checks.setdefault("yaw_target_deg", args["dyaw_deg"])
        checks.setdefault("max_yaw_err_deg", 12)

    if "expect" not in checks:
        if args["timeout_s"] <= 2.0:
            checks["expect"] = {"move_timeout", "align_timeout"}
        elif args["hold"] and args["hold_timeout_s"]:
            checks["expect"] = {"reached_and_hold_timeout", "reached"}
        else:
            checks["expect"] = {"reached"}
    return args, checks


@pytest.fixture(scope="function", autouse=True)
def record_bag(test_report_dir, pointfoot, gz_bridge, sdk_bridge):
    report_dir = f"./test_report/tmp_bag"
    report_abs = os.path.abspath(report_dir)
    bag_dir = f"{report_abs}"
    # bag_dir = f"{test_report_dir}/bag"
    vid_dir = f"{test_report_dir}/vid_bag"
    bag_gen = utils.bag_recorder(
        ["/clock", "/imu", "/joint_states"],
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
    )
    proc, bag_path = next(bag_gen)
    proc2, vid_path = next(vid_gen)
    yield
    with suppress(StopIteration):
        next(bag_gen)
    with suppress(StopIteration):
        next(vid_gen)
    logger.debug(f"Making videos in {test_report_dir}/video")
    os.makedirs(f"{test_report_dir}/video", exist_ok=True)
    for topic_name, filename in [
        ("/pointfoot/fpv/image", "fpv"),
        ("/pointfoot/bird/image", "birdeye"),
    ]:
        logger.debug(f"videoing topic {topic_name}")
        extract_video(vid_path, topic_name, f"{test_report_dir}/video/{filename}")
    logger.debug("Removing heavy video bag")
    shutil.rmtree(vid_dir, ignore_errors=True)


@pytest.fixture(scope="module", autouse=True)
def pointfoot_rl_controller(module_report_dir: str):
    yield from utils.pointfoot_rl_controller(module_report_dir)


@pytest.fixture(scope="function", autouse=True)
def pointfoot(test_report_dir: str):
    yield from utils.pointfoot(test_report_dir)


@pytest.fixture(scope="function", autouse=True)
def gz_bridge(test_report_dir, pointfoot):
    yield from utils.manual_gs_bridge(test_report_dir)


@pytest.fixture(scope="module", autouse=True)
def sdk_bridge(module_report_dir):
    yield from utils.sdk_bridge(module_report_dir)


@pytest.fixture(scope="session", autouse=True)
def cleanup(session_report_dir):
    yield from utils.cleanup(session_report_dir)


@pytest.fixture(scope="function")
def demo():
    robot, joystick = get_sdk()
    controller = GoToDemo(robot=robot, joystick=joystick)
    yield controller
    controller.close()
    time.sleep(0.05)


def test_move(demo: GoToDemo, move_case):
    args, checks = move_case

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
        ), f"Yaw err {math.degrees(yaw_err):.1f}°"


def test_move_face(demo: GoToDemo, move_face_case):
    args, checks = move_face_case

    x0, y0, _ = demo.odom.get()
    yaw0, _, _, _, _ = demo.imu.get()

    res = demo.move_face(
        forward_m=args["forward_m"],
        dyaw=math.radians(args["dyaw_deg"]),
        orientation="relative",
        hold=args["hold"],
        hold_timeout_s=args["hold_timeout_s"],
        timeout_s=args["timeout_s"],
    )
    status = res.get("status")
    assert status in checks["expect"], f"move_face() status {res}"

    x1, y1, _ = demo.odom.get()
    yaw1, _, _, _, _ = demo.imu.get()

    success_like = status in {
        "reached",
        "reached_and_hold_timeout",
        "reached_and_cancelled",
    }

    if "dist_range" in checks and success_like:
        lo, hi = checks["dist_range"]
        dist = _mag2(x1 - x0, y1 - y0)
        assert lo <= dist <= hi, f"Expected ~{(lo+hi)/2:.1f} m, got {dist:.3f} m"

    if "min_progress" in checks and success_like:
        dist = _mag2(x1 - x0, y1 - y0)
        assert (
            dist >= checks["min_progress"]
        ), f"Too little forward progress ({dist:.3f} m)"

    if "yaw_target_deg" in checks and success_like:
        target_yaw_abs = _wrap_pi(yaw0 + math.radians(checks["yaw_target_deg"]))
        yaw_err = abs(_wrap_pi(yaw1 - target_yaw_abs))
        assert yaw_err <= math.radians(
            checks["max_yaw_err_deg"]
        ), f"Yaw error {math.degrees(yaw_err):.1f}° too large"

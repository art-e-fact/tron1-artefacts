import json
import logging
import math
import os
import shutil
import time
from contextlib import suppress

import pytest
import utils
from artefacts_toolkit_config.config import get_artefacts_params
from artefacts_toolkit_rosbag.image_topics import extract_video

logger = logging.getLogger("artefacts." + __name__)


def _wrap_pi(a: float) -> float:
    return (a + math.pi) % (2 * math.pi) - math.pi


def _mag2(dx: float, dy: float) -> float:
    return math.hypot(dx, dy)


def _yaw_diff(y1: float, y0: float) -> float:
    return _wrap_pi(y1 - y0)


@pytest.fixture(scope="module", autouse=True)
def pointfoot_rl_controller(module_report_dir: str):
    artefacts_params = get_artefacts_params()
    rl_type = artefacts_params.get("rl_type", None)
    if isinstance(rl_type, str):
        rl_type = rl_type.lower()
    yield from utils.pointfoot_rl_controller(module_report_dir, rl_type)


@pytest.fixture(scope="function", autouse=True)
def pointfoot(test_report_dir: str):
    yield from utils.pointfoot(test_report_dir)


@pytest.fixture(scope="function", autouse=True)
def gz_bridge(test_report_dir, pointfoot):
    yield from utils.manual_gs_bridge(test_report_dir)


@pytest.fixture(scope="module", autouse=True)
def sdk_bridge(module_report_dir):
    yield from utils.sdk_bridge(module_report_dir)


@pytest.fixture(scope="function", autouse=True)
def record_bag(test_report_dir, pointfoot, gz_bridge, sdk_bridge):
    """
    Record bag + video exactly like in the move test.
    """
    report_dir = "./test_report/tmp_bag"
    report_abs = os.path.abspath(report_dir)
    bag_dir = f"{report_abs}"
    vid_dir = f"{test_report_dir}/vid_bag"

    bag_gen = utils.bag_recorder(
        ["/clock", "/imu", "/joint_states"],
        directory=bag_dir,
    )
    vid_gen = utils.bag_recorder(
        [
            # "/pointfoot/fpv/image",
            "/pointfoot/bird/image",
            # "/pointfoot/fpv/camera_info",
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

    logger.debug("Making videos in output")
    os.makedirs("output", exist_ok=True)
    for topic_name, filename in [
        # ("/pointfoot/fpv/image", "fpv"),
        ("/pointfoot/bird/image", "birdeye"),
    ]:
        logger.debug(f"videoing topic {topic_name}")
        extract_video(vid_path, topic_name, f"output/{filename}")
    logger.debug("Removing heavy video bag")
    shutil.rmtree(vid_dir, ignore_errors=True)


@pytest.fixture(scope="function", autouse=False)
def gz_groundtruth(test_report_dir):
    yield from utils.gz_groundtruth(test_report_dir)


@pytest.fixture(scope="session", autouse=True)
def cleanup(session_report_dir):
    yield from utils.cleanup(session_report_dir)


def _sample_stream(gt_stream, duration_s: float, sample_hz: float = 10.0):
    """
    Collect (t, x, y, yaw) tuples for the given duration.
    """
    dt = 1.0 / sample_hz
    t0 = time.time()
    data = []

    p = gt_stream.latest(timeout=10.0)
    if p is None:
        raise RuntimeError("No ground truth available at start")
    data.append((p["t"], p["pos"]["x"], p["pos"]["y"], p["ori"]["yaw"]))

    while time.time() - t0 < duration_s:
        p = gt_stream.latest(timeout=1.0)
        if p is not None:
            data.append((p["t"], p["pos"]["x"], p["pos"]["y"], p["ori"]["yaw"]))
        time.sleep(dt)
    return data


def _drift_metrics(samples):
    """
    Compute drift metrics from a list of (t, x, y, yaw).
    """
    if len(samples) < 2:
        raise RuntimeError("Insufficient samples for drift")

    t0, x0, y0, yaw0 = samples[0]
    t1, x1, y1, yaw1 = samples[-1]
    dx, dy = (x1 - x0), (y1 - y0)

    final_xy_drift_m = _mag2(dx, dy)
    final_yaw_drift_rad = _yaw_diff(yaw1, yaw0)

    dists = [_mag2(x - x0, y - y0) for _, x, y, _ in samples]
    max_xy_drift_m = max(dists)
    rms_xy_drift_m = math.sqrt(sum(d * d for d in dists) / len(dists))

    yaws = [abs(_yaw_diff(yaw, yaw0)) for *_, yaw in samples]
    max_yaw_drift_rad = max(yaws)

    return {
        "duration_s": samples[-1][0] - samples[0][0],
        "final_xy_drift_m": final_xy_drift_m,
        "max_xy_drift_m": max_xy_drift_m,
        "rms_xy_drift_m": rms_xy_drift_m,
        "final_yaw_drift_deg": math.degrees(final_yaw_drift_rad),
        "max_yaw_drift_deg": math.degrees(max_yaw_drift_rad),
    }


def _get_drift_params():
    params = get_artefacts_params()

    durations = params.get("durations_s", 10)
    settle_s = float(params.get("settle_s", 10.0))
    checks = dict(params.get("checks", {}) or {})

    rl_type = params.get("rl_type", None)
    if isinstance(rl_type, str):
        rl_type = rl_type.lower()

    return rl_type, durations, settle_s, checks


def test_idle_drift(gz_groundtruth, session_report_dir):
    """
    No motion test for different time durations and policies.

    Each duration is a separate test, so function-scoped fixtures
    restart the simulation and bridges every time.
    """
    rl_type, duration_s, settle_s, checks = _get_drift_params()

    proc, gt = gz_groundtruth

    if settle_s > 0:
        time.sleep(settle_s)

    dur = float(duration_s)
    samples = _sample_stream(gt, duration_s=dur, sample_hz=10.0)
    metrics = _drift_metrics(samples)

    logger.info(
        f"[idle_drift] RL_TYPE={rl_type} dur={dur:.1f}s "
        f"final_xy={metrics['final_xy_drift_m']:.4f} m, "
        f"max_xy={metrics['max_xy_drift_m']:.4f} m, "
        f"rms_xy={metrics['rms_xy_drift_m']:.4f} m, "
        f"final_yaw={metrics['final_yaw_drift_deg']:.2f}°, "
        f"max_yaw={metrics['max_yaw_drift_deg']:.2f}°"
    )

    metrics_entry = {
        "Duration": metrics["duration_s"],
        "XY": metrics["final_xy_drift_m"],
        "XY_max": metrics["max_xy_drift_m"],
        "XY_rms": metrics["rms_xy_drift_m"],
        "Yaw_final_deg": metrics["final_yaw_drift_deg"],
        "Yaw_max_deg": metrics["max_yaw_drift_deg"],
        "RL_TYPE": rl_type,
    }

    max_drift_m = checks.get("max_drift_m", None)
    max_yaw_deg = checks.get("max_yaw_drift_deg", None)

    if max_drift_m is not None:
        assert metrics["max_xy_drift_m"] <= float(max_drift_m), (
            f"max_xy_drift {metrics['max_xy_drift_m']:.3f} m > "
            f"{float(max_drift_m):.3f} m (dur={dur}s)"
        )

    if max_yaw_deg is not None:
        assert metrics["max_yaw_drift_deg"] <= float(max_yaw_deg), (
            f"max_yaw_drift {metrics['max_yaw_drift_deg']:.1f}° > "
            f"{float(max_yaw_deg):.1f}° (dur={dur}s)"
        )

    metric_file = "output/metrics.json"

    to_write = json.dumps(metrics_entry)

    with open(metric_file, "w") as f:
        f.write(to_write)
        logger.debug(f"metrics written in {metric_file}")

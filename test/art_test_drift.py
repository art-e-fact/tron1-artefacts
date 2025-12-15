import json
import logging
import math
import os
import shutil
import time
from contextlib import suppress
from types import SimpleNamespace

import pytest
import utils
from artefacts_toolkit_config.config import get_artefacts_params
from artefacts_toolkit_rosbag.image_topics import extract_video
from logger import CsvXYFileHandler

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


@pytest.fixture(scope="function", autouse=False)
def gz_groundtruth(test_report_dir):
    yield from utils.gz_groundtruth(test_report_dir)


@pytest.fixture(scope="session", autouse=True)
def cleanup(session_report_dir):
    yield from utils.cleanup(session_report_dir)


@pytest.fixture(scope="function")
def bag_video(test_report_dir):
    """
    Use inside a test as:
        vid = bag_video
        vid.start()
        ... do stuff ...
    Recording will be stopped and video extracted in the fixture teardown.
    """
    report_dir = "./test_report/tmp_bag"
    report_abs = os.path.abspath(report_dir)
    bag_dir = f"{report_abs}"
    vid_dir = f"{test_report_dir}/vid_bag"

    state = {
        "started": False,
        "bag_gen": None,
        "vid_gen": None,
        "vid_path": None,
        "vid_dir": vid_dir,
    }

    def start():
        if state["started"]:
            return

        bag_gen = utils.bag_recorder(
            ["/clock", "/imu", "/joint_states"],
            directory=bag_dir,
        )
        logger.info(f"Start of the video recording: {time.time()}")
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

        state["started"] = True
        state["bag_gen"] = bag_gen
        state["vid_gen"] = vid_gen
        state["vid_path"] = vid_path

    helper = SimpleNamespace(start=start)

    try:
        yield helper
    finally:
        logger.info(f"End of the video recording: {time.time()}")
        if not state["started"]:
            return

        bag_gen = state["bag_gen"]
        vid_gen = state["vid_gen"]
        vid_path = state["vid_path"]
        vid_dir = state["vid_dir"]

        with suppress(StopIteration):
            next(bag_gen)
        with suppress(StopIteration):
            next(vid_gen)
        logger.info(f"Actual end of the video recording: {time.time()}")

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


def _sample_stream(gt_stream, duration_s: float, sample_hz: float = 10.0):
    """
    Collect (t, x, y, yaw) tuples for ~`duration_s` seconds of data,
    starting from the first available sample.
    """
    dt = 1.0 / sample_hz
    data = []

    p = gt_stream.latest(timeout=10.0)
    if p is None:
        raise RuntimeError("No ground truth available at start")
    logger.info(f"Start of stream: {time.time()}")
    data.append((p["t"], p["pos"]["x"], p["pos"]["y"], p["ori"]["yaw"]))

    t0 = time.time()
    while time.time() - t0 < duration_s:
        p = gt_stream.latest(timeout=1.0)
        if p is not None:
            data.append((p["t"], p["pos"]["x"], p["pos"]["y"], p["ori"]["yaw"]))
        time.sleep(dt)
    logger.info(f"End of stream: {time.time()}")
    return data


def _drift_metrics(samples: list):
    """
    Compute drift metrics from a list of (t, x, y, yaw).
    """
    if len(samples) < 2:
        raise RuntimeError("Insufficient samples for drift")

    t0, x0_w, y0_w, yaw0 = samples[0]
    t1, x1_w, y1_w, yaw1 = samples[-1]
    dx_w, dy_w = (x1_w - x0_w), (y1_w - y0_w)

    final_xy_drift_m = _mag2(dx_w, dy_w)
    final_yaw_drift_rad = _yaw_diff(yaw1, yaw0)

    dists = [_mag2(x - x0_w, y - y0_w) for _, x, y, _ in samples]
    max_xy_drift_m = max(dists)

    yaws = [abs(_yaw_diff(yaw, yaw0)) for *_, yaw in samples]
    max_yaw_drift_rad = max(yaws)

    x0_g, y0_g = -y0_w, x0_w
    x1_g, y1_g = -y1_w, x1_w

    return {
        "duration_s": t1 - t0,
        "final_xy_drift_m": final_xy_drift_m,
        "max_xy_drift_m": max_xy_drift_m,
        "final_yaw_drift_deg": math.degrees(final_yaw_drift_rad),
        "max_yaw_drift_deg": math.degrees(max_yaw_drift_rad),
        "x0": x0_g,
        "y0": y0_g,
        "x1": x1_g,
        "y1": y1_g,
    }


def _get_drift_params():
    params = get_artefacts_params()

    duration_s = params.get("durations_s", 10)
    settle_s = float(params.get("settle_s", 0.0))

    rl_type = params.get("rl_type", None)
    if isinstance(rl_type, str):
        rl_type = rl_type.lower()

    return rl_type, duration_s, settle_s


def test_idle_drift(gz_groundtruth, session_report_dir, bag_video):
    """
    No motion test for one duration / policy.

    Order:
    - ensure groundtruth is alive
    - reset groundtruth CSV handler (for the trajectory graph)
    - start bag+video
    - sample groundtruth for `durations_s`
    """
    rl_type, duration_s, settle_s = _get_drift_params()

    proc, gt = gz_groundtruth

    if settle_s > 0:
        time.sleep(settle_s)

    p0 = gt.latest(timeout=10.0)
    if p0 is None:
        raise RuntimeError("No ground truth available before recording")
    logger.info(f"Groundtruth ready: {time.time()}")

    lg_gt = logging.getLogger("groundtruth")

    for h in list(lg_gt.handlers):
        if isinstance(h, logging.FileHandler):
            lg_gt.removeHandler(h)
            try:
                h.close()
            except Exception:
                pass

    os.makedirs("output", exist_ok=True)
    gt_csv_path = "output/trajectory_gt.csv"
    gt_handler = CsvXYFileHandler(gt_csv_path, mode="w")
    gt_handler.setLevel(logging.INFO)
    lg_gt.addHandler(gt_handler)

    bag_video.start()

    dur = float(duration_s)
    samples = _sample_stream(gt, duration_s=dur, sample_hz=10.0)
    metrics = _drift_metrics(samples)

    lg_gt.removeHandler(gt_handler)
    try:
        gt_handler.close()
    except Exception:
        pass

    logger.info(
        f"[idle_drift] RL_TYPE={rl_type} dur={dur:.1f}s "
        f"final_xy={metrics['final_xy_drift_m']:.4f} m, "
        f"max_xy={metrics['max_xy_drift_m']:.4f} m, "
        f"final_yaw={metrics['final_yaw_drift_deg']:.2f}°, "
        f"max_yaw={metrics['max_yaw_drift_deg']:.2f}°"
    )

    metrics_entry = {
        "Duration": metrics["duration_s"],
        "XY_final": metrics["final_xy_drift_m"],
        "Yaw_final_deg": metrics["final_yaw_drift_deg"],
        "X_final": metrics["x1"],
        "Y_final": metrics["y1"],
    }

    metric_file = "output/metrics.json"
    os.makedirs("output", exist_ok=True)
    to_write = json.dumps(metrics_entry)
    with open(metric_file, "w") as f:
        f.write(to_write)
    logger.debug(f"metrics written in {metric_file}")

import logging
import math
import os
import re
import shutil
import signal
import subprocess
import threading
import time
from contextlib import contextmanager, suppress
from datetime import datetime
from pathlib import Path
from typing import Any, List

import psutil

logger = logging.getLogger("artefacts." + __name__)

gt_log = logging.getLogger("groundtruth")

# pose {
#   name: "pointfoot_entity"
#   id: 15
#   position {
#     x: 0.23211411816061789
#     y: 0.00017884603448919649
#     z: 0.16635816154401506
#   }
#   orientation {
#     x: -8.8417427662779909e-05
#     y: 0.76929943658213706
#     z: 7.3429243691027133e-05
#     w: 0.63888838122547753
#   }
# }
#
# POSE_START — detects the start of each block: "pose {"
# NAME_LINE  — captures the entity name: name: "pointfoot_entity"
# POS_RE     — extracts numeric x,y,z inside position { ... }
# ORI_RE     — extracts numeric x,y,z,w inside orientation { ... }
POSE_START = re.compile(r"^\s*pose\s*\{\s*$")
NAME_LINE = re.compile(r'^\s*name:\s*"([^"]+)"')
POS_RE = re.compile(
    r"position\s*\{[^}]*?x:\s*([-\deE\.]+)[^}]*?y:\s*([-\deE\.]+)[^}]*?z:\s*([-\deE\.]+)",
    re.DOTALL,
)
ORI_RE = re.compile(
    r"orientation\s*\{[^}]*?x:\s*([-\deE\.]+)[^}]*?y:\s*([-\deE\.]+)[^}]*?z:\s*([-\deE\.]+)[^}]*?w:\s*([-\deE\.]+)",
    re.DOTALL,
)


def _quat_to_yaw(x: float, y: float, z: float, w: float) -> float:
    return math.atan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z))


@contextmanager
def ignore_int():
    original_handler = signal.getsignal(signal.SIGINT)
    inter = False

    def cbk(*_, **__):
        nonlocal inter
        inter = True

    try:
        signal.signal(signal.SIGINT, cbk)
        yield
    finally:
        signal.signal(signal.SIGINT, original_handler)
        if inter:
            raise KeyboardInterrupt


def finish_process(
    p: subprocess.Popen,
    timeout: float = 2.0,
    repetition: int = 3,
    kill_timeout: float = 1.0,
    kill_repetition: int = 5,
):
    """
    Gracefully terminate a subprocess.Popen process and its children.

    Args:
        p: subprocess.Popen object
        timeout: seconds to wait after SIGTERM before escalating
        kill_timeout: seconds to wait after SIGKILL before giving up
    """
    pid = p.pid
    try:
        pgid = os.getpgid(pid)
    except OSError:
        print("SHUDOWN: already dead")
        return

    try:
        parent_proc = psutil.Process(p.pid)
    except psutil.NoSuchProcess:
        print("SHUDOWN: already dead (proc)")
        return True

    all_proc = parent_proc.children(recursive=True) + [parent_proc]

    def is_stopped() -> bool:
        nonlocal all_proc
        for proc in all_proc:
            is_running = proc.is_running()
            is_in_reality_dead = False
            if is_running:
                is_in_reality_dead = proc.status() in [
                    psutil.STATUS_ZOMBIE,
                    psutil.STATUS_DEAD,
                ]
            is_alive = is_running and not is_in_reality_dead
            if is_alive:
                # print(f"still running: {proc.name}")
                return False
        return True

    for _ in range(repetition):
        # send SIGTERM to process group if possible
        try:
            logger.debug("Sending: SIGTERM")
            os.killpg(pgid, signal.SIGTERM)
        except ProcessLookupError:
            logger.debug("SUCCESS: on SIGTERM")
            return

        # wait for graceful exit
        deadline = time.time() + timeout
        while time.time() < deadline:
            if is_stopped():
                logger.debug("SUCCESS: on SIGTERM")
                return
            time.sleep(0.1)

    for _ in range(kill_repetition):
        # send SIGKILL to process group if possible
        try:
            logger.debug("Sending: SIGKILL")
            os.killpg(pgid, signal.SIGKILL)
        except ProcessLookupError:
            logger.debug("SUCCESS: on SIGKILL")
            return

        # wait for graceful exit
        deadline = time.time() + kill_timeout
        while time.time() < deadline:
            if is_stopped():
                logger.debug("SUCCESS: on SIGKILL")
                return
            time.sleep(0.1)


def manual_gs_bridge(test_report_dir):
    p_name = "gazebo_bridge"
    prefix = f"STARTUP [{p_name}]: "
    report_abs = test_report_dir
    stdout_file = open(f"{report_abs}/bridge_stdout.txt", "wb")
    stderr_file = open(f"{report_abs}/bridge_stderr.txt", "wb")
    p = subprocess.Popen(
        [
            "ros2",
            "run",
            "ros_gz_bridge",
            "parameter_bridge",
            "/pointfoot/fpv/image@sensor_msgs/msg/Image@gz.msgs.Image",
            "/pointfoot/bird/image@sensor_msgs/msg/Image@gz.msgs.Image",
            "/pointfoot/fpv/camera_info@sensor_msgs/msg/CameraInfo@gz.msgs.CameraInfo",
            "/pointfoot/bird/camera_info@sensor_msgs/msg/CameraInfo@gz.msgs.CameraInfo",
        ],
        stdout=stdout_file,
        stderr=stderr_file,
        preexec_fn=os.setsid,  # create a new process group/session
    )
    logger.debug(f"{prefix}process launching [{p.args}]")
    logger.debug(f"{prefix}tests starting")
    yield p
    prefix = f"SHUTDOWN [{p_name}]: "
    logger.debug(f"{prefix}processes stopping")
    with ignore_int():
        finish_process(p)
    logger.debug(f"{prefix}processes stopped")
    logger.debug(f"{prefix}files closing {report_abs}")
    stdout_file.close()
    stderr_file.close()
    logger.debug(f"{prefix}files closed")
    logger.debug(f"{prefix}finished")


def sdk_bridge(module_report_dir):
    p_name = "sdk_bridge"
    prefix = f"STARTUP [{p_name}]: "
    report_abs = module_report_dir
    stdout_file = open(f"{report_abs}/sdk_bridge_stdout.txt", "wb")
    stderr_file = open(f"{report_abs}/sdk_bridge_stderr.txt", "wb")
    p = subprocess.Popen(
        [
            "ros2",
            "run",
            "limxsdk_python",
            "pointfoot_sdk_bridge",
        ],
        stdout=stdout_file,
        stderr=stderr_file,
        preexec_fn=os.setsid,  # create a new process group/session
    )
    logger.debug(f"{prefix}process launching [{p.args}]")
    logger.debug(f"{prefix}tests starting")
    yield p
    prefix = f"SHUTDOWN [{p_name}]: "
    logger.debug(f"{prefix}processes stopping")
    with ignore_int():
        finish_process(p)
    logger.debug(f"{prefix}processes stopped")
    logger.debug(f"{prefix}files closing {report_abs}")
    stdout_file.close()
    stderr_file.close()
    logger.debug(f"{prefix}files closed")
    logger.debug(f"{prefix}finished")


def pointfoot(test_report_dir):
    p_name = "pointfoot_gazebo"
    prefix = f"STARTUP [{p_name}]: "
    report_abs = test_report_dir
    stdout_file = open(f"{report_abs}/sim_stdout.txt", "wb")
    stderr_file = open(f"{report_abs}/sim_stderr.txt", "wb")
    p = subprocess.Popen(
        [
            "ros2",
            "launch",
            "pointfoot_gazebo",
            "empty_world.launch.py",
            "server:=true",
        ],
        stdout=stdout_file,
        stderr=stderr_file,
        preexec_fn=os.setsid,  # create a new process group/session
    )
    logger.debug(f"{prefix}process launching [{p.args}]")
    logger.debug(f"{prefix}tests starting")
    yield p
    prefix = f"SHUTDOWN [{p_name}]: "
    logger.debug(f"{prefix}processes stopping")
    with ignore_int():
        finish_process(p)
    logger.debug(f"{prefix}processes stopped")
    logger.debug(f"{prefix}files closing {report_abs}")
    stdout_file.close()
    stderr_file.close()
    logger.debug(f"{prefix}files closed")
    logger.debug(f"{prefix}finished")


def pointfoot_rl_controller(module_report_dir, rl_type: str | None = None):
    p_name = "pointfoot_rl_controller"
    prefix = f"STARTUP [{p_name}]: "
    report_abs = module_report_dir
    stdout_file = open(f"{report_abs}/ctrl_stdout.txt", "wb")
    stderr_file = open(f"{report_abs}/ctrl_stderr.txt", "wb")

    env = os.environ.copy()
    selected = (rl_type or env.get("RL_TYPE") or "isaacgym").lower()
    env["RL_TYPE"] = selected
    logger.debug(f"{prefix}RL_TYPE={selected}")

    p = subprocess.Popen(
        [
            "python3",
            "src/rl-deploy-python/main.py",
        ],
        stdout=stdout_file,
        stderr=stderr_file,
        preexec_fn=os.setsid,  # create a new process group/session
        env=env,
    )
    logger.debug(f"{prefix}process launching [{p.args}]")
    logger.debug(f"{prefix}tests starting")
    yield p
    prefix = f"SHUTDOWN [{p_name}]: "
    logger.debug(f"{prefix}processes stopping")
    with ignore_int():
        finish_process(p)
    logger.debug(f"{prefix}processes stopped")
    logger.debug(f"{prefix}files closing {report_abs}")
    stdout_file.close()
    stderr_file.close()
    logger.debug(f"{prefix}files closed")
    logger.debug(f"{prefix}finished")


def bag_recorder(topic_names: List[str], directory="rosbags", use_sim_time=False):
    """Create a rosbag2 recorder for a given list of topic names and return the node and the filepath"""

    path_to_rosbags_dir = Path.cwd() / Path(directory)
    if not path_to_rosbags_dir.is_dir():
        path_to_rosbags_dir.mkdir(parents=True, exist_ok=True)

    yyyymmddhhmmss = datetime.now().strftime("%Y_%m_%d-%H_%M_%S")
    rosbag_filepath = directory + "/rosbag2_" + yyyymmddhhmmss
    # rosbag_filepath = directory
    logger.info(f"Rosbag path: {rosbag_filepath}")
    rosbag_cmd = (
        ["ros2", "bag", "record"]
        + ["--topics"]
        + topic_names
        + ["-o", rosbag_filepath, "--storage", "mcap"]
    )
    if use_sim_time:
        rosbag_cmd = rosbag_cmd + ["--use-sim-time"]
    p = subprocess.Popen(
        rosbag_cmd,
        preexec_fn=os.setsid,  # create a new process group/session
    )
    logger.debug(f"Starting rosbag process {p.args}")
    yield p, rosbag_filepath
    logger.debug("stopping rosbag")
    with ignore_int():
        finish_process(p)
    # wait for rosbag to close files
    time.sleep(5.0)
    logger.debug("rosbag closed")


def cleanup(session_report_dir):
    """
    Removes 0-byte files recursively under session_report_dir
    Removes empty directories
    """
    yield
    prefix = "[CLEANUP] "
    logger.debug(f"{prefix}Starting cleanup in: {session_report_dir}")

    for root, dirs, files in os.walk(session_report_dir, topdown=False):
        for f in files:
            path = os.path.join(root, f)
            try:
                if os.path.getsize(path) == 0:
                    os.remove(path)
                    logger.debug(f"{prefix}Removed 0-byte file: {path}")
            except OSError as e:
                logger.debug(f"{prefix}Failed to check/remove file {path}: {e}")

        for d in dirs:
            dirpath = os.path.join(root, d)
            try:
                if not os.listdir(dirpath):
                    shutil.rmtree(dirpath, ignore_errors=True)
                    logger.debug(f"{prefix}Removed empty directory: {dirpath}")
            except OSError as e:
                logger.debug(f"{prefix}Failed to remove directory {dirpath}: {e}")

    logger.debug(f"{prefix}Cleanup completed.")


def gz_groundtruth(test_report_dir, entity_name="pointfoot_entity", world="default"):
    """
    Gets groundtruth pose from gz topic for given entity name.
    """
    p_name = "gz_groundtruth"
    prefix = f"STARTUP [{p_name}]: "

    stdout_file = open(f"{test_report_dir}/gz_gt_stdout.txt", "wb")
    stderr_file = open(f"{test_report_dir}/gz_gt_stderr.txt", "wb")

    p = subprocess.Popen(
        ["gz", "topic", "-e", "--topic", f"/world/{world}/pose/info"],
        stdout=subprocess.PIPE,
        stderr=stderr_file,
        text=True,
        preexec_fn=os.setsid,
    )

    logger.debug(f"{prefix}process launching [{p.args}] entity={entity_name}")

    stop_evt = threading.Event()
    latest_lock = threading.Lock()
    latest_rec = None

    def _reader():
        nonlocal latest_rec
        prefix = f"READER [{p_name}]: "
        if not p.stdout:
            return
        inside, depth, buf = False, 0, []
        for line in p.stdout:
            if stop_evt.is_set():
                break
            stdout_file.write(line.encode("utf-8"))
            if not inside:
                if POSE_START.match(line):
                    inside, depth, buf = True, 1, [line]
                continue
            buf.append(line)
            depth += line.count("{") - line.count("}")
            if depth > 0:
                continue
            inside = False
            block = "".join(buf)
            if f'name: "{entity_name}"' not in block:
                continue
            try:
                pos = POS_RE.findall(block)
                ori = ORI_RE.findall(block)
                if not pos or not ori:
                    continue
                px, py, pz = map(float, pos[0])
                qx, qy, qz, qw = map(float, ori[0])
                yaw = _quat_to_yaw(qx, qy, qz, qw)
                latest_rec = {
                    "t": time.time(),
                    "pos": {"x": px, "y": py, "z": pz},
                    "ori": {"x": qx, "y": qy, "z": qz, "w": qw, "yaw": yaw},
                }
                with latest_lock:
                    gt_log.info("gt_pose", extra={"data": latest_rec})
                    gt_log.info("gt_xy", extra={"x": -py, "y": px})
            except Exception as e:
                logger.debug(f"{prefix} parse error: {e}")

    th = threading.Thread(target=_reader, daemon=True)
    th.start()

    class Stream:
        @staticmethod
        def latest(timeout: float | None = None):
            end = time.time() + timeout if timeout else None
            while True:
                with latest_lock:
                    if latest_rec:
                        return latest_rec.copy()
                if not end or time.time() > end:
                    return None
                time.sleep(0.05)

    yield p, Stream

    prefix = f"SHUTDOWN [{p_name}]: "
    logger.debug(f"{prefix}stopping")
    stop_evt.set()
    with ignore_int():
        finish_process(p)
    th.join(timeout=1.0)
    stdout_file.close()
    stderr_file.close()
    logger.debug(f"{prefix}finished")

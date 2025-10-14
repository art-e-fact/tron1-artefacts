import logging
import os
import signal
import subprocess
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, List

import psutil

logger = logging.getLogger("artefacts." + __name__)


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
            # "topic",
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


def pointfoot_rl_controller(module_report_dir):
    p_name = "pointfoot_rl_controller"
    prefix = f"STARTUP [{p_name}]: "
    report_abs = module_report_dir
    stdout_file = open(f"{report_abs}/ctrl_stdout.txt", "wb")
    stderr_file = open(f"{report_abs}/ctrl_stderr.txt", "wb")
    p = subprocess.Popen(
        [
            "python3",
            "src/rl-deploy-python/main.py",
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


def bag_recorder(topic_names: List[str], directory="rosbags", use_sim_time=False):
    """Create a rosbag2 recorder for a given list of topic names and return the node and the filepath"""

    path_to_rosbags_dir = Path.cwd() / Path(directory)
    if not path_to_rosbags_dir.is_dir():
        path_to_rosbags_dir.mkdir(parents=True, exist_ok=True)

    yyyymmddhhmmss = datetime.now().strftime("%Y_%m_%d-%H_%M_%S")
    rosbag_filepath = directory + "/rosbag2_" + yyyymmddhhmmss
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
    logger.debug("rosbag closed")

# doit_config.py
import os
from glob import glob
from typing import List

from doit import get_var

REPOS_TEMPLATE = {
    "limxsdk_python": {
        "url": "https://github.com/art-e-fact/tron1-artefacts-lowlevel.git",
        "versions": {"jazzy": "main", "humble": "main"},
    },
    "robot-description": {
        "url": "https://github.com/art-e-fact/tron1-artefacts-description.git",
        "versions": {"jazzy": "main", "humble": "main"},
    },
    "robot-visualization": {
        "url": "https://github.com/limxdynamics/robot-visualization.git",
        "versions": {"jazzy": "master", "humble": "master"},
    },
    "robot-gazebo": {
        "url": "https://github.com/art-e-fact/tron1-artefacts-demo.git",
        "versions": {"jazzy": "harmonic", "humble": "ignition"},
    },
}

OVERIDE_CONFIG = {
    # 'venv=y' -> use python venv (default y on jazzy, n on humble)
    "venv": None,
    # 'syml=y' -> colcon --symlink-install
    "syml": None,
    # 'pipforce=y' -> add --force-reinstall --upgrade to pip install
    "pipforce": None,
    # 'low_mem=y' -> add light LTO flags for pip builds
    "low_mem": None,
    # extra args for pip install of your workspace deps
    "pip_args": None,
    # extra args for colcon build
    "colcon_args": None,
    # override .repos file (rel/abs)
    "repos": None,
}

VALID_ROS = {"humble", "jazzy"}


def get_ros_distro() -> str:
    """Pick ROS 2 distro limited to jazzy/humble, defaulting to jazzy."""
    env = os.getenv("ROS_DISTRO")
    if env in VALID_ROS:
        return env
    roses = {p.split("/")[-1] for p in glob("/opt/ros/*")}
    if "jazzy" in roses:
        return "jazzy"
    if "humble" in roses:
        return "humble"
    return "jazzy"


ros = get_ros_distro()

# defaults per ROS
if ros == "jazzy":
    default_values = {
        "venv": "y",
        "syml": "y",
        "low_mem": "n",
        "pipforce": "n",
        "pip_args": "",
        "colcon_args": "",
        "repos": "tron_artefacts.repos",
    }
elif ros == "humble":
    default_values = {
        "venv": "y",
        "syml": "y",
        "low_mem": "n",
        "pipforce": "n",
        "pip_args": "",
        "colcon_args": "",
        "repos": "tron_artefacts.repos",
    }
else:
    raise Exception("Only 'humble' and 'jazzy' are supported.")

for k, v in OVERIDE_CONFIG.items():
    if v is not None:
        default_values[k] = v

config = {
    "ros2": ros,
    "venv": get_var("venv", default_values["venv"]) == "y",
    "syml": get_var("syml", default_values["syml"]) == "y",
    "low_mem": get_var("low_mem", default_values["low_mem"]) == "y",
    "pipforce": get_var("pipforce", default_values["pipforce"]) == "y",
    "pip_args": get_var("pip_args", default_values["pip_args"]),
    "colcon_args": get_var("colcon_args", default_values["colcon_args"]),
    "repos": get_var("repos", default_values["repos"]),
}

# doit_config.py
import dataclasses
import os
import platform
from glob import glob
from typing import List, Literal, Optional

from doit import get_var

ubuntu_ver = platform.freedesktop_os_release()["VERSION_ID"]
ros2: Literal["humble", "jazzy"] = {  # type: ignore
    "22.04": "humble",
    "24.04": "jazzy",
}[ubuntu_ver]

REPO_SPECS = {
    "limxsdk_python": {
        "url": "https://github.com/art-e-fact/tron1-artefacts-pythonsdk.git",
        "versions": {"jazzy": "main", "humble": "main"},
    },
    "robot-description": {
        "url": "https://github.com/art-e-fact/tron1-artefacts-description.git",
        "versions": {"jazzy": "main", "humble": "humble"},
    },
    "robot-visualization": {
        "url": "https://github.com/limxdynamics/robot-visualization.git",
        "versions": {"jazzy": "master", "humble": "master"},
    },
    "robot-gazebo": {
        "url": "https://github.com/art-e-fact/tron1-artefacts-demo.git",
        "versions": {"jazzy": "main", "humble": "humble"},
    },
    "rl-deploy-python": {
        "url": "https://github.com/art-e-fact/tron1-rl-deploy-artefacts.git",
        "versions": {"jazzy": "main", "humble": "main"},
    },
    "robot-joystick": {
        "url": "https://github.com/limxdynamics/robot-joystick.git",
        "versions": {"jazzy": "main", "humble": "main"},
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
}

VALID_ROS = {"humble", "jazzy"}


class PATH:
    """Paths and file locations"""

    setup = os.path.abspath("./")
    root = setup
    src = os.path.join(setup, "src")


def get_files_reg(path_regex: str) -> List[str]:
    dirs_and_files = glob(path_regex, recursive=True)
    return [f for f in dirs_and_files if os.path.isfile(f)]


def get_files(path: str) -> List[str]:
    """Gets all files in a directory and its children dirs"""
    return get_files_reg(os.path.join(path, "**"))


@dataclasses.dataclass
class GitRepo:
    """Class to help caching github repos"""

    location: str
    link: str
    branch: str = "HEAD"

    @property
    def src_dir(self) -> str:
        """directory of the cached repo"""
        return os.path.join(PATH.src, self.location)

    @property
    def src_files(self) -> List[str]:
        """Targets indicating the  repo files.

        As long as the repo is not downloaded this will be empty"""
        return get_files(self.src_dir)

    @property
    def uptodate(self) -> List[str]:
        """Shell Command returning false if the src is out of date

        use this in doit task's up_to_date field."""
        return [
            f"""cd {self.src_dir} && git fetch && [ "$(git rev-parse HEAD)" = "$(git rev-parse origin/{self.branch})" ]"""
        ]


def tron_git_repos_for_ros() -> list[GitRepo]:
    """Materialize GitRepo objects from REPO_SPECS for current ros2 (humble/jazzy)."""
    out = []
    for name, spec in REPO_SPECS.items():
        out.append(
            GitRepo(
                location=name,
                link=spec["url"],
                branch=spec["versions"][ros2],
            )
        )
    return out


def get_ros_distro() -> str:
    """Pick ROS 2 distro limited to jazzy/humble, defaulting to jazzy."""
    env = os.getenv("ROS_DISTRO")
    if env in VALID_ROS:
        return env
    roses = {p.split("/")[-1] for p in glob("/opt/ros2/*")}
    if "jazzy" in roses:
        return "jazzy"
    if "humble" in roses:
        return "humble"
    return "jazzy"


# defaults per ROS
if ros2 == "jazzy":
    default_values = {
        "venv": "y",
        "syml": "y",
        "low_mem": "n",
        "pipforce": "n",
        "pip_args": "",
        "colcon_args": "",
    }
elif ros2 == "humble":
    default_values = {
        "venv": "y",
        "syml": "y",
        "low_mem": "n",
        "pipforce": "n",
        "pip_args": "",
        "colcon_args": "",
    }

for k, v in OVERIDE_CONFIG.items():
    if v is not None:
        default_values[k] = v

config = {
    "ros2": ros2,
    "venv": get_var("venv", default_values["venv"]) == "y",
    "syml": get_var("syml", default_values["syml"]) == "y",
    "low_mem": get_var("low_mem", default_values["low_mem"]) == "y",
    "pipforce": get_var("pipforce", default_values["pipforce"]) == "y",
    "pip_args": get_var("pip_args", default_values["pip_args"]),
    "colcon_args": get_var("colcon_args", default_values["colcon_args"]),
}

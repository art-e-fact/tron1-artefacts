"""
Tron workspace automation with doit.

- Installs tools (vcstool, rosdep, colcon, venv helpers)
- Creates src/, imports & pulls repos (vcs)
- Sets up Python venv (optional; default on Jazzy)
- Installs Python deps from ./requirements.txt
- rosdep init/update/install
- Per-package colcon build with incremental targets

Run from WORKSPACE ROOT (the dir that contains `src/`, `requirements.txt`).
"""

import os
import shutil
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from glob import glob
from os import path
from pathlib import Path
from time import time
from typing import Callable, Dict, List, Sequence, Set, Union

from doit.task import clean_targets
from doit.tools import Interactive, check_timestamp_unchanged

from doit_config import config, get_ros_distro, ros

here = path.abspath("./")
stamps = path.abspath("./stamps")

REPOS_FILE = path.abspath(config["repos"])  # default ./tron_artefacts.repos
REQ_FILE = path.abspath("requirements.txt")  # requirements live in workspace root

pip_args: str = (config["pip_args"] or "").strip()
if config["pipforce"]:
    if "--force-reinstall" not in pip_args:
        pip_args += " --force-reinstall"
    if "--upgrade" not in pip_args:
        pip_args += " --upgrade"

pip_low_mem = (
    """CXXFLAGS="-fno-fat-lto-objects --param ggc-min-expand=10 --param ggc-min-heapsize=2048" """
    if config["low_mem"]
    else ""
)

colcon_args: str = (config["colcon_args"] or "") + " --cmake-args -Wno-dev "
if config["syml"]:
    colcon_args += "--symlink-install "

ros_src_cmd = f". /opt/ros/{ros}/setup.sh && "

use_venv: bool = config["venv"]
VENV_READY_TRG = f"{here}/venv/COLCON_IGNORE"
env_src_cmd = f""". {here}/venv/bin/activate && """ if use_venv else ""
env_path_cmd = ""  # not needed
ws_src_cmd = f"{env_src_cmd}{env_path_cmd}. {here}/install/setup.sh && "
is_pip_usable = [VENV_READY_TRG] if use_venv else []


def remove_dir(dirs: List[str]) -> List[Callable]:
    out: List[Callable] = []
    for d in dirs:
        if path.exists(d):
            out.append(lambda x=d: shutil.rmtree(x) if path.exists(x) else None)
    return out


def _require_repos():
    if not path.isfile(REPOS_FILE):
        raise RuntimeError(
            f".repos file not found: {REPOS_FILE}\n"
            "Set it via CLI:  doit repos=/abs/or/relative/file.repos"
        )


@dataclass
class RosPackage:
    name: str
    src: str
    xml: ET.Element
    other_packages: Set[str] = field(default_factory=set)

    @property
    def bld_depend(self) -> Set[str]:
        depend = {e.text for e in self.xml.findall("depend") if e.text}
        exec_depend = {e.text for e in self.xml.findall("exec_depend") if e.text}
        all_dep = depend | exec_depend
        return all_dep & self.other_packages

    @property
    def targets(self) -> List[str]:
        return [self.output_setup(self.name)]

    @property
    def code_dep(self) -> Set[str]:
        source_files = set(glob(rf"{self.src}/**", recursive=True))
        garbage = set(glob(rf"{self.src}/**/*cache*", recursive=True)) | set(
            glob(rf"{self.src}/**/*cache*/**", recursive=True)
        )
        return {f for f in (source_files - garbage) if path.isfile(f)}

    @property
    def build_dep(self) -> Set[str]:
        pypak_dir: Set[str] = {
            f[: -len(r"/__init__.py")]
            for f in glob(rf"{self.src}/**/__init__.py", recursive=True)
        }
        linked_pyfiles = {py for d in pypak_dir for py in glob(f"{d}/*")}
        builded_src_files = {
            f for f in (self.code_dep - linked_pyfiles) if path.isfile(f)
        }
        other_outputs = {self.output_setup(d) for d in self.bld_depend} | {
            self.output_stamp(d) for d in self.bld_depend
        }
        return other_outputs | builded_src_files

    @staticmethod
    def output_setup(name) -> str:
        return f"install/{name}/share/{name}/package.sh"

    @staticmethod
    def output_stamp(name) -> str:
        return f"build/{name}/doit.stamp"

    @property
    def cleans(self) -> Sequence[Union[str, Callable]]:
        return remove_dir(
            [f"build/{self.name}", f"log/{self.name}", f"install/{self.name}"]
        )


def extract_package_data(xml_path: str) -> RosPackage:
    xml_root = ET.parse(xml_path).getroot()
    pkg_path = xml_path[: -len("/package.xml")]
    return RosPackage(name=xml_root.find("name").text, src=pkg_path, xml=xml_root)


IGNORED_DIR_NAMES = {"lib", "install", "build", ".git", ".venv", "venv"}


def _is_ignored_tree(p: Path) -> bool:
    # Skip if any ancestor (from src/ down) is an install-like folder
    for part in p.parts:
        if part in IGNORED_DIR_NAMES:
            return True
    return False


def _looks_like_real_pkg(pkg_dir: Path) -> bool:
    # Heuristic: must have ament build file next to package.xml
    return any(
        (pkg_dir / name).exists()
        for name in ("CMakeLists.txt", "setup.py", "pyproject.toml")
    )


def packages(root: str) -> Dict[str, RosPackage]:
    pk_dict: Dict[str, RosPackage] = {}
    for px in glob(f"{root}/**/package.xml", recursive=True):
        pkg_dir = Path(px).parent.resolve()
        # ignore vendor/install artifacts
        if _is_ignored_tree(pkg_dir.relative_to(Path(root).resolve())):
            continue
        if not _looks_like_real_pkg(pkg_dir):
            continue
        p = extract_package_data(str(px))
        pk_dict[p.name] = p
    names = set(pk_dict.keys())
    for pk in pk_dict.values():
        pk.other_packages = names
    return pk_dict


src_pkg = packages("src")


# ------------------------------ Tasks ------------------------------


def task_tools():
    """Install workspace tools: vcstool, colcon, rosdep, venv helpers."""
    yield {"name": None, "actions": None, "doc": "Installs apt-based tooling."}
    yield {
        "name": "apt",
        "actions": [
            Interactive("sudo apt update"),
            Interactive(
                "sudo apt install -y "
                "python3-vcstool python3-colcon-common-extensions "
                "python3-rosdep git build-essential curl "
                "python3-venv python3-virtualenv "
            ),
        ],
        "uptodate": ["vcs --help", "colcon --help", "rosdep --help"],
        "verbosity": 2,
    }


def task_workspace():
    """Create src/ and import/pull repos with vcstool."""
    yield {"name": None, "actions": None, "doc": "Creates src/ and imports repos."}
    yield {
        "name": "mkdir-stamp",
        "actions": [f"mkdir -p {here}/stamps"],
        "targets": [f"{here}/stamps"],
        "uptodate": [path.isdir(f"{here}/stamps")],
        "verbosity": 2,
    }
    yield {
        "name": "mkdir-src",
        "actions": [f"mkdir -p {here}/src"],
        "targets": [f"{here}/src"],
        "uptodate": [path.isdir(f"{here}/src")],
        "verbosity": 2,
    }
    yield {
        "name": "vcs-import",
        "actions": [
            lambda: _require_repos(),
            f"cd {here} && vcs import src < {REPOS_FILE} || true",
            f"bash -lc \"echo 'stamp: {time()}' > {stamps}/.vcs_import.stamp\"",
        ],
        "task_dep": ["workspace:mkdir-src", "workspace:mkdir-stamp", "tools:apt"],
        "targets": [f"{stamps}/.vcs_import.stamp"],
        "verbosity": 2,
        "clean": True,
    }
    yield {
        "name": "vcs-pull",
        "actions": [
            f"cd {here} && vcs pull src || true",
            f"bash -lc \"echo 'stamp: {time()}' > {stamps}/.vcs_pull.stamp\"",
        ],
        "task_dep": ["workspace:vcs-import"],
        "targets": [f"{stamps}/.vcs_pull.stamp"],
        "verbosity": 2,
        "clean": True,
    }


def task_python_venv():
    """Create and prep Python venv (enabled on Jazzy by default)."""
    yield {"name": None, "actions": None, "doc": "Creates python venv if 'venv=y'."}
    yield {
        "name": "install-venv-tools",
        "actions": [
            f"{ros_src_cmd}sudo apt install -y python3-venv python3-virtualenv python3-wheel"
        ],
        "uptodate": [rf"{ros_src_cmd}virtualenv --help"],
        "verbosity": 2,
    }
    yield {
        "name": "create-venv",
        "actions": [
            rf"{ros_src_cmd}python3 -m venv --system-site-packages {here}/venv && touch {VENV_READY_TRG}",
            rf"{env_src_cmd}python3 -m pip install --upgrade pip wheel",
        ],
        "uptodate": [path.isfile(VENV_READY_TRG)] if use_venv else [True],
        "targets": [VENV_READY_TRG] if use_venv else [],
        "task_dep": ["python_venv:install-venv-tools"] if use_venv else [],
        "clean": remove_dir([f"{here}/venv"]),
        "verbosity": 2,
    }


def task_pydep():
    """Install Python deps from ./requirements.txt (uses venv if enabled)."""
    tar = f"{stamps}/.doit_pydep.stamp"

    def _check_req():
        if not path.isfile(REQ_FILE):
            raise RuntimeError(f"requirements.txt not found at {REQ_FILE}")

    return {
        "actions": [
            _check_req,
            Interactive(
                f"""{env_src_cmd}{pip_low_mem}python3 -m pip install {pip_args} -r "{REQ_FILE}" """
            ),
            f"bash -lc \"echo 'stamp: {time()}' > {tar}\"",
        ],
        "file_dep": is_pip_usable if use_venv else [],
        "targets": [tar],
        "clean": True,
        "verbosity": 2,
        "doc": "Install python dependencies from the workspace root requirements.txt",
    }


def task_rosdep():
    """Install ROS package dependencies for everything in src/."""
    check = f"{ros_src_cmd}rosdep check --from-paths src --ignore-src -r"

    missing_rosdep = ["libmatio-dev", "liburdfdom-dev"]
    missing_specific = (
        [
            "libgz-sim8",
            "libgz-transport13",
            "libgz-msgs10",
            "ros-jazzy-ros-gz",
            "ros-jazzy-gz-ros2-control",
        ]
        if ros == "jazzy"
        else []
    )
    missing_rosdep += missing_specific

    yield {"name": None, "actions": None, "doc": "rosdep init/update/install"}

    yield {
        "name": "available",
        "actions": [f"{ros_src_cmd}sudo apt-get install -y python3-rosdep"],
        "uptodate": [rf"{ros_src_cmd}rosdep --help"],
        "verbosity": 2,
    }

    if ros == "jazzy":
        gazebo_list = "/etc/apt/sources.list.d/gazebo-stable.list"
        yield {
            "name": "gazebo_repo",
            "actions": [
                Interactive(
                    r"""sudo sh -c 'echo "deb http://packages.osrfoundation.org/gazebo/ubuntu-stable $(lsb_release -cs) main" > /etc/apt/sources.list.d/gazebo-stable.list'"""
                ),
                Interactive(
                    "wget -qO - http://packages.osrfoundation.org/gazebo.key | sudo apt-key add -"
                ),
                Interactive("sudo apt-get update"),
            ],
            "uptodate": [path.exists(gazebo_list)],
            "verbosity": 2,
            "doc": "Adds OSRF Gazebo apt repository for gz* packages (Jazzy).",
            "task_dep": ["rosdep:available"],
        }

    yield {
        "name": "init",
        "actions": [Interactive(f"{ros_src_cmd}sudo rosdep init || true")],
        "verbosity": 2,
        "uptodate": [path.exists("/etc/ros/rosdep/sources.list.d")],
        "task_dep": ["rosdep:available"],
    }

    for apt_pkg in missing_rosdep:
        deps = ["rosdep:available"]
        if ros == "jazzy":
            deps.append("rosdep:gazebo_repo")
        yield {
            "name": apt_pkg,
            "actions": [f"{ros_src_cmd}sudo apt install -y {apt_pkg}"],
            "verbosity": 2,
            "uptodate": [f"dpkg -s {apt_pkg}"],
            "task_dep": deps,
        }

    yield {
        "name": "update",
        "actions": [f"{ros_src_cmd}rosdep update --rosdistro {ros}"],
        "verbosity": 2,
        "task_dep": ["rosdep:init"],
        "uptodate": [check],
    }

    yield {
        "name": "install",
        "actions": [
            f"{ros_src_cmd}rosdep install --from-paths src --ignore-src -r -y",
            f"bash -lc \"echo 'stamp: {time()}' > {stamps}/.doit_rosdep.stamp\"",
        ],
        "uptodate": [check],
        "task_dep": ["rosdep:update"]
        + [f"rosdep:{apt_pkg}" for apt_pkg in missing_rosdep],
        "targets": [f"{stamps}/.doit_rosdep.stamp"],
        "verbosity": 2,
    }


def task_build():
    """Per-package colcon builds + umbrella target."""
    yield {
        "name": None,
        "actions": None,
        "targets": [f"{here}/install/setup.sh"],
        "file_dep": [t for pkg in src_pkg.values() for t in pkg.targets],
        "uptodate": [
            check_timestamp_unchanged(t)
            for pkg in src_pkg.values()
            for t in pkg.targets
        ],
        "clean": remove_dir(["install", "log", "build"]),
        "doc": "Colcon builds packages. Uses symlink if cli_arg has 'syml=y'",
    }

    for name, pkg in src_pkg.items():
        # build each package incrementally
        cmd = (
            f"{env_src_cmd}{ros_src_cmd}"
            f"python3 -m colcon build --packages-select {name} {colcon_args} && "
            f"mkdir -p {here}/build/{name} && "
            f"bash -lc \"echo 'build time: {time()}' > {here}/build/{name}/doit.stamp\""
        )

        raw_task = {
            "name": f"{pkg.name}",
            "actions": [cmd],
            "targets": pkg.targets,
            "file_dep": list(pkg.build_dep) + [f"{stamps}/.doit_rosdep.stamp"],
            "task_dep": ["rosdep"],
            "clean": pkg.cleans,
            "verbosity": 2,
        }
        if not raw_task["file_dep"]:
            del raw_task["file_dep"]
        yield raw_task


def task_setup():
    """All tasks."""
    return {
        "actions": None,
        "task_dep": [
            "tools:apt",
            "workspace:vcs-import",
            "workspace:vcs-pull",
            "python_venv:create-venv",
            "pydep",
            "rosdep:install",
            "build",
        ],
        "doc": "End-to-end setup & build.",
    }


def task_download():
    return {
        "actions": None,
        "task_dep": [
            "workspace:vcs-import",
            "workspace:vcs-pull",
        ],
    }

# Tron Artefacts Workspace

A demo project using the **Limx Tron1 Robot** with **Artefacts**, **ROS 2**, and **Gazebo**.

---

## Overview

This workspace provides a Tron1 simulation and development environment using a standard ROS 2 workflow.

It supports both **ROS 2 Humble** (Ubuntu 22.04) and **ROS 2 Jazzy** (Ubuntu 24.04):

- **Humble**: Uses **Ignition Fortress**
- **Jazzy**: Uses **Gazebo Harmonic**

---

## 1. Prerequisites

### Install ROS 2

Follow the official installation guide for your Ubuntu version:

- [ROS 2 Jazzy on Ubuntu 24.04](https://docs.ros.org/en/jazzy/Installation/Ubuntu-Install-Debs.html)
- [ROS 2 Humble on Ubuntu 22.04](https://docs.ros.org/en/humble/Installation/Ubuntu-Install-Debs.html)

Install the `ros-{ROS_DISTRO}-desktop` package.

### Install tools

```bash
sudo apt update
sudo apt install python3-pip python3-vcstool python3-colcon-common-extensions python3-rosdep git
```

---

## 2. Setup

### Clone this repository

```bash
git clone https://github.com/art-e-fact/tron1-artefacts.git
cd tron1-artefacts
```

### Import dependencies

```bash
# For Jazzy:
mkdir src && vcs import src < jazzy.repos
# For Humble:
mkdir src && vcs import src < humble.repos
```

### Create Python virtual environment

```bash
python3 -m venv --system-site-packages venv
source venv/bin/activate
pip install --upgrade pip && pip install -r requirements.txt
```

### Install ROS dependencies
(Replace `.bash` with the shell you are using (e.g. `.zsh`))
```bash
source /opt/ros/$ROS_DISTRO/setup.bash
sudo rosdep init  # Only required when using rosdep for the first time
rosdep update
rosdep install --from-paths src --ignore-src -y
```

### Build
(Replace `.bash` with the shell you are using (e.g. `.zsh`))
```bash
source venv/bin/activate
source /opt/ros/$ROS_DISTRO/setup.bash
colcon build --symlink-install
```

---

##  3. Usage

* You will need three sessions to run a full simulation: 1. The RL Controller, 2. The simulation, and 3. The custom controller

1. Run the RL Controller:  Do this before the simulation, if you want the robot to start walking, or else it will fall:
  ```bash
  export ROBOT_TYPE=PF_TRON1A # Set the robot model type (only PF_TRON1A compatible with artefacts)
  export RL_TYPE=isaacgym # or isaaclab
  source venv/bin/activate
  python3 src/rl-deploy-python/main.py
  ```

2. Run the Simulation
  ```bash
  export ROBOT_TYPE=PF_TRON1A
  source venv/bin/activate
  source install/setup.bash # or e.g. .zsh
  ros2 launch pointfoot_gazebo empty_world.launch.py server:=false # or true to run headlessly 
  ```

3. Run the custom controller to move the robot:

  ```bash
  export ROBOT_TYPE=PF_TRON1A
  source venv/bin/activate
  source install/setup.bash
  python3 src/limxsdk_python/limxsdk_python/api/goto.py
  ```

## 4. Testing
NOTE: Do not manually launch any processes before running the test.
The test script will automatically collect and launch all necessary components.
Please ensure that any other active processes (simulators or controllers) are fully terminated beforehand.


- Test with Artefacts:

  Three tests have been provided for you to try out:
    1. move_around
    2. policy_test
    3. policy_drift

  See the `artefacts.yaml` in the root of this repository file for details

  ```bash
  source venv/bin/activate
  source install/setup.bash
  artefacts run test_policy
  ```

- Test with Pytest:

  ```bash
  source venv/bin/activate
  source install/setup.bash
  python3 -m pytest test/test_move.py -v -x
  ```

## Notes

- Use `vcs status src` to check repo status across all dependencies.
- Use `vcs pull src` to update dependent repos
- `rm -rf build install log` followed by `colcon build --symlink-install` for a clean rebuild
- a clean rebuild can be done with `rm -rf build install log` followed by `colcon build --symlink-install`

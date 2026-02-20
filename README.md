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
git clone https://github.com/art-e-fact/tron1-artefacts.git ~/tron_artefacts_ws
cd ~/tron_artefacts_ws
```

### Import dependencies

```bash
# For Jazzy:
vcs import src < jazzy.repos

# For Humble:
vcs import src < humble.repos
```

### Create Python virtual environment

```bash
python3 -m venv --system-site-packages venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### Install ROS dependencies

```bash
source /opt/ros/$ROS_DISTRO/setup.bash
sudo rosdep init  # only needed once
rosdep update
rosdep install --from-paths src --ignore-src -y
```

### Build

```bash
source venv/bin/activate
source /opt/ros/$ROS_DISTRO/setup.bash
colcon build --symlink-install
```


---

##  3. Usage

- Select robot type
  - Taking PF_TRON1A (the only one compatible with Artefacts now) as an example, set the robot model type:

    ```bash
    echo 'export ROBOT_TYPE=PF_TRON1A' >> ~/.bashrc && source ~/.bashrc
    ```

Before running anything, do not forget to source your virtual environment and ROS installation.

- Run the RL controller: Do this before the simulation, if you want the robot to start walking, or else it will fall:

  - Select the trained policy: Set the RL_TYPE environmental variable to isaacgym or isaaclab:

    ```bash
    export RL_TYPE=isaacgym
    source ~/tron_artefacts_ws/venv/bin/activate
    python3 ~/tron_artefacts_ws/src/rl-deploy-python/main.py
    ```

- Run the simulation: You can run the server (no GUI) instead by passing server:=true param:

  ```bash
  source ~/tron_artefacts_ws/install/setup.bash
  ros2 launch pointfoot_gazebo empty_world.launch.py server:=false
  ```

- Run the custom controller to move the robot:

  ```bash
  source ~/tron_artefacts_ws/venv/bin/activate
  python3 ~/tron_artefacts_ws/src/limxsdk_python/limxsdk_python/api/goto.py
  ```
## 4. Testing
NOTE: Do not manually launch any processes before running the test.
The test script will automatically collect and launch all necessary components.
Please ensure that any other active processes (simulators or controllers) are fully terminated beforehand.

- Test with Artefacts:

  ```bash
  source ~/tron_artefacts_ws/venv/bin/activate
  source ~/tron_artefacts_ws/install/setup.bash
  artefacts run move_around
  ```

- Test with Pytest:

  ```bash
  source ~/tron_artefacts_ws/venv/bin/activate
  source ~/tron_artefacts_ws/install/setup.bash
  python3 -m pytest ~/tron_artefacts_ws/test/test_move.py -v -x
  ```

## Notes

- Use `vcs status src` to check repo status across all dependencies.
- Use `vcs pull src` to update dependent repos
- `rm -rf build install log` followed by `colcon build --symlink-install` for a clean rebuild

### Clean rebuild

```bash
rm -rf build install log
colcon build --symlink-install
```

# Tron Artefacts Workspace

A demo project using the **Limx Tron1 Robot** with **Artefacts**, **ROS 2**, and **Gazebo**.

---

## Overview

This workspace serves as a **unified installer** for the Tron1 simulation and development environment.
It automates everything, from dependency installation and virtual environment setup, to pulling repositories and building the entire ROS 2 workspace, using a single command interface powered by [`doit`](https://pydoit.org/).
It supports both **ROS 2 Humble** and **ROS 2 Jazzy**, automatically detecting your installed distribution and configuring everything accordingly:

- **Humble**: Installs and configures **Ignition Fortress**
- **Jazzy**: Installs and configures **Gazebo Harmonic**

This allows the same installer to seamlessly handle both ecosystems with no manual changes required.


---

## 1. Set Up the Development Environment

### Install ROS 2 Jazzy or Humble
For installation, please follow the official guides below and select **`ros-{ROS_DISTRO}-desktop`**:

[ROS 2 Jazzy Installation on Ubuntu 24.04](https://docs.ros.org/en/jazzy/Installation/Ubuntu-Install-Debs.html)
[ROS 2 Humble Installation on Ubuntu 22.04](https://docs.ros.org/en/humble/Installation/Ubuntu-Install-Debs.html)

### Install fundamental dependencies
```bash
sudo apt-get update
sudo apt-get upgrade
sudo apt install python3-pip python3-doit git
```

###  Clone the repository (preferably into ~/tron_artefacts_ws)
```bash
git clone https://github.com/art-e-fact/tron1-artefacts.git ~/tron_artefacts_ws
cd ~/tron_artefacts_ws
doit tabcompletion > bash_completion_doit.bash
source bash_completion_doit.bash
```

---

## 2. Using the Unified Installer

Once ROS 2 and system prerequisites are installed, this workspace manages everything else through `doit` tasks.

### Initial setup
```bash
cd ~/tron_artefacts_ws
doit setup
```
> Installs dependencies, creates the virtual environment, and sets up ROS 2 packages.


### Build the workspace
```bash
cd ~/tron_artefacts_ws
doit build
```
> Builds all packages in the workspace using `colcon`.


### Update repositories
```bash
cd ~/tron_artefacts_ws
doit download
```
> Pulls, fetches, and updates all repositories.


### Full rebuild cycle
```bash
cd ~/tron_artefacts_ws
doit clean
doit setup
doit build
```
> Refreshes repositories and rebuilds everything from scratch.

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
  ros2 launch pointfoot_gazebo gazebo.launch.py server:=false
  ```

- Run the custom controller to move the robot:

  ```bash
  source ~/tron_artefacts_ws/venv/bin/activate
  python3 ~/tron_artefacts_ws/src/limxsdk_python/limxsdk_python/api/goto.py
  ```
## 4. Testing

### Local

NOTE: Do not manually launch any processes before running the test.
The test script will automatically collect and launch all necessary components.
Please ensure that any other active processes (simulators or controllers) are fully terminated beforehand.

- Test with Artefacts:

  Before running any experiments, activate the virtual environment and source the workspace:

  ```bash
  source ~/tron_artefacts_ws/venv/bin/activate
  source ~/tron_artefacts_ws/install/setup.bash
  ```

  - Relative motion execution test:

    ```bash
    artefacts run move_around
    ```

  - Relative command policy comparison:

    ```bash
    artefacts run policy_test
    ```

  - Idle drift evaluation:

    ```bash
    artefacts run policy_drift
    ```

- Test with Pytest:

  ```bash
  source ~/tron_artefacts_ws/venv/bin/activate
  source ~/tron_artefacts_ws/install/setup.bash
  python3 -m pytest ~/tron_artefacts_ws/test/test_move.py -v -x
  ```

### Containerized (Docker)

The tests can be ran with artefacts in a container, either locally, or on the artefacts platform.

1. Locally (`--in-container`)

Note: Requires a gpu that is available to Docker.

```
# "policy_test" can be changed for any of the other tests (e.g policy_drift)
artefacts run --in-container policy_test --gpus=all
```

2. On the artefacts platform (`run-remote`)

```
# "policy_test" can be changed for any of the other tests (e.g policy_drift)
artefacts run-remote policy_test
```
## Notes

- Use `doit list` to see all available commands.

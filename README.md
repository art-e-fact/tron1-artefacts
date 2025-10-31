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
  - List available robot types via the Shell command tree -L 1 src/robot-description/pointfoot:

    ```
    src/robot-description/pointfoot
    ├── PF_P441A
    ├── PF_P441B
    ├── PF_P441C
    ├── PF_P441C2
    ├── PF_TRON1A
    ├── SF_TRON1A
    └── WF_TRON1A
    ```

  - Taking PF_TRON1A (please replace it according to the actual robot type) as an example, set the robot model type:

    ```bash
    echo 'export ROBOT_TYPE=PF_TRON1A' >> ~/.bashrc && source ~/.bashrc
    ```
- Select the trained policy:

Set the RL_TYPE environmental variable to isaacgym or isaaclab:

```bash
echo 'export RL_TYPE=isaacgym' >> ~/.bashrc && source ~/.bashrc
```
- Run the RL controller: Do this before the simulation, if you want the robot to start walking, or else it will fall:

  ```bash
  . ~/tron_artefacts_ws/SOURCE.bash
  python3 ~/tron_artefacts_ws/src/rl-deploy-python/main.py
  ```

- Run the simulation: You can run the server (no GUI) instead by passing server:=true param:

  ```bash
  . ~/tron_artefacts_ws/SOURCE.bash
  ros2 launch pointfoot_gazebo empty_world.launch.py server:=false
  ```

- Run the custom controller to move the robot:

  ```bash
  . ~/tron_artefacts_ws/SOURCE.bash
  python3 ~/tron_artefacts_ws/src/limxsdk_python/limxsdk_python/api/goto.py
  ```
## 4. Testing
NOTE: Do not manually launch any processes before running the test.
The test script will automatically collect and launch all necessary components.
Please ensure that any other active processes (simulators or controllers) are fully terminated beforehand.

- Test with Artefacts:

  ```bash
  . ~/tron_artefacts_ws/SOURCE.bash
  artefacts run move_around
  ```

- Test with Pytest:

  ```bash
  bash TEST.bash
  ```

## Notes

- Use `doit list` to see all available commands.

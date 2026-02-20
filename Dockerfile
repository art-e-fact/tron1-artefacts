FROM public.ecr.aws/artefacts/ros2:jazzy-harmonic-gpu-0.12.0

ENV ROBOT_TYPE=PF_TRON1A
ENV RMW_IMPLEMENTATION=rmw_cyclonedds_cpp

SHELL ["/bin/bash", "-lc"]

WORKDIR /ws

COPY requirements.txt artefacts.yaml /ws/
COPY test/ /ws/test/

# Dependent packages
RUN mkdir -p /ws/src && \
    git clone --depth 1 -b main https://github.com/art-e-fact/tron1-artefacts-pythonsdk.git /ws/src/limxsdk_python && \
    git clone --depth 1 -b main https://github.com/art-e-fact/tron1-artefacts-description.git /ws/src/robot-description && \
    git clone --depth 1 -b master https://github.com/limxdynamics/robot-visualization.git /ws/src/robot-visualization && \
    git clone --depth 1 -b main https://github.com/art-e-fact/tron1-artefacts-sim.git /ws/src/robot-gazebo && \
    git clone --depth 1 -b main https://github.com/art-e-fact/tron1-rl-deploy-artefacts.git /ws/src/rl-deploy-python && \
    git clone --depth 1 -b main https://github.com/limxdynamics/robot-joystick.git /ws/src/robot-joystick

RUN apt update -y && \
    apt install -y --no-install-recommends \
      ros-jazzy-rmw-cyclonedds-cpp \
      ros-jazzy-rmw-zenoh-cpp

RUN python3 -m pip install --upgrade pip && \
    python3 -m pip install -r /ws/requirements.txt

RUN source /opt/ros/jazzy/setup.bash && \
    rosdep update && \
    rosdep install --from-paths src --ignore-src -r -y

RUN rm -rf /var/lib/apt/lists/*

RUN source /opt/ros/jazzy/setup.bash && \
    MAKEFLAGS="-j1 -l1" colcon build --symlink-install --executor sequential

CMD source /ws/install/setup.bash && artefacts run $ARTEFACTS_JOB_NAME

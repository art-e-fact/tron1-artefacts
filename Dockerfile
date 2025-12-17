FROM public.ecr.aws/artefacts/ros2:jazzy-harmonic-gpu-0.9.9

ENV ROBOT_TYPE=PF_TRON1A
ENV RMW_IMPLEMENTATION=rmw_cyclonedds_cpp

SHELL ["/bin/bash", "-lc"]

COPY . /ws
WORKDIR /ws

RUN apt update -y && \
    apt install -y --no-install-recommends \
      ros-jazzy-rmw-cyclonedds-cpp \
      ros-jazzy-rmw-zenoh-cpp

RUN python3 -m pip install --upgrade pip && \
    python3 -m pip install -r /ws/requirements.txt && \
    python3 -m pip install --upgrade artefacts-cli

RUN source /opt/ros/jazzy/setup.bash && \
    rosdep update && \
    rosdep install --from-paths src --ignore-src -r -y

RUN rm -rf /var/lib/apt/lists/*

RUN source /opt/ros/jazzy/setup.bash && \
    MAKEFLAGS="-j1 -l1" colcon build --symlink-install --executor sequential

CMD source /ws/install/setup.bash && artefacts run $ARTEFACTS_JOB_NAME

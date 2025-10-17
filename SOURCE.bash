SCRIPT_DIR="$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")"

source /opt/ros/jazzy/setup.bash
source $SCRIPT_DIR/install/setup.bash
source $SCRIPT_DIR/venv/bin/activate
export RCUTILS_COLORIZED_OUTPUT=1

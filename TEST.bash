#!/bin/bash
SCRIPT_DIR="$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")"
source $SCRIPT_DIR/SOURCE.bash
set -e -o pipefail

python -m pytest ./test/test_move.py \
    -v \
    -x \

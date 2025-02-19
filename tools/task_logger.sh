#!/bin/bash

# ANSI color codes
RED="\033[0;31m"
GREEN="\033[0;32m"
YELLOW="\033[1;33m"
BLUE="\033[1;34m"
CYAN="\033[0;36m"
NC="\033[0m" # No Color

export PS4="${CYAN}+ ${NC}"

function log_entry() {
    echo -e "$1"
}

function log_group_start() {
    echo -e "${BLUE}======================= Start of '$1' =======================${NC}"
    set -x
}

function log_group_end() {
    set +x
    echo -e "${BLUE}======================= End of '$1' =======================${NC}\n"
}

function reset() {
    set +x
    export PS4="+"
}

#!/bin/bash

# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# ==============================================================================
#
# == Description ==
#
# This script acts as a wrapper to run a specified command. If the command
# exits with a non-zero status (indicating failure), the script will wait
# for a calculated period and then retry the command.
#
# The delay between retries increases exponentially to avoid overwhelming
# a failing service (e.g., a database, web API) that might be
# temporarily unavailable.
#
# == Backoff Logic ==
#
# The delay is calculated using the formula:
#   DELAY = BASE_DELAY * (2 ^ (current_attempt_number - 1))
#
# With default settings (BASE_DELAY=60s, ATTEMPTS=3):
#   - Attempt 1 fails: Waits 60 * (2^0) = 60 seconds
#   - Attempt 2 fails: Waits 60 * (2^1) = 120 seconds
#   - Attempt 3 fails: Script gives up and exits with the command's final error code.
#
# == Usage ==
#
#   ./backoff_retry.sh -c "<command_to_run>" [-a <num_attempts>] [-d <base_delay_sec>]
#
# == Options ==
#
#   -c, --command      The command string to execute (required).
#                      **Must be quoted** if it contains spaces, pipes, or
#                      other special characters.
#
#   -a, --attempts     The total number of times to try the command.
#                      Must be a positive integer. (Default: 3)
#
#   -d, --base-delay   The initial delay in seconds before the first retry.
#                      Must be a non-negative integer. (Default: 60)
#
#   -h, --help         Show this help message and exit.
#
# == Examples ==
#
# 1. Run a simple 'false' command (will fail 3 times by default):
#    ./backoff_retry.sh -c "false"
#
# 2. Attempt to curl a potentially flaky API 5 times, starting with a 10s delay:
#    ./backoff_retry.sh -c "curl -f http://localhost/status" -a 5 -d 10
#
# 3. Run a complex command with pipes and ensure it's properly quoted:
#    ./backoff_retry.sh -c "ps aux | grep 'xpk' | grep -v 'grep'"
#
# ==============================================================================

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m'

usage() {
    echo -e "Usage: $0 -c \"<command>\" [-a <attempts>] [-d <base_delay>]" >&2
    echo -e "\nOptions:" >&2
    echo -e "  -c, --command      The command string to execute (required)." >&2
    echo -e "  -a, --attempts     Number of attempts (default: 3)." >&2
    echo -e "  -d, --base-delay   Base delay in seconds for backoff (default: 60)." >&2
    echo -e "  -h, --help         Show this help message." >&2
}

ATTEMPTS=3
BASE_DELAY=60
COMMAND_STRING=""

if [ "$#" -eq 0 ]; then
    echo -e "${RED}Error: No arguments provided.${NC}" >&2
    usage
    exit 1
fi

while [[ "$#" -gt 0 ]]; do
    case "$1" in
        -c|--command)
            if [[ -n "$2" && ! "$2" =~ ^- ]]; then
                COMMAND_STRING="$2"
                shift 2
            else
                echo -e "${RED}Error: --command requires an argument.${NC}" >&2
                usage
                exit 1
            fi
            ;;
        -a|--attempts)
            if [[ -n "$2" && ! "$2" =~ ^- ]]; then
                ATTEMPTS="$2"
                shift 2
            else
                echo -e "${RED}Error: --attempts requires an argument.${NC}" >&2
                usage
                exit 1
            fi
            ;;
        -d|--base-delay)
            if [[ -n "$2" && ! "$2" =~ ^- ]]; then
                BASE_DELAY="$2"
                shift 2
            else
                echo -e "${RED}Error: --base-delay requires an argument.${NC}" >&2
                usage
                exit 1
            fi
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo -e "${RED}Error: Unknown option: $1${NC}" >&2
            usage
            exit 1
            ;;
    esac
done

if [[ -z "$COMMAND_STRING" ]]; then
    echo -e "${RED}Error: You must provide a command string with -c or --command.${NC}" >&2
    usage
    exit 1
fi

if ! [[ "$ATTEMPTS" =~ ^[1-9][0-9]*$ ]]; then
    echo -e "${RED}Error: ATTEMPTS (-a) must be a positive integer.${NC}" >&2
    exit 1
fi

if ! [[ "$BASE_DELAY" =~ ^[0-9]+$ ]]; then
    echo -e "${RED}Error: BASE_DELAY (-d) must be a non-negative integer.${NC}" >&2
    exit 1
fi

for (( i=1; i<=ATTEMPTS; i++ )); do
    echo -e "${YELLOW}--- Attempt $i of $ATTEMPTS ---${NC}"
    
    /bin/bash -c "$COMMAND_STRING"

    EXIT_CODE=$?

    if [ $EXIT_CODE -eq 0 ]; then
        echo -e "${GREEN}Command succeeded on attempt $i. Exiting.${NC}"
        exit 0
    fi

    if [ $i -eq $ATTEMPTS ]; then
        echo -e "${RED}Command failed after $ATTEMPTS attempts. Exiting with status $EXIT_CODE.${NC}"
        exit $EXIT_CODE
    fi


    DELAY=$(( BASE_DELAY * (2 ** (i - 1)) ))

    echo -e "${YELLOW}Command failed with status $EXIT_CODE. Waiting for $DELAY seconds before next attempt...${NC}"
    
    sleep "$DELAY"
done

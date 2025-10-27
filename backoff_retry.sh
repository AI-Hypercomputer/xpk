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

#==============================================================================
#
# SCRIPT: backoff_retry.sh
#
# DESCRIPTION: Executes a given command string and retries it with an
#              exponential backoff strategy if it fails.
#
#              The script will attempt to run the command up to a specified
#              number of times. If the command fails, it will wait for a
#              calculated delay before retrying. The delay doubles after
#              each subsequent failure.
#
# USAGE:
#   ./backoff_retry.sh "<command>"
#
#   Example (default 3 attempts, 60s base delay):
#   ./backoff_retry.sh "curl -f http://my-service.local/health"
#
#   Example (custom settings via environment variables):
#   ATTEMPTS=5 BASE_DELAY=10 ./backoff_retry.sh "./my_flaky_script.py --init"
#
# ARGUMENTS:
#   $1 (Required): The command string to execute. This string *must* be
#                  quoted if it contains spaces, pipes, or other special
#                  shell characters.
#
# ENVIRONMENT VARIABLES:
#   ATTEMPTS:     The total number of times to try the command.
#                 (Default: 3)
#
#   BASE_DELAY:   The initial wait time (in seconds) used before the *first*
#                 retry (i.e., after the first failure). The delay is
#                 calculated as: (BASE_DELAY * 2^(attempt_number - 1))
#                 (Default: 60)
#
#                 Delay progression (for default BASE_DELAY=60):
#                 - After fail 1: 60s  (60 * 2^0)
#                 - After fail 2: 120s (60 * 2^1)
#                 - After fail 3: 240s (60 * 2^2)
#                 - ...etc.
#
# EXIT CODES:
#   0: The command succeeded (exited with 0) on one of the attempts.
#   1: Script usage error (e.g., no command provided, invalid ATTEMPTS).
#   <other>: If the command fails on all attempts, this script will exit
#            with the *last exit code* provided by the failed command.
#
#==============================================================================

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m'

if [ "$#" -ne 1 ]; then
  echo -e "${RED}Correct usage: backoff_retry.sh \"<command>\"${NC}"
  exit 1
fi

ATTEMPTS="${ATTEMPTS:-3}"
BASE_DELAY="${BASE_DELAY:-60}"
COMMAND_STRING="$1"

if [[ -z "$COMMAND_STRING" ]]; then
    echo -e "${RED}Error: You must provide a command string as the first argument.${NC}" >&2
    exit 1
fi

if ! [[ "$ATTEMPTS" =~ ^[0-9]+$ ]]; then
    echo -e "${RED}Error: ATTEMPTS environment variable must be a positive integer.${NC}" >&2
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

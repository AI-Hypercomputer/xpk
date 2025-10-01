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
# Golden Buddy - Golden File Management Script
#
# This script automates the process of managing "golden files," which are
# baseline output files used for regression testing. It can operate in two
# modes: 'update' or 'verify'.
#
# It reads a YAML configuration file specifying a set of commands, executes
# each command, and stores its stdout/stderr output in a corresponding
# file within a specified directory.
#
# Dependencies:
#   - yq: For parsing the YAML goldens file.
#   - git: For diffing and managing file state during verification.
#
# Usage:
#   ./golden_buddy.sh <mode> <goldens file> <goldens directory>
#
# Arguments:
#   <mode>:
#     - "update": Runs all commands from the <goldens file> and overwrites
#                 the corresponding output files in <goldens directory>.
#                 This is used to establish a new baseline (e.g., after
#                 making intentional changes).
#     - "verify": Runs all commands and compares their output against the
#                 existing files in <goldens directory> using 'git diff'.
#                 If any differences are found, it prints the diff, exits
#                 with status 1, and suggests the 'update' command.
#                 This is used in CI/testing to ensure outputs haven't
#                 changed unexpectedly.
#
#   <goldens file>:
#     Path to the YAML file defining the golden tests. The file should
#     have a top-level key 'goldens', which is an object where each key
#     is a test name and its value is an object containing a 'command' string.
#
#     Example 'goldens.yaml':
#     goldens:
#       test_case_1:
#         command: "echo 'Hello World'"
#       list_files:
#         command: "ls -la"
#
#   <goldens directory>:
#     Path to the directory where the output files (the "goldens")
#     will be stored. The script will create this directory if it
#     doesn't exist. Output filenames are derived from the test keys
#     in the YAML file (with spaces replaced by underscores).
#
# Exit Codes:
#   - 0: Success (Goldens updated successfully in 'update' mode, or
#          no diffs found in 'verify' mode).
#   - 1: General error (e.g., wrong arguments, unsupported mode) OR
#        Diffs found during 'verify' mode.
# ==============================================================================

if [ "$#" -ne 3 ]; then
  echo "Correct usage: golden_buddy.sh <update/verify> <goldens file> <goldens directory>" >&2
  exit 1
fi

MODE=$1
GOLDENS_FILE=$2
GOLDENS_DIR=$3
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m'

if ! command -v yq &> /dev/null; then
  echo -e "${RED}Error: 'yq' command not found. Please install yq to continue.${NC}" >&2
  exit 1
fi

if [[ "$MODE" != "update" && "$MODE" != "verify" ]]; then
  echo "Error: Unsupported mode '$MODE'. Must be 'update' or 'verify'." >&2
  exit 1
fi

mkdir -p "$GOLDENS_DIR"

has_diffs=false
while read -r key; do
  command=$(yq -r '.goldens["'"$key"'"].command' "$GOLDENS_FILE")
  if [[ "$MODE" = "update" ]]; then
    printf "${YELLOW}Updating: %s...${NC} " "$key"
  fi
  if [[ "$MODE" = "verify" ]]; then
    printf "${YELLOW}Evaluating: %s...${NC} " "$key"
  fi

  REFERENCE_FILE="$GOLDENS_DIR/${key// /_}.txt"
  echo "\$ $command" > $REFERENCE_FILE
  eval "$command" >> $REFERENCE_FILE 2>&1
  if [[ "$MODE" = "update" ]]; then
    printf "${GREEN}DONE${NC}\n"
  fi
  
  if [[ "$MODE" = "verify" ]]; then
    git add $REFERENCE_FILE
    
    DIFF_OUTPUT=$(git diff --color=always HEAD -- $REFERENCE_FILE | cat)
    
    git reset HEAD -- $REFERENCE_FILE &> /dev/null
    git restore $REFERENCE_FILE &> /dev/null
    git clean -fd -- $REFERENCE_FILE &> /dev/null

    if [[ -n "$DIFF_OUTPUT" ]]; then
      printf "${RED}FAIL${NC}\n"

      has_diffs=true
      echo "\$ $command" $REFERENCE_FILE
      printf "%s\n" "$DIFF_OUTPUT" >&2
    else
      printf "${GREEN}OK${NC}\n"
    fi
  fi
done < <(yq -r '.goldens | keys[]' "$GOLDENS_FILE")

if [[ "$MODE" = "verify" ]]; then
  if [[ "$has_diffs" == true ]]; then
    printf "${RED}Golden diffs found! Please use the following command to regenerate goldens:${NC}\n" >&2
    printf "${YELLOW}\n\t%s${NC}\n\n" "${UPDATE_GOLDEN_COMMAND:-"golden_buddy.sh update $GOLDENS_FILE $GOLDENS_DIR"}" >&2
    exit 1
  else
    printf "${GREEN}All goldens up to date!${NC}\n"
    exit 0
  fi
fi

if [[ "$MODE" = "update" ]]; then
  printf "${GREEN}Goldens updated!${NC}\n"
  exit 0
fi

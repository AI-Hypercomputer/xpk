#!/bin/bash

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

if [[ "$MODE" != "update" && "$MODE" != "verify" ]]; then
  echo "Error: Unsupported mode '$MODE'. Must be 'update' or 'verify'." >&2
  exit 1
fi

mkdir -p "$GOLDENS_DIR"

cat "$GOLDENS_FILE" | yq -r '.goldens | to_entries[] | [.key, .value.command] | @tsv' | \
  while IFS=$'\t' read -r key command; do
    if [[ "$MODE" = "update" ]]; then
      printf "${YELLOW}Updating: %s${NC}\n" "$key"
    fi
    if [[ "$MODE" = "verify" ]]; then
      printf "${YELLOW}Evaluating: %s${NC}\n" "$key"
    fi
    eval "$command" > "$GOLDENS_DIR/${key// /_}.txt" 2>&1
done

if [[ "$MODE" = "verify" ]]; then
  git add "$GOLDENS_DIR"
  DIFF_OUTPUT=$(git diff HEAD -- "$GOLDENS_DIR" | cat)

  git reset HEAD -- "$GOLDENS_DIR" &> /dev/null
  git restore "$GOLDENS_DIR" &> /dev/null
  git clean -fd -- "$GOLDENS_DIR" &> /dev/null

  if [[ -n "$DIFF_OUTPUT" ]]; then
    printf "%s\n" "$DIFF_OUTPUT" >&2

    echo "" >&2
    
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
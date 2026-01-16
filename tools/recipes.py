#!/usr/bin/env python3

"""
Copyright 2026 Google LLC

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

     https://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

"""
XPK Recipe Executor

This script executes Markdown recipes for XPK. It supports three modes:
- golden: Verifies that the command output matches the golden output in the markdown.
- update: Updates the golden output in the markdown file.
- run: Executes the commands without verification (integration test mode).

Usage:
  python3 tools/recipes.py <mode> <recipe_files>
"""

import difflib
import re
import subprocess
import sys
import dataclasses
from enum import Enum


class Mode(str, Enum):
  GOLDEN = "golden"
  UPDATE = "update"
  RUN = "run"


class Color(str, Enum):
  RED = "\033[0;31m"
  GREEN = "\033[0;32m"
  YELLOW = "\033[0;33m"
  NC = "\033[0m"

  def __str__(self):
    return self.value


@dataclasses.dataclass
class CodeBlock:
  command: str
  expected_output: str | None
  start: int
  end: int


def extract_code_blocks(content: str) -> list[CodeBlock]:
  regex = re.compile(r"```shell\n(.*?)```\n(?:<!--\n(.*?)-->\n?)?", re.DOTALL)
  return [
      CodeBlock(
          command=m.group(1).strip(),
          expected_output=m.group(2),
          start=m.start(),
          end=m.end(),
      )
      for m in regex.finditer(content)
  ]


def build_script(blocks: list[CodeBlock], mode: Mode) -> str:
  script_parts = ["set -e"]

  if mode in [Mode.GOLDEN, Mode.UPDATE]:
    script_parts.append("""
        xpk() {
            command xpk "$@" --dry-run
        }
        export -f xpk
        """)

  for block in blocks:
    safe_command = block.command.replace("'", "'\\''")

    script_parts.append("echo 'XPK_RECIPE_EXECUTOR_BLOCK_START'")
    script_parts.append(f"echo '$ {safe_command}'")
    script_parts.append(f"{block.command}")
    script_parts.append("echo 'XPK_RECIPE_EXECUTOR_BLOCK_END'")

  return "\n".join(script_parts)


def run_script(script: str) -> str:
  return subprocess.run(
      script,
      shell=True,
      executable="/bin/bash",
      stdout=subprocess.PIPE,
      stderr=subprocess.STDOUT,
      text=True,
      check=False,
  ).stdout


def extract_script_outputs(output: str) -> tuple[list[str], bool]:
  results = []
  current_pos = 0

  start_marker = "XPK_RECIPE_EXECUTOR_BLOCK_START"
  end_marker = "XPK_RECIPE_EXECUTOR_BLOCK_END"

  while True:
    start_idx = output.find(start_marker, current_pos)

    if start_idx == -1:
      break

    content_start = start_idx + len(start_marker)
    end_idx = output.find(end_marker, content_start)

    if end_idx == -1:
      content = output[content_start:].strip()
      results.append(content)
      return results, True

    content = output[content_start:end_idx].strip()
    results.append(content)
    current_pos = end_idx + len(end_marker)

  return results, False


def format_block(block: CodeBlock, output: str) -> str:
  """
  Formats a code block with the given output.
  """
  new_block = f"```shell\n{block.command}\n```\n"
  if output:
    new_block += f"<!--\n{output}\n-->\n"
  return new_block


def reconstruct_content(
    content: str, blocks: list[CodeBlock], results: list[str]
) -> str:
  last_pos = 0
  new_content_chunks = []

  for block, actual_output in zip(blocks, results):
    new_content_chunks.append(content[last_pos : block.start])
    new_content_chunks.append(format_block(block, actual_output))
    last_pos = block.end

  new_content_chunks.append(content[last_pos:])
  return "".join(new_content_chunks)


def process_file(filepath: str, mode: Mode):
  with open(filepath, mode="r", encoding="utf-8") as f:
    content = f.read()

  blocks = extract_code_blocks(content)
  if not blocks:
    print(f"{Color.YELLOW}No shell blocks found in {filepath}{Color.NC}")
    return

  full_script = build_script(blocks, mode)

  if mode == Mode.UPDATE:
    print(
        f"{Color.YELLOW}Updating: {filepath}...{Color.NC} ", end="", flush=True
    )
  elif mode == Mode.RUN:
    print(
        f"{Color.YELLOW}Running: {filepath}...{Color.NC} ", end="", flush=True
    )
  elif mode == Mode.GOLDEN:
    print(
        f"{Color.YELLOW}Verifying: {filepath}...{Color.NC} ", end="", flush=True
    )

  output_script_log = run_script(full_script)
  results, failed = extract_script_outputs(output_script_log)

  if mode == Mode.RUN:
    if failed:
      print(f"{Color.RED}FAIL{Color.NC}")
    else:
      print(f"{Color.GREEN}DONE{Color.NC}")
    print("\n".join(results))
    return

  new_content = reconstruct_content(content, blocks, results)

  if mode == Mode.UPDATE:
    with open(filepath, mode="w", encoding="utf-8") as f:
      f.write(new_content)
    print(f"{Color.GREEN}DONE{Color.NC}")

  elif mode == Mode.GOLDEN:
    if content != new_content:
      print(f"{Color.RED}FAIL{Color.NC}")
      diff = difflib.unified_diff(
          content.splitlines(),
          new_content.splitlines(),
          fromfile="Expected",
          tofile="Actual",
      )
      print("\n".join(diff))
    else:
      print(f"{Color.GREEN}OK{Color.NC}")


def main():
  if len(sys.argv) < 3:
    print("Usage: python3 tools/recipes.py <mode> <files...>")
    return

  try:
    mode = Mode(sys.argv[1])
  except ValueError:
    modes = ", ".join([m.value for m in Mode])
    print(f"Invalid mode: {sys.argv[1]}. Must be one of: {modes}")
    return

  files = sys.argv[2:]

  for f in files:
    process_file(f, mode)


if __name__ == "__main__":
  main()

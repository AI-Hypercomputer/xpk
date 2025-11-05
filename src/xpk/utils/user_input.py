"""
Copyright 2025 Google LLC

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

from typing import Literal

from .console import xpk_print
from .execution_context import is_quiet


def ask_for_user_consent(
    question: str, default_option: Literal["Y", "N"] = "N"
) -> bool:
  """Prompts user with the given question, asking for a yes/no answer and returns a relevant boolean.
  Important: immediatelly returns `True` in quiet mode!

  Example prompt for `question='Continue?'`: `[XPK] Continue? (y/N): `.

  Args:
    question: The question to ask the user.
    default_option: Option to use when user response is empty.
  """
  if is_quiet():
    return True

  options = "y/N" if default_option == "N" else "Y/n"
  prompt = f"[XPK] {question} ({options}): "

  while True:
    user_input = input(prompt) or default_option
    if user_input.lower() in ["yes", "y"]:
      return True
    elif user_input.lower() in ["no", "n"]:
      return False
    else:
      xpk_print("Invalid input. Please enter: yes/no/y/n.")

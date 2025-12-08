"""
Copyright 2024 Google LLC

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

import datetime
import subprocess
import sys
import time

from dataclasses import dataclass
from ..utils.objects import chunks
from ..utils.file import make_tmp_files, write_tmp_file
from ..utils.console import xpk_print
from ..utils.execution_context import is_dry_run


@dataclass
class FailedCommand:
  return_code: int
  name: str
  command: str
  logfile: str


def run_commands(
    commands: list[str],
    jobname: str,
    per_command_name: list[str],
    batch: int = 10,
) -> FailedCommand | None:
  """Run commands in groups of `batch`.

  Args:
    commands: list of command.
    jobname: the name of the job.
    per_command_name: list of command names.
    batch: number of commands to run in parallel.

  Returns:
    None if all commands were successful, FailedCommand instance containing
    details of a single failing command otherwise
  """

  temporary_files_batches = chunks(make_tmp_files(per_command_name), batch)
  commands_batched = chunks(commands, batch)
  per_command_name_batches = chunks(per_command_name, batch)

  xpk_print(
      f'Breaking up a total of {len(commands)} commands into'
      f' {len(commands_batched)} batches'
  )
  if is_dry_run():
    xpk_print('Pretending all the jobs succeeded')
    return None

  for i, _ in enumerate(commands_batched):
    xpk_print(f'Dispatching batch {i}/{len(commands_batched)}')
    maybe_failure = run_command_batch(
        commands_batched[i],
        jobname,
        per_command_name_batches[i],
        temporary_files_batches[i],
    )
    if maybe_failure is not None:
      return maybe_failure
  return None


def run_command_batch(
    commands: list[str],
    jobname: str,
    per_command_name: list[str],
    output_logs: list[str],
) -> FailedCommand | None:
  """Runs commands in parallel.

  Args:
    commands: list of n commands, each command is a a list of strings
    jobname: Useful debugging name for the group of commands
    per_command_name: specific name per task
    output_logs: list of n log paths, each command will output to each log.

  Returns:
    None if all commands were successful, FailedCommand instance containing
    details of a single failing command otherwise
  """

  files = [open(f, 'w', encoding='utf-8') for f in output_logs]
  children = []
  start_time = datetime.datetime.now()
  for command, file in zip(commands, files):
    children.append(
        # subprocess managed by list pylint: disable=consider-using-with
        subprocess.Popen(command, stdout=file, stderr=file, shell=True)
    )

  maybe_failure: FailedCommand | None = None
  while True:
    returncodes = [child.poll() for child in children]
    max_returncode = max([0] + [r for r in returncodes if r is not None])
    completed = len([r for r in returncodes if r is not None])
    total = len(returncodes)
    seconds_elapsed = (datetime.datetime.now() - start_time).total_seconds()
    if completed < total:
      slow_worker_index = returncodes.index(None)
      slow_worker_text = per_command_name[slow_worker_index]
      slow_str = (
          f', task {slow_worker_text} still working, logfile'
          f' {output_logs[slow_worker_index]}'
      )
    else:
      slow_str = ''
    xpk_print(
        f'[t={seconds_elapsed:.2f}, {jobname}] Completed'
        f' {completed}/{total}{slow_str}'
    )
    if max_returncode > 0:
      failing_index = [
          i for i, x in enumerate(returncodes) if x is not None and x > 0
      ][0]
      xpk_print(
          f'Terminating all {jobname} processes since at least one failed.'
      )
      xpk_print(
          f'Failure is {per_command_name[failing_index]}'
          f' and logfile {output_logs[failing_index]}'
      )
      for child in children:
        child.terminate()
      maybe_failure = FailedCommand(
          return_code=returncodes[failing_index] or 0,
          name=per_command_name[failing_index],
          command=commands[failing_index],
          logfile=output_logs[failing_index],
      )
      break

    if completed == total:
      break

    time.sleep(1)

  for file in files:
    file.close()

  return maybe_failure


def run_command_with_updates_retry(
    command, task, verbose=True, num_retry_attempts=5, wait_seconds=10
) -> int:
  """Generic run commands function with updates and retry logic.

  Args:
    command: command to execute
    task: user-facing name of the task
    verbose: shows stdout and stderr if set to true. Set to True by default.
    num_retry_attempts: number of attempts to retry the command.
        This has a default value in the function arguments.
    wait_seconds: Seconds to wait between attempts.
        Has a default value in the function arguments.

  Returns:
    0 if successful and 1 otherwise.
  """

  i = 0
  return_code = -1
  while return_code != 0 and i < num_retry_attempts:
    # Do not sleep before first try.
    if i != 0:
      xpk_print(f'Wait {wait_seconds} seconds before retrying.')
      time.sleep(wait_seconds)
    i += 1
    xpk_print(f'Try {i}: {task}')
    return_code = run_command_with_updates(command, task, verbose=verbose)
  return return_code


def run_command_with_updates(command, task, verbose=True) -> int:
  """Generic run commands function with updates.

  Args:
    command: command to execute
    task: user-facing name of the task
    verbose: shows stdout and stderr if set to true. Set to True by default.

  Returns:
    0 if successful and 1 otherwise.
  """
  if is_dry_run():
    xpk_print(
        f'Task: `{task}` is implemented by the following command'
        ' not running since it is a dry run.'
        f' \n{command}'
    )
    return 0
  if verbose:
    xpk_print(
        f'Task: `{task}` is implemented by `{command}`, streaming output live.'
    )
    with subprocess.Popen(
        command,
        stdout=sys.stdout,
        stderr=sys.stderr,
        shell=True,
    ) as child:
      i = 0
      while True:
        return_code = child.poll()
        if return_code is None:
          xpk_print(f'Waiting for `{task}`, for {i} seconds...', end='\r')
          time.sleep(10)
          i += 10
        else:
          xpk_print(f'Task: `{task}` terminated with code `{return_code}`')
          return return_code
  else:
    xpk_print(f'Task: `{task}` is implemented by `{command}`')
    try:
      subprocess.check_output(command, shell=True, stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as e:
      xpk_print(
          f'Task: `{task}` terminated with ERROR `{e.returncode}`, printing'
          ' logs'
      )
      xpk_print('*' * 80)
      xpk_print(e.output)
      xpk_print('*' * 80)
      return e.returncode
    xpk_print(f'Task: `{task}` succeeded.')
    return 0


def run_command_for_value(
    command,
    task,
    dry_run_return_val='0',
    print_timer=False,
    hide_error=False,
    quiet=False,
) -> tuple[int, str]:
  """Runs the command and returns the error code and stdout.

  Prints errors and associated user-facing information

  Args:
    command: user provided command to run.
    task: user provided task name for running the command.
    dry_run_return_val: return value of this command for dry run.
    print_timer: print out the time the command is running.
    hide_error: hide the error from the command output upon success.

  Returns:
    tuple[int, str]
    int: return_code, default is 0
    str: return_val, default is '0'
  """
  if is_dry_run():
    xpk_print(
        f'Task: `{task}` is implemented by the following command'
        ' not running since it is a dry run.'
        f' \n{command}'
    )
    return 0, dry_run_return_val

  if print_timer:
    if not quiet:
      xpk_print(f'Task: `{task}` is implemented by `{command}`')
    with subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=True,
    ) as child:
      i = 0
      while True:
        return_code = child.poll()
        if return_code is None:
          if not quiet:
            xpk_print(f'Waiting for `{task}`, for {i} seconds...', end='\r')
          time.sleep(1)
          i += 1
        else:
          if not quiet:
            xpk_print(f'Task: `{task}` terminated with code `{return_code}`')
          out_bytes, err_bytes = child.communicate()
          out_str, err_str = str(out_bytes, 'UTF-8'), str(err_bytes, 'UTF-8')
          return return_code, f'{out_str}\n{err_str}'
  else:
    if not quiet:
      xpk_print(f'Task: `{task}` is implemented by `{command}`')
    try:
      output = subprocess.check_output(
          command,
          shell=True,
          stderr=subprocess.STDOUT if not hide_error else None,
      )
    except subprocess.CalledProcessError as e:
      if not quiet:
        xpk_print(f'Task {task} failed with {e.returncode}')
        xpk_print('*' * 80)
        xpk_print(e.output)
        xpk_print('*' * 80)
      return e.returncode, str(e.output, 'UTF-8')
    return 0, str(output, 'UTF-8')


def run_command_with_full_controls(
    command: str,
    task: str,
    instructions: str | None = None,
) -> int:
  """Run command in current shell with system out, in and error handles. Wait
  until it exits.

  Args:
    command: command to execute
    task: user-facing name of the task
    verbose: shows stdout and stderr if set to true. Set to True by default.

  Returns:
    0 if successful and 1 otherwise.
  """
  if is_dry_run():
    xpk_print(
        f'Task: `{task}` is implemented by the following command'
        ' not running since it is a dry run.'
        f' \n{command}'
    )
    return 0

  xpk_print(
      f'Task: `{task}` is implemented by `{command}`. '
      'Streaming output and input live.'
  )

  if instructions is not None:
    xpk_print(instructions)

  try:
    with subprocess.Popen(
        command,
        stdout=sys.stdout,
        stderr=sys.stderr,
        stdin=sys.stdin,
        shell=True,
    ) as child:
      return_code = child.wait()
      xpk_print(f'Task: `{task}` terminated with code `{return_code}`')
  except KeyboardInterrupt:
    return_code = 0

  return return_code


def run_kubectl_apply(yml_string: str, task: str) -> int:
  tmp = write_tmp_file(yml_string)
  command = f'kubectl apply -f {str(tmp)}'
  err_code = run_command_with_updates(command, task)
  return err_code

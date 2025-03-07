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
from argparse import Namespace

from ..utils.objects import chunks
from ..utils.file import make_tmp_files, write_tmp_file
from ..utils.console import xpk_print


def run_commands(commands, jobname, per_command_name, batch=10, dry_run=False):
  """Run commands in groups of `batch`.

  Args:
    commands: list of command.
    jobname: the name of the job.
    per_command_name: list of command names.
    batch: number of commands to run in parallel.
    dry_run: enables dry_run if set to true.

  Returns:
    0 if successful and 1 otherwise.
  """
  temporary_files_batches = chunks(make_tmp_files(per_command_name), batch)
  commands_batched = chunks(commands, batch)
  per_command_name_batches = chunks(per_command_name, batch)

  xpk_print(
      f'Breaking up a total of {len(commands)} commands into'
      f' {len(commands_batched)} batches'
  )
  if dry_run:
    xpk_print('Pretending all the jobs succeeded')
    return 0

  max_return_code = 0
  for i, _ in enumerate(commands_batched):
    xpk_print(f'Dispatching batch {i}/{len(commands_batched)}')
    batch_max_return_code, _ = run_command_batch(
        commands_batched[i],
        jobname,
        per_command_name_batches[i],
        temporary_files_batches[i],
    )
    max_return_code = max(max_return_code, batch_max_return_code)
    if max_return_code > 0:
      return max_return_code
  return max_return_code


def run_command_batch(commands, jobname, per_command_name, output_logs):
  """Runs commands in parallel.

  Args:
    commands: list of n commands, each command is a a list of strings
    jobname: Useful debugging name for the group of commands
    per_command_name: specific name per task
    output_logs: list of n log paths, each command will output to each log.

  Returns:
    The max return code and a list of all the return codes.
  """

  children = []
  start_time = datetime.datetime.now()
  for i, command in enumerate(commands):
    children.append(
        # subprocess managed by list pylint: disable=consider-using-with
        subprocess.Popen(
            command, stdout=output_logs[i], stderr=output_logs[i], shell=True
        )
    )

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
          f' {output_logs[slow_worker_index].name}'
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
          f' and logfile {output_logs[failing_index].name}'
      )
      for child in children:
        child.terminate()
      break

    if completed == total:
      break

    time.sleep(1)
  return max_returncode, returncodes


def run_command_with_updates_retry(
    command, task, args, verbose=True, num_retry_attempts=5, wait_seconds=10
) -> int:
  """Generic run commands function with updates and retry logic.

  Args:
    command: command to execute
    task: user-facing name of the task
    args: user provided arguments for running the command.
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
    return_code = run_command_with_updates(command, task, args, verbose=verbose)
  return return_code


def run_command_with_updates(command, task, global_args, verbose=True) -> int:
  """Generic run commands function with updates.

  Args:
    command: command to execute
    task: user-facing name of the task
    global_args: user provided arguments for running the command.
    verbose: shows stdout and stderr if set to true. Set to True by default.

  Returns:
    0 if successful and 1 otherwise.
  """
  if global_args.dry_run:
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
          time.sleep(1)
          i += 1
        else:
          xpk_print(f'Task: `{task}` terminated with code `{return_code}`')
          return return_code
  else:
    xpk_print(
        f'Task: `{task}` is implemented by `{command}`, hiding output unless'
        ' there is an error.'
    )
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
    global_args,
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
    global_args: user provided arguments for running the command.
    dry_run_return_val: return value of this command for dry run.
    print_timer: print out the time the command is running.
    hide_error: hide the error from the command output upon success.

  Returns:
    tuple[int, str]
    int: return_code, default is 0
    str: return_val, default is '0'
  """
  if global_args is not None and global_args.dry_run:
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
          out, err = child.communicate()
          out, err = str(out, 'UTF-8'), str(err, 'UTF-8')
          return return_code, f'{out}\n{err}'
  else:
    if not quiet:
      xpk_print(
          f'Task: `{task}` is implemented by `{command}`, hiding output unless'
          ' there is an error.'
      )
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
    global_args: Namespace,
    instructions: str | None = None,
) -> int:
  """Run command in current shell with system out, in and error handles. Wait
  until it exits.

  Args:
    command: command to execute
    task: user-facing name of the task
    global_args: user provided arguments for running the command.
    verbose: shows stdout and stderr if set to true. Set to True by default.

  Returns:
    0 if successful and 1 otherwise.
  """
  if global_args.dry_run:
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


def run_kubectl_apply(yml_string: str, task: str, args: Namespace) -> int:
  tmp = write_tmp_file(yml_string)
  command = f'kubectl apply -f {str(tmp.file.name)}'
  err_code = run_command_with_updates(command, task, args)
  return err_code

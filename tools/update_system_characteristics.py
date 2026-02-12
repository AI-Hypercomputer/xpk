import os

FILE_PATH = 'src/xpk/core/system_characteristics.py'


def update_file():
  with open(FILE_PATH, 'r') as f:
    lines = f.readlines()

  new_lines = []
  in_cpu_entry = False

  for i, line in enumerate(lines):
    new_lines.append(line)

    # Check if we are inside a CPU entry
    if 'accelerator_type=AcceleratorType.CPU,' in line:
      in_cpu_entry = True

    # If we are in a CPU entry and see docker_platform, add the missing field
    if in_cpu_entry and 'docker_platform=AMD_PLATFORM,' in line:
      # check if next line is not reservation_accelerator_type (to avoid double add if run twice)
      if i + 1 < len(lines) and 'reservation_accelerator_type' in lines[i + 1]:
        in_cpu_entry = False
        continue

      indent = line[: line.find('docker_platform')]
      # Use raw string or explicit newline char
      new_lines.append(indent + "reservation_accelerator_type='',\n")
      in_cpu_entry = False

  with open(FILE_PATH, 'w') as f:
    f.writelines(new_lines)


if __name__ == '__main__':
  update_file()

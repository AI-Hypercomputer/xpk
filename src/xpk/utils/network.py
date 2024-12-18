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

import ipaddress
import socket
import requests
from .console import xpk_print

# Retrives machine's external IP address
ip_resolver_url = "http://api.ipify.org"
all_IPs_cidr = "0.0.0.0/0"


def get_current_machine_ip(external_ip=True):
  """
  Gets the IP address of the current machine.

  Args:
    external: If True (default), retrieves the external IP address.
              If False, retrieves the internal IP address.

  Returns:
    The IP address as a string.
  """

  try:
    if external_ip:
      # Get external IP address
      response = requests.get(ip_resolver_url, timeout=30)
      return 0, response.text
    else:
      # Get internal IP address
      hostname = socket.gethostname()
      return 0, socket.gethostbyname(hostname)
  except (requests.exceptions.RequestException, socket.gaierror) as e:
    xpk_print(f"Error getting IP address: {e}")
    return 1, None


def is_ip_in_any_network(ip_address, cidrs):
  """
  Checks if an IP address is within any of the provided CIDR ranges.

  Args:
    ip_address: The IP address to check (as a string).
    cidrs: A list of CIDR strings.

  Returns:
    True if the IP address is found in any of the CIDRs, False otherwise.
  """

  try:
    if not are_cidrs_valid(cidrs):
      return False

    if cidrs is None:
      return False

    current_ip = ipaddress.ip_address(ip_address)
    for cidr in cidrs:
      network = ipaddress.ip_network(cidr)
      if current_ip in network:
        return True
  except ValueError as e:
    xpk_print(f"Error: {e}")
    return False
  return False


def is_current_machine_in_any_network(cidrs, external_ip=True):
  """
  Checks if the current machine's IP address is within any of the provided CIDR ranges.

  Args:
    cidrs: A list of CIDR strings.
    external_ip: If True (default), checks the external IP. If False, checks the internal IP.

  Returns:
    True if the IP address is found in any of the CIDRs, False otherwise.
  """
  if not are_cidrs_valid(cidrs):
    return 1, False

  if cidrs is None:
    return 0, False

  return_code, ip_address = get_current_machine_ip(external_ip)
  if return_code > 0:
    return return_code, False
  else:
    return return_code, is_ip_in_any_network(ip_address, cidrs)


def add_current_machine_to_networks(cidrs, external_ip=True):
  """
  Adds the current machine's IP address to the list of CIDRs if it's not already present.

  Args:
    cidrs: A list of CIDR strings.
    external_ip: If True, uses the external IP. If False (default), uses the internal IP.

  Returns:
    The updated list of CIDRs with the current machine's IP added (if necessary).
  """
  if not are_cidrs_valid(cidrs):
    return 1, None

  return_code, ip_address = get_current_machine_ip(external_ip)
  if return_code > 0:
    return return_code, None

  if not is_ip_in_any_network(ip_address, cidrs):
    cidrs.append(f"{ip_address}/32")

  return 0, cidrs


def is_cidr_valid(cidr):
  """
  Validates a CIDR string.

  Args:
    cidr: The CIDR string to validate.

  Returns:
    True if the CIDR string is valid, False otherwise.
  """
  try:
    ipaddress.ip_network(cidr)
    return True
  except ValueError:
    return False


def are_cidrs_valid(cidrs):
  """
  Validates a list of CIDR strings.

  Args:
    cidrs: A list of CIDR strings to validate.

  Returns:
    True if all CIDR strings in the list are valid, False otherwise.
  """
  if cidrs is None:
    return True

  all_cidrs_are_valid = True

  for cidr in cidrs:
    if not is_cidr_valid(cidr):
      all_cidrs_are_valid = False
      xpk_print(f"Error: the string '{cidr}' is not a valid CIDR.")

  return all_cidrs_are_valid

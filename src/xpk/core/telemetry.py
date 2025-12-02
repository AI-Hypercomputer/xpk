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

import platform
import uuid
import json
import os
import time
import sys
import importlib
import subprocess
import tempfile
import requests
from enum import Enum
from typing import Any
from dataclasses import dataclass
from .config import get_config, CLIENT_ID_KEY, SEND_TELEMETRY_KEY, __version__ as xpk_version
from ..utils.execution_context import is_dry_run
from ..utils.user_agent import get_user_agent
from ..utils.feature_flags import FeatureFlags


def should_send_telemetry():
  return (
      FeatureFlags.TELEMETRY_ENABLED
      and get_config().get(SEND_TELEMETRY_KEY) != "false"
  )


def send_clearcut_payload(data: str, wait_to_complete: bool = False) -> None:
  """Sends payload to clearcut endpoint."""
  try:
    file_path = _store_payload_in_temp_file(data)
    if not _schedule_clearcut_background_flush(file_path, wait_to_complete):
      _clearcut_flush(file_path)
  except Exception:  # pylint: disable=broad-exception-caught
    pass


def _store_payload_in_temp_file(data: str) -> str:
  with tempfile.NamedTemporaryFile(
      mode="w", delete=False, encoding="utf-8"
  ) as file:
    json.dump(
        {
            "data": data,
            "url": "https://play.googleapis.com/log",
            "params": {"format": "json_proto"},
            "headers": {"User-Agent": get_user_agent()},
            "method": "POST",
        },
        file,
    )
    return file.name


def _schedule_clearcut_background_flush(
    file_path: str, wait_to_complete: bool
) -> bool:
  """Schedules clearcut background flush.

  Args:
    file_path: path to the temporary file where the events are stored.
    wait_to_complete: whenever to wait for the background script completion.

  Returns:
    True if successful and False otherwise
  """
  with importlib.resources.path("xpk", "telemetry_uploader.py") as path:
    if not os.path.exists(path):
      return False

    kwargs: dict[str, Any] = {}
    if sys.platform == "win32":
      kwargs["creationflags"] = (
          subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW
      )
    else:
      kwargs["start_new_session"] = True

    process = subprocess.Popen(
        args=[
            sys.executable,
            str(path),
            file_path,
        ],
        stdout=sys.stdout if wait_to_complete else subprocess.DEVNULL,
        stderr=sys.stderr if wait_to_complete else subprocess.DEVNULL,
        **kwargs,
    )
    if wait_to_complete:
      process.wait()
    return True


def _clearcut_flush(file_path: str) -> None:
  with open(file_path, mode="r", encoding="utf-8") as file:
    kwargs = json.load(file)
    requests.request(**kwargs)
    os.remove(file_path)


class MetricsEventMetadataKey(Enum):
  SESSION_ID = "XPK_SESSION_ID"
  DRY_RUN = "XPK_DRY_RUN"
  PYTHON_VERSION = "XPK_PYTHON_VERSION"
  ZONE = "XPK_ZONE"
  SYSTEM_CHARACTERISTICS = "XPK_SYSTEM_CHARACTERISTICS"
  PROVISIONING_MODE = "XPK_PROVISIONING_MODE"
  COMMAND = "XPK_COMMAND"
  EXIT_CODE = "XPK_EXIT_CODE"
  RUNNING_AS_PIP = "XPK_RUNNING_AS_PIP"
  RUNNING_FROM_SOURCE = "XPK_RUNNING_FROM_SOURCE"
  LATENCY_SECONDS = "XPK_LATENCY_SECONDS"


@dataclass
class _MetricsEvent:
  time: float
  type: str
  name: str
  metadata: dict[MetricsEventMetadataKey, str]


class _MetricsCollector:
  """Metrics collector for collecting various metrics and events across application."""

  _events: list[_MetricsEvent] = []

  def log_start(self, command: str) -> None:
    """Logs start event."""
    self._events.append(
        _MetricsEvent(
            time=time.time(),
            type="commands",
            name="start",
            metadata={MetricsEventMetadataKey.COMMAND: command},
        )
    )

  def log_complete(self, exit_code: int) -> None:
    """Logs complete event."""
    self._events.append(
        _MetricsEvent(
            time=time.time(),
            type="commands",
            name="complete",
            metadata={MetricsEventMetadataKey.EXIT_CODE: str(exit_code)},
        )
    )

  def log_custom(
      self,
      name: str,
      metadata: dict[MetricsEventMetadataKey, str] | None = None,
  ) -> None:
    """Logs custom event."""
    self._events.append(
        _MetricsEvent(
            time=time.time(),
            type="custom",
            name=name,
            metadata=metadata if metadata is not None else {},
        )
    )

  def flush(self) -> str:
    """Flushes collected events into concord payload."""
    result = _generate_payload(self._events)
    self._events.clear()
    return result


MetricsCollector = _MetricsCollector()


def _generate_payload(events: list[_MetricsEvent]) -> str:
  base_concord_event = _get_base_concord_event()
  base_event_metadata = _get_base_event_metadata()
  serialized_events = []
  first_time = events[0].time if len(events) > 0 else 0
  for event in events:
    metadata = {
        **base_event_metadata,
        **event.metadata,
        MetricsEventMetadataKey.LATENCY_SECONDS: str(
            int(event.time - first_time)
        ),
    }
    serialized_events.append({
        "event_time_ms": int(event.time * 1000),
        "source_extension_json": json.dumps({
            **base_concord_event,
            "event_type": event.type,
            "event_name": event.name,
            "event_metadata": [
                {"key": key.value, "value": value}
                for key, value in metadata.items()
            ],
        }),
    })

  return json.dumps({
      "client_info": {"client_type": "XPK"},
      "log_source_name": "CONCORD",
      "request_time_ms": int(time.time() * 1000),
      "log_event": serialized_events,
  })


def _get_base_event_metadata() -> dict[MetricsEventMetadataKey, str]:
  return {
      MetricsEventMetadataKey.SESSION_ID: _get_session_id(),
      MetricsEventMetadataKey.DRY_RUN: str(is_dry_run()).lower(),
      MetricsEventMetadataKey.PYTHON_VERSION: platform.python_version(),
      MetricsEventMetadataKey.RUNNING_AS_PIP: str(_is_running_as_pip()).lower(),
      MetricsEventMetadataKey.RUNNING_FROM_SOURCE: str(
          _is_running_from_source()
      ).lower(),
  }


def _get_base_concord_event() -> dict[str, str]:
  return {
      "release_version": xpk_version,
      "console_type": "XPK",
      "client_install_id": _ensure_client_id(),
  }


def _is_running_as_pip() -> bool:
  return os.path.basename(sys.argv[0]) == "xpk"


def _is_running_from_source() -> bool:
  current_path = os.path.abspath(os.path.realpath(__file__))
  return (
      "site-packages" not in current_path
      and "dist-packages" not in current_path
  )


def _get_session_id() -> str:
  return str(uuid.uuid4())


def _ensure_client_id() -> str:
  """Generates Client ID and stores in configuration if not already present."""
  current_client_id = get_config().get(CLIENT_ID_KEY)
  if current_client_id is not None:
    return current_client_id

  new_client_id = str(uuid.uuid4())
  get_config().set(CLIENT_ID_KEY, new_client_id)
  return new_client_id

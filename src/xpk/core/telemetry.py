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
import time
from enum import Enum
from dataclasses import dataclass
from .config import xpk_config, CLIENT_ID_KEY, __version__ as xpk_version
from ..utils.execution_context import is_dry_run


def ensure_client_id() -> str:
  """Generates Client ID and stores in configuration if not already present."""
  current_client_id = xpk_config.get(CLIENT_ID_KEY)
  if current_client_id is not None:
    return current_client_id

  new_client_id = str(uuid.uuid4())
  xpk_config.set(CLIENT_ID_KEY, new_client_id)
  return new_client_id


class MetricsEventMetadataKey(Enum):
  SESSION_ID = "XPK_SESSION_ID"
  DRY_RUN = "XPK_DRY_RUN"
  PYTHON_VERSION = "XPK_PYTHON_VERSION"
  ZONE = "XPK_ZONE"
  SYSTEM_CHARACTERISTICS = "XPK_SYSTEM_CHARACTERISTICS"
  PROVISIONING_MODE = "XPK_PROVISIONING_MODE"
  COMMAND = "XPK_COMMAND"
  EXIT_CODE = "XPK_EXIT_CODE"


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
  for event in events:
    metadata = {
        **base_event_metadata,
        **event.metadata,
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
  }


def _get_base_concord_event() -> dict[str, str]:
  return {
      "release_version": xpk_version,
      "console_type": "XPK",
      "client_install_id": ensure_client_id(),
  }


def _get_session_id() -> str:
  return str(uuid.uuid4())

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
from dataclasses import dataclass
from .config import xpk_config, CLIENT_ID_KEY, __version__ as xpk_version
from ..utils.execution_context import is_dry_run

def generate_client_id():
  """Generates Client ID and stores in configuration if not already present."""
  if xpk_config.get(CLIENT_ID_KEY) is None:
    xpk_config.set(CLIENT_ID_KEY, str(uuid.uuid4()))


@dataclass
class _MetricsEvent:
  time: float
  type: str
  name: str
  metadata: dict[str, str]


class _MetricsCollector:
  _events: list[_MetricsEvent] = []

  def log_start(self, command: str) -> None:
    """Logs start event."""
    self._events.append(
        _MetricsEvent(
            time=time.time(),
            type="commands",
            name="start",
            metadata={"command": command},
        )
    )

  def log_complete(self, exit_code: int) -> None:
    """Logs complete event."""
    self._events.append(
        _MetricsEvent(
            time=time.time(),
            type="commands",
            name="complete",
            metadata={"exit_code": str(exit_code)},
        )
    )

  def log_custom(self, name: str, metadata: dict[str, str] = {}) -> None:
    """Logs custom event."""
    self._events.append(
        _MetricsEvent(
            time=time.time(),
            type="custom",
            name=name,
            metadata=metadata,
        )
    )

  def serialize(self) -> str:
    """Serializes collected events into a clearcut payload."""
    return _generate_payload(self._events)

  def clear(self) -> None:
    """Clears collected events."""
    self._events.clear()


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
                {"key": key, "value": value} for key, value in metadata.items()
            ],
        }),
    })

  return json.dumps({
      "client_info": {"client_type": "XPK"},
      "log_source_name": "CONCORD",
      "request_time_ms": int(time.time() * 1000),
      "log_event": serialized_events,
  })


def _get_base_event_metadata() -> dict[str, str]:
  return {
      "session_id": _get_session_id(),
      "dry_run": str(is_dry_run()).lower(),
      "python_version": platform.python_version(),
  }


def _get_base_concord_event() -> dict[str, str]:
  return {
      "release_version": xpk_version,
      "console_type": "XPK",
      "client_install_id": xpk_config.get(CLIENT_ID_KEY),
  }


def _get_session_id() -> str:
  return str(uuid.uuid4())

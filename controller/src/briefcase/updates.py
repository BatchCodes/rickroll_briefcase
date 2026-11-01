"""Briefcase updates from the web app.

The controller does not update the briefcase itself. It writes a request
file. On the Pi, the systemd unit ``rickroll-briefcase-update.path`` starts
``scripts/update.sh`` as root. The script writes its progress to a status
file, which the controller reads.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Literal

LOGGER = logging.getLogger(__name__)

UpdateTarget = Literal["release", "prerelease", "main"]
FINAL_STATES = frozenset({"done", "failed"})
# An update that writes no status for this time has probably stopped.
STALE_SEC = 45 * 60


class UpdateError(RuntimeError):
    pass


class UpdateManager:
    def __init__(self, update_dir: Path, enabled: bool, installed_version: str) -> None:
        self._dir = update_dir
        self._enabled = enabled
        self._installed_version = installed_version

    @property
    def request_file(self) -> Path:
        return self._dir / "request.json"

    @property
    def status_file(self) -> Path:
        return self._dir / "status.json"

    def _read_status(self) -> dict[str, Any] | None:
        try:
            return json.loads(self.status_file.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, json.JSONDecodeError):
            LOGGER.warning("Cannot read %s", self.status_file)
            return None

    def _running(self, status: dict[str, Any] | None) -> bool:
        if status is None or status.get("state") in FINAL_STATES:
            return False
        try:
            age = time.time() - self.status_file.stat().st_mtime
        except OSError:
            return False
        return age < STALE_SEC

    def status(self) -> dict[str, Any]:
        status = self._read_status()
        pending = self.request_file.exists()
        return {
            "available": self._enabled,
            "installed_version": self._installed_version,
            "pending": pending,
            "running": pending or self._running(status),
            "status": status,
        }

    def request(self, target: UpdateTarget) -> dict[str, Any]:
        if not self._enabled:
            raise UpdateError("Updates are not available on this system.")
        if self.status()["running"]:
            raise UpdateError("An update is already running.")
        self._dir.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            {"target": target, "requested_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
        )
        file_descriptor, temp_name = tempfile.mkstemp(
            dir=self._dir, prefix=".request.", suffix=".tmp"
        )
        try:
            with os.fdopen(file_descriptor, "w", encoding="utf-8") as handle:
                handle.write(payload + "\n")
            # The path unit starts the update as soon as request.json exists,
            # so the file must appear complete.
            os.replace(temp_name, self.request_file)
        except BaseException:
            Path(temp_name).unlink(missing_ok=True)
            raise
        LOGGER.info("Requested a briefcase update (target: %s)", target)
        return self.status()

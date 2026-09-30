"""Monitor power control.

The correct method depends on the monitor. ``NullDisplay`` does nothing: the
screen shows a paused frame while the lid is closed. ``CommandDisplay`` runs a
shell command for "on" and for "off", for example an HDMI-CEC command.
Refer to ``docs/software/player.md`` for the methods that were tested.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Protocol

from briefcase.config import AppConfig

LOGGER = logging.getLogger(__name__)

COMMAND_TIMEOUT_SEC = 5.0


class Display(Protocol):
    async def on(self) -> None: ...

    async def off(self) -> None: ...


class NullDisplay:
    async def on(self) -> None:
        pass

    async def off(self) -> None:
        pass


class CommandDisplay:
    def __init__(self, on_command: str, off_command: str) -> None:
        self._on_command = on_command
        self._off_command = off_command
        self._is_on: bool | None = None

    async def on(self) -> None:
        if self._is_on is not True:
            await self._run(self._on_command)
            self._is_on = True

    async def off(self) -> None:
        if self._is_on is not False:
            await self._run(self._off_command)
            self._is_on = False

    async def _run(self, command: str) -> None:
        if not command:
            return
        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await asyncio.wait_for(
                process.communicate(), COMMAND_TIMEOUT_SEC
            )
        except (OSError, TimeoutError):
            LOGGER.exception("The display command %r failed", command)
            return
        if process.returncode != 0:
            LOGGER.warning(
                "The display command %r exited with %d: %s",
                command,
                process.returncode,
                stderr.decode(errors="replace").strip(),
            )


def create_display(config: AppConfig) -> Display:
    if config.display_backend == "command":
        return CommandDisplay(config.display_on_command, config.display_off_command)
    return NullDisplay()

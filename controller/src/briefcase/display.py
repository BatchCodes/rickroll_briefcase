"""Monitor power control.

The correct method depends on the monitor. ``NullDisplay`` does nothing: the
screen shows a paused frame while the lid is closed. ``CommandDisplay`` runs a
shell command for "on" and for "off", for example an HDMI-CEC command.
``MpvDisplay`` makes mpv release the HDMI output and turn the signal off, so
that the monitor goes into power saving.
Refer to ``docs/software/player.md`` for the methods that were tested.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Protocol

from briefcase.config import AppConfig
from briefcase.mpv import MpvClient, MpvError

LOGGER = logging.getLogger(__name__)

COMMAND_TIMEOUT_SEC = 5.0
SCREEN_OFF_COMMAND = "/usr/local/bin/screen-off"


class Display(Protocol):
    @property
    def can_turn_off(self) -> bool: ...

    async def on(self) -> None: ...

    async def off(self) -> None: ...


class NullDisplay:
    can_turn_off = False

    async def on(self) -> None:
        pass

    async def off(self) -> None:
        pass


class CommandDisplay:
    can_turn_off = True

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


class MpvDisplay:
    """Release the video output in mpv, and turn the HDMI signal off.

    Without a video and with ``force-window=no``, mpv closes its video output.
    The kernel keeps the last mode active, so the player container runs a
    script that sets DPMS to off. To turn the screen on, mpv selects the video
    again and sets the mode. The loaded file, its position and the audio stay.
    """

    can_turn_off = True

    def __init__(self, client: MpvClient) -> None:
        self._client = client
        self._is_on: bool | None = None
        client.on_connection(self._on_connection)

    async def on(self) -> None:
        if self._is_on is True:
            return
        try:
            await self._client.set_property("vid", "auto")
            await self._client.set_property("force-window", True)
        except MpvError as error:
            LOGGER.warning("Cannot turn the screen on: %s", error)
            return
        self._is_on = True

    async def off(self) -> None:
        if self._is_on is False:
            return
        try:
            await self._client.set_property("force-window", False)
            await self._client.set_property("vid", "no")
            await self._client.command("run", SCREEN_OFF_COMMAND)
        except MpvError as error:
            LOGGER.warning("Cannot turn the screen off: %s", error)
            return
        self._is_on = False

    async def _on_connection(self, _connected: bool) -> None:
        # A new mpv starts with its video output on.
        self._is_on = None


def create_display(config: AppConfig, client: MpvClient) -> Display:
    if config.display_backend == "player":
        return MpvDisplay(client)
    if config.display_backend == "command":
        return CommandDisplay(config.display_on_command, config.display_off_command)
    return NullDisplay()

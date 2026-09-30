"""Asynchronous client for the mpv JSON IPC socket, and the ``Player`` API.

The controller uses the small ``Player`` protocol. ``MpvPlayer`` implements
it with mpv. Tests use a fake player.
"""

from __future__ import annotations

import asyncio
import contextlib
import itertools
import json
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, Protocol

LOGGER = logging.getLogger(__name__)

RECONNECT_DELAY_SEC = 1.0
COMMAND_TIMEOUT_SEC = 5.0
LOAD_TIMEOUT_SEC = 15.0

EventHandler = Callable[[dict[str, Any]], Awaitable[None] | None]
ConnectionHandler = Callable[[bool], Awaitable[None] | None]


class MpvError(RuntimeError):
    pass


class Player(Protocol):
    @property
    def connected(self) -> bool: ...

    def on_connection(self, handler: ConnectionHandler) -> None: ...

    def on_end_of_file(self, handler: Callable[[], Awaitable[None] | None]) -> None: ...

    async def preload(self, path: Path, start_sec: float, loop: bool) -> None: ...

    async def play(self) -> None: ...

    async def pause(self) -> None: ...

    async def set_mute(self, muted: bool) -> None: ...

    async def set_volume(self, volume: int) -> None: ...

    async def position(self) -> float | None: ...

    async def seek_relative(self, offset_sec: float) -> None: ...

    async def stop(self) -> None: ...


async def _call(handler: Callable[..., Awaitable[None] | None], *args: Any) -> None:
    try:
        result = handler(*args)
        if asyncio.iscoroutine(result):
            await result
    except Exception:
        LOGGER.exception("An mpv event handler failed")


class MpvClient:
    """Keep a connection to the mpv IPC socket, and reconnect when it breaks."""

    def __init__(self, socket_path: Path) -> None:
        self._socket_path = socket_path
        self._request_ids = itertools.count(1)
        self._pending: dict[int, asyncio.Future[Any]] = {}
        self._writer: asyncio.StreamWriter | None = None
        self._event_handlers: list[EventHandler] = []
        self._connection_handlers: list[ConnectionHandler] = []
        self._task: asyncio.Task[None] | None = None
        self._connected = asyncio.Event()

    @property
    def connected(self) -> bool:
        return self._connected.is_set()

    def on_event(self, handler: EventHandler) -> None:
        self._event_handlers.append(handler)

    def on_connection(self, handler: ConnectionHandler) -> None:
        self._connection_handlers.append(handler)

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name="mpv-client")

    async def close(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def wait_connected(self) -> None:
        await self._connected.wait()

    async def command(self, *args: Any) -> Any:
        writer = self._writer
        if writer is None or not self.connected:
            raise MpvError("mpv is not connected")
        request_id = next(self._request_ids)
        future: asyncio.Future[Any] = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future
        message = {"command": list(args), "request_id": request_id}
        try:
            writer.write((json.dumps(message) + "\n").encode())
            await writer.drain()
            return await asyncio.wait_for(future, COMMAND_TIMEOUT_SEC)
        finally:
            self._pending.pop(request_id, None)

    async def set_property(self, name: str, value: Any) -> None:
        await self.command("set_property", name, value)

    async def get_property(self, name: str) -> Any:
        return await self.command("get_property", name)

    async def _run(self) -> None:
        while True:
            try:
                reader, writer = await asyncio.open_unix_connection(
                    str(self._socket_path)
                )
            except OSError:
                await asyncio.sleep(RECONNECT_DELAY_SEC)
                continue
            LOGGER.info("Connected to mpv at %s", self._socket_path)
            self._writer = writer
            self._connected.set()
            for handler in self._connection_handlers:
                asyncio.create_task(_call(handler, True))
            try:
                await self._read_loop(reader)
            finally:
                LOGGER.warning("Lost the connection to mpv")
                self._connected.clear()
                self._writer = None
                writer.close()
                for future in self._pending.values():
                    if not future.done():
                        future.set_exception(MpvError("mpv disconnected"))
                self._pending.clear()
                for handler in self._connection_handlers:
                    asyncio.create_task(_call(handler, False))
            await asyncio.sleep(RECONNECT_DELAY_SEC)

    async def _read_loop(self, reader: asyncio.StreamReader) -> None:
        while True:
            line = await reader.readline()
            if not line:
                return
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                LOGGER.warning("mpv sent a line that is not JSON: %r", line)
                continue
            if "event" in message:
                for handler in self._event_handlers:
                    asyncio.create_task(_call(handler, message))
                continue
            future = self._pending.get(message.get("request_id", -1))
            if future is None or future.done():
                continue
            if message.get("error") == "success":
                future.set_result(message.get("data"))
            else:
                future.set_exception(MpvError(str(message.get("error"))))


class MpvPlayer:
    """``Player`` implementation for mpv."""

    def __init__(self, client: MpvClient) -> None:
        self._client = client
        self._loaded_path: Path | None = None
        self._restart = asyncio.Event()
        self._eof_handlers: list[Callable[[], Awaitable[None] | None]] = []
        client.on_event(self._on_event)
        client.on_connection(self._on_connection)

    @property
    def connected(self) -> bool:
        return self._client.connected

    def on_connection(self, handler: ConnectionHandler) -> None:
        self._client.on_connection(handler)

    def on_end_of_file(self, handler: Callable[[], Awaitable[None] | None]) -> None:
        self._eof_handlers.append(handler)

    async def preload(self, path: Path, start_sec: float, loop: bool) -> None:
        """Load ``path`` paused at ``start_sec``, and wait until it is ready."""
        await self._client.set_property("pause", True)
        await self._client.set_property("loop-file", "inf" if loop else "no")
        self._restart.clear()
        if path == self._loaded_path:
            await self._client.command("seek", start_sec, "absolute+exact")
        else:
            await self._client.set_property("start", f"{start_sec:.3f}")
            await self._client.command("loadfile", str(path), "replace")
            self._loaded_path = path
        try:
            await asyncio.wait_for(self._restart.wait(), LOAD_TIMEOUT_SEC)
        except TimeoutError as error:
            self._loaded_path = None
            raise MpvError(f"mpv did not load {path} in time") from error

    async def play(self) -> None:
        await self._client.set_property("pause", False)

    async def pause(self) -> None:
        await self._client.set_property("pause", True)

    async def set_mute(self, muted: bool) -> None:
        await self._client.set_property("mute", muted)

    async def set_volume(self, volume: int) -> None:
        await self._client.set_property("volume", volume)

    async def position(self) -> float | None:
        try:
            value = await self._client.get_property("time-pos")
        except MpvError:
            return None
        return float(value) if value is not None else None

    async def seek_relative(self, offset_sec: float) -> None:
        await self._client.command("seek", offset_sec, "relative+exact")

    async def stop(self) -> None:
        await self._client.command("stop")
        self._loaded_path = None

    async def _on_connection(self, connected: bool) -> None:
        self._loaded_path = None

    async def _on_event(self, message: dict[str, Any]) -> None:
        event = message.get("event")
        if event == "playback-restart":
            self._restart.set()
        elif event == "end-file" and message.get("reason") == "eof":
            self._loaded_path = None
            for handler in self._eof_handlers:
                await _call(handler)

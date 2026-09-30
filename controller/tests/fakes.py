from __future__ import annotations

import asyncio
from pathlib import Path


class FakePlayer:
    def __init__(self, connected: bool = True) -> None:
        self._connected = connected
        self.calls: list[tuple] = []
        self.loaded: tuple[Path, float, bool] | None = None
        self.paused = True
        self.muted = True
        self.volume: int | None = None
        self.current_position = 0.0
        self._connection_handlers = []
        self._eof_handlers = []

    @property
    def connected(self) -> bool:
        return self._connected

    def on_connection(self, handler) -> None:
        self._connection_handlers.append(handler)

    def on_end_of_file(self, handler) -> None:
        self._eof_handlers.append(handler)

    async def set_connected(self, connected: bool) -> None:
        self._connected = connected
        for handler in self._connection_handlers:
            await handler(connected)

    async def finish(self) -> None:
        for handler in self._eof_handlers:
            await handler()

    async def preload(self, path: Path, start_sec: float, loop: bool) -> None:
        self.calls.append(("preload", path.name, start_sec, loop))
        self.loaded = (path, start_sec, loop)
        self.paused = True
        self.current_position = start_sec

    async def play(self) -> None:
        self.calls.append(("play",))
        self.paused = False

    async def pause(self) -> None:
        self.calls.append(("pause",))
        self.paused = True

    async def set_mute(self, muted: bool) -> None:
        self.muted = muted

    async def set_volume(self, volume: int) -> None:
        self.volume = volume

    async def position(self) -> float | None:
        return self.current_position

    async def seek_relative(self, offset_sec: float) -> None:
        self.calls.append(("seek", offset_sec))
        self.current_position = max(0.0, self.current_position + offset_sec)

    async def stop(self) -> None:
        self.calls.append(("stop",))
        self.loaded = None


class FakeDisplay:
    def __init__(self) -> None:
        self.is_on: bool | None = None

    async def on(self) -> None:
        self.is_on = True

    async def off(self) -> None:
        self.is_on = False


async def settle() -> None:
    for _ in range(5):
        await asyncio.sleep(0)

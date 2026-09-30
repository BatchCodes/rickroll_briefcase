import asyncio
import json
from pathlib import Path

import pytest

from briefcase.mpv import MpvClient, MpvError, MpvPlayer


class FakeMpvServer:
    """A small subset of the mpv JSON IPC protocol."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.properties: dict[str, object] = {"pause": False, "time-pos": None}
        self.commands: list[list] = []
        self.writers: list[asyncio.StreamWriter] = []
        self.server: asyncio.base_events.Server | None = None

    async def start(self) -> None:
        self.server = await asyncio.start_unix_server(self._handle, str(self.path))

    async def stop(self) -> None:
        for writer in self.writers:
            writer.close()
        self.server.close()
        await self.server.wait_closed()

    async def send_event(self, event: dict) -> None:
        for writer in self.writers:
            writer.write((json.dumps(event) + "\n").encode())
            await writer.drain()

    async def _handle(self, reader, writer) -> None:
        self.writers.append(writer)
        while line := await reader.readline():
            message = json.loads(line)
            command = message["command"]
            self.commands.append(command)
            reply = {"request_id": message["request_id"], "error": "success"}
            name = command[0]
            if name == "set_property":
                self.properties[command[1]] = command[2]
            elif name == "get_property":
                if command[1] not in self.properties:
                    reply["error"] = "property not found"
                else:
                    reply["data"] = self.properties[command[1]]
            elif name == "loadfile":
                self.properties["time-pos"] = float(self.properties.get("start", 0))
            elif name == "seek":
                self.properties["time-pos"] = float(command[1])
            writer.write((json.dumps(reply) + "\n").encode())
            await writer.drain()
            if name in {"loadfile", "seek"}:
                await self.send_event({"event": "playback-restart"})


@pytest.fixture
async def server(tmp_path):
    fake = FakeMpvServer(tmp_path / "mpv.sock")
    await fake.start()
    yield fake
    await fake.stop()


@pytest.fixture
async def client(server):
    mpv = MpvClient(server.path)
    mpv.start()
    await asyncio.wait_for(mpv.wait_connected(), 2)
    yield mpv
    await mpv.close()


async def test_command_round_trip(client, server):
    await client.set_property("volume", 50)
    assert server.properties["volume"] == 50
    assert await client.get_property("volume") == 50


async def test_command_error_raises(client):
    with pytest.raises(MpvError):
        await client.get_property("missing")


async def test_preload_loads_paused_at_start_then_seeks_for_same_file(client, server):
    player = MpvPlayer(client)
    await player.preload(Path("/data/videos/a.mp4"), 30.0, loop=True)

    assert server.properties["pause"] is True
    assert server.properties["start"] == "30.000"
    assert server.properties["loop-file"] == "inf"
    assert ["loadfile", "/data/videos/a.mp4", "replace"] in server.commands
    assert await player.position() == 30.0

    server.commands.clear()
    await player.preload(Path("/data/videos/a.mp4"), 10.0, loop=False)
    assert ["seek", 10.0, "absolute+exact"] in server.commands
    assert not any(command[0] == "loadfile" for command in server.commands)
    assert server.properties["loop-file"] == "no"


async def test_end_of_file_event_calls_handler(client, server):
    player = MpvPlayer(client)
    finished = asyncio.Event()
    player.on_end_of_file(finished.set)

    await server.send_event({"event": "end-file", "reason": "stop"})
    await asyncio.sleep(0.05)
    assert not finished.is_set()

    await server.send_event({"event": "end-file", "reason": "eof"})
    await asyncio.wait_for(finished.wait(), 1)


async def test_command_without_connection_raises(tmp_path):
    mpv = MpvClient(tmp_path / "missing.sock")
    with pytest.raises(MpvError):
        await mpv.command("get_property", "pause")

import asyncio

import pytest
from test_mpv import FakeMpvServer

from briefcase.config import AppConfig
from briefcase.display import (
    SCREEN_OFF_COMMAND,
    CommandDisplay,
    MpvDisplay,
    NullDisplay,
    create_display,
)
from briefcase.mpv import MpvClient


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


async def test_off_releases_the_video_and_runs_the_screen_off_script(client, server):
    display = MpvDisplay(client)
    await display.off()

    assert server.properties["force-window"] is False
    assert server.properties["vid"] == "no"
    assert ["run", SCREEN_OFF_COMMAND] in server.commands


async def test_on_selects_the_video_again(client, server):
    display = MpvDisplay(client)
    await display.off()
    await display.on()

    assert server.properties["vid"] == "auto"
    assert server.properties["force-window"] is True


async def test_repeated_calls_send_nothing(client, server):
    display = MpvDisplay(client)
    await display.off()
    server.commands.clear()
    await display.off()
    assert server.commands == []

    await display.on()
    server.commands.clear()
    await display.on()
    assert server.commands == []


async def test_a_new_mpv_resets_the_state(client, server):
    display = MpvDisplay(client)
    await display.off()
    await display._on_connection(True)
    server.commands.clear()

    await display.off()
    assert ["run", SCREEN_OFF_COMMAND] in server.commands


async def test_off_without_mpv_does_not_raise(tmp_path):
    display = MpvDisplay(MpvClient(tmp_path / "missing.sock"))
    await display.off()
    await display.on()


def test_create_display_selects_the_backend(tmp_path):
    client = MpvClient(tmp_path / "mpv.sock")
    assert isinstance(
        create_display(AppConfig(display_backend="player"), client), MpvDisplay
    )
    assert isinstance(
        create_display(AppConfig(display_backend="command"), client), CommandDisplay
    )
    display = create_display(AppConfig(display_backend="none"), client)
    assert isinstance(display, NullDisplay)
    assert display.can_turn_off is False

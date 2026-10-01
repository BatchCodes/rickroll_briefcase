import asyncio

import pytest
from fakes import FakeDisplay, FakePlayer

from briefcase.controller import BriefcaseController, State
from briefcase.inputs import InputState, SimulatedInputs
from briefcase.library import Library
from briefcase.power import (
    PowerError,
    PowerManager,
    PowerState,
    SimulatedPowerAction,
)
from briefcase.settings import SettingsStore

DELAY = 0.05


class FailingAction:
    simulated = False

    async def power_off(self):
        raise PowerError("polkit said no")


class RealAction:
    simulated = False

    def __init__(self):
        self.calls = 0

    async def power_off(self):
        self.calls += 1


@pytest.fixture
def parts(tmp_path):
    videos = tmp_path / "videos"
    videos.mkdir()
    (videos / "a.mp4").write_bytes(b"x")
    inputs = SimulatedInputs(lid_open=True, armed=True, power_switch=True)
    player = FakePlayer()
    controller = BriefcaseController(
        inputs,
        player,
        FakeDisplay(),
        Library(videos),
        SettingsStore(tmp_path / "settings.json"),
    )
    return inputs, player, controller


async def make_manager(inputs, controller, action):
    manager = PowerManager(inputs, controller, action, DELAY)
    await controller.start()
    await manager.start()
    return manager


async def test_without_power_switch_nothing_happens():
    inputs = SimulatedInputs()
    assert inputs.read().power_on is None
    inputs.set(power_on=False)
    assert inputs.read().power_on is None


async def test_switch_off_stops_video_and_powers_off(parts):
    inputs, player, controller = parts
    action = RealAction()
    manager = await make_manager(inputs, controller, action)
    assert controller.state is State.PLAYING

    inputs.set(power_on=False)
    await manager.inputs_changed()
    assert manager.status()["state"] == PowerState.OFF_PENDING
    await asyncio.sleep(DELAY * 3)

    assert action.calls == 1
    assert player.paused and player.muted
    assert controller.state is State.SHUTTING_DOWN
    assert manager.status()["state"] == PowerState.SHUTTING_DOWN

    inputs.set(lid_open=False)
    await controller.inputs_changed()
    assert controller.state is State.SHUTTING_DOWN


async def test_switch_on_within_delay_cancels(parts):
    inputs, _, controller = parts
    action = RealAction()
    manager = await make_manager(inputs, controller, action)

    inputs.set(power_on=False)
    await manager.inputs_changed()
    await asyncio.sleep(DELAY / 3)
    inputs.set(power_on=True)
    await manager.inputs_changed()
    await asyncio.sleep(DELAY * 2)

    assert action.calls == 0
    assert controller.state is State.PLAYING
    assert manager.status()["state"] == PowerState.ON


async def test_simulated_power_off_and_on(parts):
    inputs, _, controller = parts
    action = SimulatedPowerAction()
    manager = await make_manager(inputs, controller, action)

    inputs.set(power_on=False)
    await manager.inputs_changed()
    await asyncio.sleep(DELAY * 3)
    assert action.calls == 1
    assert manager.status()["state"] == PowerState.SIMULATED_OFF

    inputs.set(power_on=True)
    await manager.inputs_changed()
    assert controller.state is State.PLAYING
    assert manager.status()["state"] == PowerState.ON


async def test_failed_power_off_resumes(parts):
    inputs, _, controller = parts
    manager = await make_manager(inputs, controller, FailingAction())

    inputs.set(power_on=False)
    await manager.inputs_changed()
    await asyncio.sleep(DELAY * 3)

    status = manager.status()
    assert "polkit said no" in status["error"]
    assert status["state"] == PowerState.ON
    assert controller.state is not State.SHUTTING_DOWN


async def test_switch_off_at_start_shuts_down(parts):
    inputs, _, controller = parts
    inputs.set(power_on=False)
    action = RealAction()
    await make_manager(inputs, controller, action)
    await asyncio.sleep(DELAY * 3)
    assert action.calls == 1


def test_input_state_default_has_no_power_switch():
    assert InputState(lid_open=False, armed=True).power_on is None

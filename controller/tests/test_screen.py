import asyncio
import random

import pytest
from fakes import FakeDisplay, FakePlayer

from briefcase.controller import BriefcaseController, ControllerError, State
from briefcase.inputs import SimulatedInputs
from briefcase.library import Library
from briefcase.mpv import AudioStatus
from briefcase.settings import Settings, SettingsStore

DELAY = 0.05


class FixedDisplay(FakeDisplay):
    can_turn_off = False


@pytest.fixture
def videos_dir(tmp_path):
    directory = tmp_path / "videos"
    directory.mkdir()
    (directory / "a.mp4").write_bytes(b"x")
    return directory


def make_controller(tmp_path, videos_dir, display, **settings):
    inputs = SimulatedInputs(lid_open=False, armed=False)
    store = SettingsStore(tmp_path / "settings.json")
    store.replace(Settings(resume_window_sec=0, screen_off_delay_sec=DELAY, **settings))
    controller = BriefcaseController(
        inputs, FakePlayer(), display, Library(videos_dir), store, rng=random.Random(1)
    )
    return inputs, store, controller


@pytest.fixture
def parts(tmp_path, videos_dir):
    display = FakeDisplay()
    inputs, store, controller = make_controller(tmp_path, videos_dir, display)
    return inputs, display, store, controller


async def change(controller, inputs, **values):
    inputs.set(**values)
    await controller.inputs_changed()


async def wait_for_delay():
    await asyncio.sleep(DELAY * 3)


async def test_disarmed_and_closed_turns_the_screen_off(parts):
    _, display, _, controller = parts
    await controller.start()

    assert controller.state is State.DISARMED
    assert display.is_on is False
    assert controller.status().screen_on is False


async def test_disarmed_with_the_lid_open_shows_the_screen(parts):
    inputs, display, _, controller = parts
    await controller.start()

    await change(controller, inputs, lid_open=True)
    assert controller.state is State.DISARMED
    assert display.is_on is True

    await change(controller, inputs, lid_open=False)
    assert display.is_on is False


async def test_arming_turns_the_screen_on_until_the_delay_ends(parts):
    inputs, display, _, controller = parts
    await controller.start()

    await change(controller, inputs, armed=True)
    assert display.is_on is True
    assert controller.status().screen_off_remaining_sec is not None

    await wait_for_delay()
    assert display.is_on is False
    assert controller.status().screen_off_remaining_sec is None


async def test_lid_opens_while_the_screen_is_off_plays_at_once(parts):
    inputs, display, _, controller = parts
    await controller.start()
    await change(controller, inputs, armed=True)
    await wait_for_delay()
    assert display.is_on is False

    await change(controller, inputs, lid_open=True)
    assert controller.state is State.PLAYING
    assert display.is_on is True


async def test_closing_the_lid_while_armed_starts_the_delay(parts):
    inputs, display, _, controller = parts
    await controller.start()
    await change(controller, inputs, armed=True, lid_open=True)
    assert controller.state is State.PLAYING

    await change(controller, inputs, lid_open=False)
    assert display.is_on is True

    await wait_for_delay()
    assert display.is_on is False


async def test_disarm_and_arm_primes_again(parts):
    inputs, display, _, controller = parts
    await controller.start()
    await change(controller, inputs, armed=True)
    await wait_for_delay()

    await change(controller, inputs, armed=False)
    assert display.is_on is False
    await change(controller, inputs, armed=True)
    assert display.is_on is True


async def test_prime_turns_the_screen_on_for_the_delay(parts):
    inputs, display, _, controller = parts
    await controller.start()
    await change(controller, inputs, armed=True)
    await wait_for_delay()

    await controller.prime(until_opened=False)
    assert display.is_on is True
    assert controller.status().screen_off_remaining_sec is not None

    await wait_for_delay()
    assert display.is_on is False


async def test_prime_until_opened_keeps_the_screen_on(parts):
    inputs, display, _, controller = parts
    await controller.start()
    await change(controller, inputs, armed=True)
    await wait_for_delay()

    await controller.prime(until_opened=True)
    await wait_for_delay()
    assert display.is_on is True
    assert controller.status().primed_until_opened is True

    await change(controller, inputs, lid_open=True)
    assert controller.state is State.PLAYING
    assert controller.status().primed_until_opened is False

    await change(controller, inputs, lid_open=False)
    await wait_for_delay()
    assert display.is_on is False


async def test_disarm_ends_prime_until_opened(parts):
    inputs, display, _, controller = parts
    await controller.start()
    await change(controller, inputs, armed=True)
    await controller.prime(until_opened=True)

    await change(controller, inputs, armed=False)
    assert display.is_on is False
    assert controller.status().primed_until_opened is False


async def test_prime_needs_an_armed_briefcase(parts):
    _, _, _, controller = parts
    await controller.start()

    with pytest.raises(ControllerError):
        await controller.prime(until_opened=False)


async def test_setting_off_keeps_the_screen_on(tmp_path, videos_dir):
    display = FakeDisplay()
    inputs, _, controller = make_controller(
        tmp_path, videos_dir, display, screen_off_enabled=False
    )
    await controller.start()

    assert controller.state is State.DISARMED
    assert controller.status().screen_on is True
    assert display.is_on is None
    with pytest.raises(ControllerError):
        await controller.prime(until_opened=False)


async def test_turning_the_setting_off_turns_the_screen_on(parts):
    _, display, store, controller = parts
    await controller.start()
    assert display.is_on is False

    settings = store.get()
    settings.screen_off_enabled = False
    store.replace(settings)
    await controller.settings_changed()
    assert display.is_on is True


async def test_a_display_that_cannot_turn_off_stays_on(tmp_path, videos_dir):
    display = FixedDisplay()
    _, _, controller = make_controller(tmp_path, videos_dir, display)
    await controller.start()

    status = controller.status()
    assert status.screen_on is True
    assert status.screen_off_available is False
    assert status.screen_off_enabled is False
    assert display.is_on is None


async def test_shutdown_turns_the_screen_off(parts):
    inputs, display, _, controller = parts
    await controller.start()
    await change(controller, inputs, armed=True, lid_open=True)

    await controller.prepare_shutdown()
    assert display.is_on is False


async def test_a_new_player_turns_the_screen_off_again(parts):
    _, display, _, controller = parts
    await controller.start()
    assert display.is_on is False
    display.is_on = True

    await controller._on_player_connection(True)
    assert display.is_on is False


async def test_the_sound_is_checked_often_after_a_wake(parts):
    inputs, display, _, controller = parts
    player = controller._player
    await controller.start()
    await change(controller, inputs, armed=True)
    await wait_for_delay()
    assert display.is_on is False

    # HDMI sound fails until the HDMI output is active again.
    player.audio = AudioStatus.FAILED
    player.audio_after_retry = AudioStatus.FAILED
    await change(controller, inputs, lid_open=True)
    assert controller.state is State.PLAYING
    player.audio_after_retry = AudioStatus.OK

    await asyncio.sleep(0.7)
    assert player.audio is AudioStatus.OK
    await controller.close()


async def test_the_sound_status_is_hidden_while_the_screen_is_off(parts):
    _, display, _, controller = parts
    player = controller._player
    player.audio = AudioStatus.FAILED
    await controller.start()
    assert display.is_on is False

    status = await controller.status_with_position()
    assert status.audio is AudioStatus.UNKNOWN

import asyncio
import random

import pytest
from fakes import FakeDisplay, FakePlayer

from briefcase.controller import BriefcaseController, State
from briefcase.inputs import SimulatedInputs
from briefcase.library import Library
from briefcase.settings import (
    EndAction,
    SelectionMode,
    Settings,
    SettingsStore,
    StartMode,
    VideoSettings,
)


@pytest.fixture
def videos_dir(tmp_path):
    directory = tmp_path / "videos"
    directory.mkdir()
    for name in ("a.mp4", "b.mp4", "c.mp4"):
        (directory / name).write_bytes(b"x")
    return directory


@pytest.fixture
def parts(tmp_path, videos_dir):
    inputs = SimulatedInputs(lid_open=False, armed=True)
    player = FakePlayer()
    display = FakeDisplay()
    library = Library(videos_dir)
    store = SettingsStore(tmp_path / "settings.json")
    controller = BriefcaseController(
        inputs, player, display, library, store, rng=random.Random(1)
    )
    return inputs, player, display, store, controller


async def test_start_preloads_default_video_paused_at_30_seconds(parts):
    inputs, player, display, _, controller = parts
    await controller.start()

    assert controller.state is State.READY
    assert player.calls == [("preload", "a.mp4", 30.0, True)]
    assert player.paused and player.muted
    assert display.is_on is False


async def test_open_lid_plays_immediately_and_close_stops(parts):
    inputs, player, display, _, controller = parts
    await controller.start()

    inputs.set(lid_open=True)
    await controller.inputs_changed()
    assert controller.state is State.PLAYING
    assert not player.paused and not player.muted
    assert display.is_on is True
    assert player.calls[-1] == ("play",)

    inputs.set(lid_open=False)
    await controller.inputs_changed()
    assert controller.state is State.READY
    assert player.paused and player.muted
    assert display.is_on is False
    assert player.calls[-1] == ("preload", "a.mp4", 30.0, True)


async def test_disarmed_open_lid_does_not_play(parts):
    inputs, player, _, _, controller = parts
    inputs.set(armed=False)
    await controller.start()
    inputs.set(lid_open=True)
    await controller.inputs_changed()

    assert controller.state is State.DISARMED
    assert ("play",) not in player.calls


async def test_arm_with_lid_open_plays(parts):
    inputs, player, _, _, controller = parts
    inputs.set(armed=False, lid_open=True)
    await controller.start()
    assert controller.state is State.DISARMED

    inputs.set(armed=True)
    await controller.inputs_changed()
    assert controller.state is State.PLAYING


async def test_cold_boot_armed_and_open_plays_without_user_action(parts):
    inputs, player, _, _, controller = parts
    inputs.set(lid_open=True)
    await controller.start()

    assert controller.state is State.PLAYING
    assert player.calls == [("preload", "a.mp4", 30.0, True), ("play",)]


async def test_disarm_while_playing_stops(parts):
    inputs, player, _, _, controller = parts
    inputs.set(lid_open=True)
    await controller.start()
    inputs.set(armed=False)
    await controller.inputs_changed()

    assert controller.state is State.DISARMED
    assert player.paused


async def test_armed_video_and_start_modes(parts):
    inputs, player, _, store, controller = parts
    store.replace(
        Settings(
            armed_video="b.mp4",
            videos={"b.mp4": VideoSettings(start_mode=StartMode.BEGINNING)},
        )
    )
    await controller.start()
    assert player.loaded[0].name == "b.mp4"
    assert player.loaded[1] == 0.0


async def test_random_start_uses_cue_points(parts):
    _, player, _, store, controller = parts
    store.update_video(
        "a.mp4",
        VideoSettings(start_mode=StartMode.RANDOM, cue_points_sec=[10, 20, 40]),
    )
    await controller.start()
    assert player.loaded[1] in {10.0, 20.0, 40.0}


async def test_resume_saves_position_on_close(parts):
    inputs, player, _, store, controller = parts
    store.update_video("a.mp4", VideoSettings(start_mode=StartMode.RESUME))
    await controller.start()
    assert player.loaded[1] == 0.0

    inputs.set(lid_open=True)
    await controller.inputs_changed()
    player.current_position = 42.5
    inputs.set(lid_open=False)
    await controller.inputs_changed()

    assert store.get().video("a.mp4").resume_sec == 42.5
    assert player.loaded[1] == 42.5


async def test_cycle_mode_moves_to_next_video_after_each_play(parts):
    inputs, player, _, store, controller = parts
    store.replace(Settings(selection_mode=SelectionMode.CYCLE))
    await controller.start()
    played = []
    for _ in range(4):
        inputs.set(lid_open=True)
        await controller.inputs_changed()
        played.append(controller.status().current_video)
        inputs.set(lid_open=False)
        await controller.inputs_changed()

    assert played == ["a.mp4", "b.mp4", "c.mp4", "a.mp4"]


async def test_shuffle_mode_does_not_repeat_immediately(parts):
    inputs, _, _, store, controller = parts
    store.replace(Settings(selection_mode=SelectionMode.SHUFFLE))
    await controller.start()
    played = []
    for _ in range(10):
        inputs.set(lid_open=True)
        await controller.inputs_changed()
        played.append(controller.status().current_video)
        inputs.set(lid_open=False)
        await controller.inputs_changed()

    assert all(
        first != second for first, second in zip(played, played[1:], strict=False)
    )


async def test_end_action_stop_finishes_and_close_prepares_again(parts):
    inputs, player, display, store, controller = parts
    store.update_video("a.mp4", VideoSettings(end_action=EndAction.STOP))
    await controller.start()
    assert player.loaded[2] is False

    inputs.set(lid_open=True)
    await controller.inputs_changed()
    await player.finish()
    assert controller.state is State.FINISHED
    assert display.is_on is False

    inputs.set(lid_open=False)
    await controller.inputs_changed()
    assert controller.state is State.READY
    assert player.calls[-1] == ("preload", "a.mp4", 30.0, False)


async def test_test_play_and_lid_change_cancels_it(parts):
    inputs, player, _, _, controller = parts
    await controller.start()
    await controller.set_test_play(True)
    assert controller.state is State.PLAYING

    await controller.set_test_play(False)
    assert controller.state is State.READY

    await controller.set_test_play(True)
    inputs.set(lid_open=False)
    await controller.inputs_changed()
    assert controller.state is State.READY
    assert not controller.status().test_play


async def test_settings_change_reloads_when_idle(parts):
    _, player, _, store, controller = parts
    await controller.start()
    store.replace(Settings(armed_video="c.mp4", volume=55))
    await controller.settings_changed()

    assert player.loaded[0].name == "c.mp4"
    assert player.volume == 55


async def test_settings_change_does_not_interrupt_playback(parts):
    inputs, player, _, store, controller = parts
    inputs.set(lid_open=True)
    await controller.start()
    store.replace(Settings(armed_video="c.mp4", volume=20))
    await controller.settings_changed()

    assert controller.state is State.PLAYING
    assert player.loaded[0].name == "a.mp4"
    assert player.volume == 20


async def test_no_videos(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    controller = BriefcaseController(
        SimulatedInputs(),
        FakePlayer(),
        FakeDisplay(),
        Library(empty),
        SettingsStore(tmp_path / "settings.json"),
    )
    await controller.start()
    assert controller.state is State.NO_VIDEO


async def test_deleted_current_video_moves_to_next(parts, videos_dir):
    _, player, _, _, controller = parts
    await controller.start()
    (videos_dir / "a.mp4").unlink()
    await controller.library_changed()

    assert player.loaded[0].name == "b.mp4"


async def test_player_offline_then_reconnect_prepares_and_plays(parts):
    inputs, player, _, _, controller = parts
    player._connected = False
    inputs.set(lid_open=True)
    await controller.start()
    assert controller.state is State.PLAYER_OFFLINE

    await player.set_connected(True)
    assert controller.state is State.PLAYING


async def test_failed_preload_retries_automatically(parts, monkeypatch):
    import briefcase.controller as controller_module

    monkeypatch.setattr(controller_module, "RETRY_DELAY_SEC", 0.01)
    _, player, _, _, controller = parts
    original = player.preload
    failures = {"left": 1}

    async def flaky_preload(path, start_sec, loop):
        if failures["left"]:
            failures["left"] -= 1
            raise RuntimeError("mpv did not load the file in time")
        await original(path, start_sec, loop)

    player.preload = flaky_preload
    await controller.start()
    assert controller.state is State.ERROR
    assert "did not load" in controller.status().error

    for _ in range(50):
        await asyncio.sleep(0.01)
        if controller.state is State.READY:
            break
    assert controller.state is State.READY
    assert controller.status().error is None


async def test_start_after_end_of_short_video_uses_zero(parts, monkeypatch):
    from briefcase.library import Library, VideoInfo

    monkeypatch.setattr(
        Library, "probe", lambda self, name: VideoInfo(duration_sec=10.0)
    )
    _, player, _, _, controller = parts
    await controller.start()
    assert player.loaded[1] == 0.0


async def test_pause_seek_and_use_position_as_start(parts):
    _, player, _, store, controller = parts
    await controller.start()
    await controller.set_test_play(True)

    await controller.set_paused(True)
    assert player.paused
    assert controller.status().paused
    await controller.seek(5)
    assert player.current_position == 35.0

    assert await controller.use_position(as_cue_point=False) == 35.0
    video = store.get().video("a.mp4")
    assert video.start_sec == 35.0
    assert video.start_mode is StartMode.FIXED

    assert await controller.use_position(as_cue_point=True) == 35.0
    assert store.get().video("a.mp4").cue_points_sec == [35.0]

    await controller.set_test_play(False)
    assert player.loaded[1] == 35.0
    assert not controller.status().paused


async def test_pause_needs_a_playing_video(parts):
    from briefcase.controller import ControllerError

    _, _, _, _, controller = parts
    await controller.start()
    with pytest.raises(ControllerError):
        await controller.set_paused(True)
    with pytest.raises(ControllerError):
        await controller.use_position(as_cue_point=False)


async def test_status_with_position(parts):
    _, player, _, _, controller = parts
    await controller.start()
    status = await controller.status_with_position()
    assert status.position_sec == 30.0

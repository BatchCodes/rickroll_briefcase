"""The briefcase state machine.

Rules:

- The video plays only while the briefcase is armed and the lid is open, or
  while a test play from the web app is active.
- While the video does not play, the next video is already loaded, paused at
  its start position and muted. Thus an open lid only has to unpause it.
- All events go through one lock, so transitions never overlap. Each handler
  reads the latest input state, so switch bounce cannot leave a stale state.
"""

from __future__ import annotations

import asyncio
import logging
import random
from dataclasses import asdict, dataclass, replace
from enum import StrEnum

from briefcase.display import Display
from briefcase.inputs import Inputs, InputState
from briefcase.library import Library
from briefcase.mpv import MpvError, Player
from briefcase.settings import (
    EndAction,
    SelectionMode,
    Settings,
    SettingsStore,
    StartMode,
)

LOGGER = logging.getLogger(__name__)

RETRY_DELAY_SEC = 5.0
KNOB_TEXT_MS = 3000


class ControllerError(RuntimeError):
    """A request that the controller cannot do in the current state."""


class State(StrEnum):
    STARTING = "starting"
    NO_VIDEO = "no_video"
    PLAYER_OFFLINE = "player_offline"
    DISARMED = "disarmed"
    READY = "ready"
    PLAYING = "playing"
    FINISHED = "finished"
    ERROR = "error"
    SHUTTING_DOWN = "shutting_down"


@dataclass(frozen=True)
class Status:
    state: State
    lid_open: bool
    armed: bool
    simulated_inputs: bool
    player_connected: bool
    power_switch_on: bool | None
    current_video: str | None
    start_sec: float | None
    test_play: bool
    paused: bool
    error: str | None
    position_sec: float | None = None
    duration_sec: float | None = None
    resume_remaining_sec: float | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class BriefcaseController:
    def __init__(
        self,
        inputs: Inputs,
        player: Player,
        display: Display,
        library: Library,
        settings: SettingsStore,
        rng: random.Random | None = None,
    ) -> None:
        self._inputs = inputs
        self._player = player
        self._display = display
        self._library = library
        self._settings = settings
        self._rng = rng or random.Random()
        self._lock = asyncio.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._state = State.STARTING
        self._current: str | None = None
        self._next: str | None = None
        self._start_sec: float | None = None
        self._prepared = False
        self._test_play = False
        self._paused = False
        self._shutting_down = False
        self._error: str | None = None
        self._retry: asyncio.TimerHandle | None = None
        self._resume_timer: asyncio.TimerHandle | None = None
        self._resume_deadline: float | None = None

    @property
    def state(self) -> State:
        return self._state

    def status(self) -> Status:
        inputs = self._inputs.read()
        return Status(
            state=self._state,
            lid_open=inputs.lid_open,
            armed=inputs.armed,
            simulated_inputs=self._inputs.simulated,
            player_connected=self._player.connected,
            power_switch_on=inputs.power_on,
            current_video=self._current,
            start_sec=self._start_sec,
            test_play=self._test_play,
            paused=self._paused,
            error=self._error,
            resume_remaining_sec=self._resume_remaining(),
        )

    def _resume_remaining(self) -> float | None:
        if self._resume_deadline is None or self._loop is None:
            return None
        return max(0.0, self._resume_deadline - self._loop.time())

    async def status_with_position(self) -> Status:
        """The status, with the playback position and the video length."""
        status = self.status()
        if self._current is None or not self._player.connected:
            return status
        position = None
        try:
            position = await self._player.position()
        except MpvError:
            LOGGER.debug("Cannot read the playback position")
        info = self._library.probe(self._current) if self._current else None
        return replace(
            status,
            position_sec=position,
            duration_sec=info.duration_sec if info else None,
        )

    async def start(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._inputs.subscribe(self._on_inputs_threadsafe)
        self._player.on_connection(self._on_player_connection)
        self._player.on_end_of_file(self._on_end_of_file)
        await self._run(self._refresh)

    def _on_inputs_threadsafe(self, _state: InputState) -> None:
        if self._loop is None:
            return
        self._loop.call_soon_threadsafe(
            lambda: asyncio.ensure_future(self.inputs_changed())
        )

    async def inputs_changed(self) -> None:
        async def handler() -> None:
            self._test_play = False
            await self._apply()

        await self._run(handler)

    async def settings_changed(self) -> None:
        """Load the new settings. Do not interrupt a video that plays."""

        async def handler() -> None:
            await self._player_call(
                self._player.set_volume(self._settings.get().volume)
            )
            if self._state is not State.PLAYING:
                self._cancel_resume_window()
                self._prepared = False
            await self._apply()

        await self._run(handler)

    async def volume_changed(self) -> None:
        """Apply the new volume at once. Do not load the video again."""

        async def handler() -> None:
            await self._player_call(
                self._player.set_volume(self._settings.get().volume)
            )

        await self._run(handler)

    async def library_changed(self) -> None:
        async def handler() -> None:
            names = self._library.names()
            if self._state is not State.PLAYING:
                self._cancel_resume_window()
            if self._current not in names:
                self._prepared = False
                if self._state in (State.PLAYING, State.FINISHED):
                    await self._player_call(self._player.stop())
                    self._state = State.READY
            elif self._state is not State.PLAYING:
                self._prepared = False
            await self._apply()

        await self._run(handler)

    def on_knob_threadsafe(self, step: int) -> None:
        if self._loop is None:
            return
        self._loop.call_soon_threadsafe(
            lambda: asyncio.ensure_future(self.knob_turned(step))
        )

    async def knob_turned(self, step: int) -> None:
        """Select the next or previous video. Only while disarmed."""

        async def handler() -> None:
            inputs = self._inputs.read()
            if inputs.armed or self._state is State.PLAYING or self._shutting_down:
                LOGGER.debug("Knob step ignored: armed or playing")
                return
            names = self._library.names()
            if not names or not self._player.connected:
                return
            settings = self._settings.get()
            if self._current in names:
                index = names.index(self._current)
            elif settings.armed_video in names:
                index = names.index(settings.armed_video)
            else:
                index = 0
            index = (index + step) % len(names)
            name = names[index]
            settings.armed_video = name
            self._settings.replace(settings)
            self._cancel_resume_window()
            self._next = name
            self._prepared = False
            await self._prepare()
            self._state = State.DISARMED
            if inputs.lid_open:
                await self._display.on()
            await self._player_call(
                self._player.show_text(
                    f"{index + 1}/{len(names)}  {name}", KNOB_TEXT_MS
                )
            )
            LOGGER.info("Knob: selected %s", name)

        await self._run(handler)

    async def set_test_play(self, active: bool) -> None:
        async def handler() -> None:
            self._test_play = active
            await self._apply()

        await self._run(handler)

    async def set_paused(self, paused: bool) -> None:
        """Pause or resume a video that plays, for example to find a frame."""

        async def handler() -> None:
            if self._state is not State.PLAYING:
                raise ControllerError("No video plays now.")
            if paused:
                await self._player.pause()
            else:
                await self._player.play()
            self._paused = paused

        await self._run_strict(handler)

    async def seek(self, offset_sec: float) -> None:
        async def handler() -> None:
            if self._state is not State.PLAYING:
                raise ControllerError("No video plays now.")
            await self._player.seek_relative(offset_sec)

        await self._run_strict(handler)

    async def seek_to(self, position_sec: float) -> None:
        async def handler() -> None:
            if self._state is not State.PLAYING:
                raise ControllerError("No video plays now.")
            await self._player.seek_absolute(max(0.0, position_sec))

        await self._run_strict(handler)

    async def use_position(self, as_cue_point: bool) -> float:
        """Store the current position as the start position or as a cue point."""
        result: dict[str, float] = {}

        async def handler() -> None:
            if self._current is None or self._state is not State.PLAYING:
                raise ControllerError("Play the video first, then pause it.")
            position = await self._player.position()
            if position is None:
                raise ControllerError("The player has no position now.")
            position = round(position, 1)
            video = self._settings.get().video(self._current)
            if as_cue_point:
                video.cue_points_sec = sorted({*video.cue_points_sec, position})
            else:
                video.start_mode = StartMode.FIXED
                video.start_sec = position
            self._settings.update_video(self._current, video)
            result["position"] = position

        await self._run_strict(handler)
        return result["position"]

    async def _run_strict(self, handler) -> None:
        """Run a web request. Raise its error to the caller."""
        async with self._lock:
            await handler()

    async def prepare_shutdown(self) -> None:
        """Stop the video before the Pi powers off. Ignore later events."""

        async def handler() -> None:
            self._cancel_resume_window()
            if self._state is State.PLAYING and self._player.connected:
                await self._stop_playback()
            await self._display.off()
            self._shutting_down = True
            self._test_play = False
            self._state = State.SHUTTING_DOWN
            LOGGER.info("Ready for the power-off")

        await self._run(handler)

    async def resume_after_shutdown(self) -> None:
        """Start again after a simulated or failed power-off."""

        async def handler() -> None:
            self._shutting_down = False
            await self._refresh()

        await self._run(handler)

    async def _on_player_connection(self, connected: bool) -> None:
        async def handler() -> None:
            self._cancel_resume_window()
            self._prepared = False
            if not connected:
                self._state = State.PLAYER_OFFLINE
                return
            await self._refresh()

        await self._run(handler)

    async def _on_end_of_file(self) -> None:
        async def handler() -> None:
            if self._state is not State.PLAYING:
                return
            LOGGER.info("The video %s finished", self._current)
            self._prepared = False
            self._state = State.FINISHED
            self._test_play = False
            await self._display.off()

        await self._run(handler)

    async def _run(self, handler) -> None:
        async with self._lock:
            try:
                await handler()
            except Exception as error:
                LOGGER.exception("A controller event failed")
                self._error = str(error)
                if not self._prepared:
                    self._state = State.ERROR
                    self._schedule_retry()

    def _schedule_retry(self) -> None:
        """Try again later, so the briefcase recovers without user action."""
        if self._loop is None:
            return
        if self._retry is not None:
            self._retry.cancel()
        LOGGER.info("Trying again in %.0f s", RETRY_DELAY_SEC)
        self._retry = self._loop.call_later(
            RETRY_DELAY_SEC,
            lambda: asyncio.ensure_future(self._run(self._refresh)),
        )

    async def _refresh(self) -> None:
        self._cancel_resume_window()
        self._prepared = False
        await self._apply()

    def _wants_play(self, inputs: InputState) -> bool:
        return (inputs.armed and inputs.lid_open) or self._test_play

    async def _apply(self) -> None:
        if self._shutting_down:
            self._state = State.SHUTTING_DOWN
            return
        inputs = self._inputs.read()
        if not self._player.connected:
            self._state = State.PLAYER_OFFLINE
            return
        if not self._library.names():
            self._current = None
            self._start_sec = None
            self._prepared = False
            self._state = State.NO_VIDEO
            return

        wants_play = self._wants_play(inputs)
        if self._state is State.PLAYING:
            if wants_play:
                return
            await self._stop_playback(keep_position=True)
        elif self._state is State.FINISHED:
            if wants_play:
                return
            self._advance()

        if not self._prepared:
            await self._prepare()
        if wants_play:
            await self._play()
        else:
            self._state = State.READY if inputs.armed else State.DISARMED

    async def _prepare(self) -> None:
        settings = self._settings.get()
        name = self._choose_video(settings)
        start_sec = self._choose_start(settings, name)
        video = settings.video(name)
        await self._player.set_mute(True)
        await self._display.off()
        await self._player.preload(
            self._library.path(name),
            start_sec,
            loop=video.end_action is EndAction.LOOP,
        )
        await self._player.set_volume(settings.volume)
        self._current = name
        self._start_sec = start_sec
        self._prepared = True
        self._error = None
        LOGGER.info("Ready: %s at %.1f s", name, start_sec)

    async def _play(self) -> None:
        if self._resume_deadline is not None:
            LOGGER.info("Reopened within the resume window. Continuing")
        self._cancel_resume_window()
        self._paused = False
        await self._player.set_mute(False)
        await asyncio.gather(self._player.play(), self._display.on())
        self._state = State.PLAYING
        LOGGER.info("Playing %s", self._current)

    async def _stop_playback(self, keep_position: bool = False) -> None:
        """Stop the video.

        With ``keep_position`` and a resume window, the video stays paused
        at its position. Opening the lid within the window continues it.
        After the window, the next video loads at its start position.
        """
        self._paused = False
        await self._player.pause()
        await self._player.set_mute(True)
        await self._save_resume_position()
        await self._display.off()
        window = self._settings.get().resume_window_sec
        if keep_position and window > 0 and self._loop is not None:
            self._start_resume_window(window)
            LOGGER.info("Paused %s. Resume window: %.0f s", self._current, window)
            return
        self._prepared = False
        self._advance()
        LOGGER.info("Stopped %s", self._current)

    def _start_resume_window(self, window: float) -> None:
        self._cancel_resume_window()
        assert self._loop is not None
        self._resume_deadline = self._loop.time() + window
        self._resume_timer = self._loop.call_later(
            window, lambda: asyncio.ensure_future(self._run(self._end_resume_window))
        )

    def _cancel_resume_window(self) -> None:
        if self._resume_timer is not None:
            self._resume_timer.cancel()
        self._resume_timer = None
        self._resume_deadline = None

    async def _end_resume_window(self) -> None:
        if self._resume_deadline is None or self._state is State.PLAYING:
            return
        self._cancel_resume_window()
        LOGGER.info("The resume window ended. Loading the start position")
        self._prepared = False
        self._advance()
        await self._apply()

    async def _save_resume_position(self) -> None:
        if self._current is None:
            return
        settings = self._settings.get()
        video = settings.video(self._current)
        if video.start_mode is not StartMode.RESUME:
            return
        position = await self._player.position()
        if position is None:
            return
        video.resume_sec = position
        self._settings.update_video(self._current, video)

    def _advance(self) -> None:
        """Move to the next video after a play, for the cycle and shuffle modes."""
        settings = self._settings.get()
        names = self._library.names()
        if not names or settings.selection_mode is SelectionMode.SINGLE:
            return
        if settings.selection_mode is SelectionMode.CYCLE:
            if self._current in names:
                index = (names.index(self._current) + 1) % len(names)
            else:
                index = 0
            self._next = names[index]
        else:
            choices = [name for name in names if name != self._current] or names
            self._next = self._rng.choice(choices)

    def _choose_video(self, settings: Settings) -> str:
        names = self._library.names()
        pending = self._next
        self._next = None
        if pending in names and settings.selection_mode is not SelectionMode.SINGLE:
            return pending
        if settings.selection_mode is SelectionMode.SHUFFLE and self._current is None:
            return self._rng.choice(names)
        if (
            settings.selection_mode is not SelectionMode.SINGLE
            and self._current in names
        ):
            return self._current
        if settings.armed_video in names:
            return settings.armed_video
        return names[0]

    def _choose_start(self, settings: Settings, name: str) -> float:
        start_sec = self._wanted_start(settings, name)
        info = self._library.probe(name)
        duration = info.duration_sec if info else None
        if duration and start_sec >= duration - 1:
            LOGGER.info(
                "The start position %.1f s is after the end of %s. Using 0 s.",
                start_sec,
                name,
            )
            return 0.0
        return start_sec

    def _wanted_start(self, settings: Settings, name: str) -> float:
        video = settings.video(name)
        if video.start_mode is StartMode.BEGINNING:
            return 0.0
        if video.start_mode is StartMode.RESUME:
            return video.resume_sec
        if video.start_mode is StartMode.RANDOM and video.cue_points_sec:
            return self._rng.choice(video.cue_points_sec)
        return settings.start_sec_for(name)

    async def _player_call(self, awaitable) -> None:
        try:
            await awaitable
        except MpvError as error:
            LOGGER.warning("A player command failed: %s", error)

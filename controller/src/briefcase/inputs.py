"""Lid and arm switch inputs.

``GpioInputs`` reads a reed switch and a toggle switch on a Raspberry Pi.
``SimulatedInputs`` replaces them on a laptop. The web app changes the
simulated values.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from briefcase.config import AppConfig

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class InputState:
    lid_open: bool
    armed: bool


Listener = Callable[[InputState], None]


class Inputs(Protocol):
    simulated: bool

    def read(self) -> InputState: ...

    def subscribe(self, listener: Listener) -> None: ...

    def close(self) -> None: ...


class _ListenerMixin:
    def __init__(self) -> None:
        self._listeners: list[Listener] = []
        self._listener_lock = threading.Lock()

    def subscribe(self, listener: Listener) -> None:
        with self._listener_lock:
            self._listeners.append(listener)

    def _notify(self, state: InputState) -> None:
        with self._listener_lock:
            listeners = list(self._listeners)
        for listener in listeners:
            try:
                listener(state)
            except Exception:
                LOGGER.exception("An input listener failed")


class SimulatedInputs(_ListenerMixin):
    """Inputs for a laptop. The default is armed with the lid closed."""

    simulated = True

    def __init__(self, lid_open: bool = False, armed: bool = True) -> None:
        super().__init__()
        self._lock = threading.Lock()
        self._state = InputState(lid_open=lid_open, armed=armed)

    def read(self) -> InputState:
        with self._lock:
            return self._state

    def set(self, *, lid_open: bool | None = None, armed: bool | None = None) -> None:
        with self._lock:
            state = InputState(
                lid_open=self._state.lid_open if lid_open is None else lid_open,
                armed=self._state.armed if armed is None else armed,
            )
            changed = state != self._state
            self._state = state
        if changed:
            self._notify(state)

    def close(self) -> None:
        pass


class GpioInputs(_ListenerMixin):
    """Reed switch and arm switch on GPIO pins, with internal pull-ups.

    Each switch connects its pin to ground when it is closed. With the
    default wiring, the reed switch is closed (pin low) when the magnet is
    near, so a low lid pin means "lid closed". A low arm pin means "armed".
    """

    simulated = False

    def __init__(self, config: AppConfig, pin_factory: object | None = None) -> None:
        super().__init__()
        from gpiozero import Button

        bounce = config.debounce_sec if config.debounce_sec > 0 else None
        self._lid_closed_when_low = config.lid_closed_when_low
        self._armed_when_low = config.armed_when_low
        self._lid = Button(
            config.lid_pin, pull_up=True, bounce_time=bounce, pin_factory=pin_factory
        )
        self._arm = Button(
            config.arm_pin, pull_up=True, bounce_time=bounce, pin_factory=pin_factory
        )
        self._last: InputState | None = None
        self._state_lock = threading.Lock()
        for button in (self._lid, self._arm):
            button.when_pressed = self._on_change
            button.when_released = self._on_change
        LOGGER.info(
            "GPIO inputs ready: lid pin %d, arm pin %d", config.lid_pin, config.arm_pin
        )

    def read(self) -> InputState:
        lid_low = self._lid.is_pressed
        arm_low = self._arm.is_pressed
        lid_closed = lid_low if self._lid_closed_when_low else not lid_low
        armed = arm_low if self._armed_when_low else not arm_low
        return InputState(lid_open=not lid_closed, armed=armed)

    def _on_change(self) -> None:
        state = self.read()
        with self._state_lock:
            if state == self._last:
                return
            self._last = state
        self._notify(state)

    def close(self) -> None:
        self._lid.close()
        self._arm.close()


def create_inputs(config: AppConfig) -> Inputs:
    if config.input_backend == "simulated":
        LOGGER.info("Using simulated lid and arm inputs")
        return SimulatedInputs()
    return GpioInputs(config)

"""The video selector knob: a rotary encoder such as the KY-040.

Each detent of the knob produces one step: +1 clockwise, -1 anticlockwise.
``GpioKnob`` reads the encoder on a Raspberry Pi. ``SimulatedKnob`` replaces
it on a laptop. The web app produces the simulated steps.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import Protocol

from briefcase.config import AppConfig

LOGGER = logging.getLogger(__name__)

StepListener = Callable[[int], None]


class Knob(Protocol):
    simulated: bool

    def subscribe(self, listener: StepListener) -> None: ...

    def close(self) -> None: ...


class _StepNotifier:
    def __init__(self) -> None:
        self._listeners: list[StepListener] = []
        self._lock = threading.Lock()

    def subscribe(self, listener: StepListener) -> None:
        with self._lock:
            self._listeners.append(listener)

    def _notify(self, step: int) -> None:
        with self._lock:
            listeners = list(self._listeners)
        for listener in listeners:
            try:
                listener(step)
            except Exception:
                LOGGER.exception("A knob listener failed")


class SimulatedKnob(_StepNotifier):
    simulated = True

    def turn(self, step: int) -> None:
        if step not in (-1, 1):
            raise ValueError("A knob step must be -1 or 1.")
        self._notify(step)

    def close(self) -> None:
        pass


# The pin levels (CLK << 1 | DT) in clockwise order: 11, 01, 00, 10.
_CLOCKWISE_ORDER = (0b11, 0b01, 0b00, 0b10)
_REST_STATES = (0b11, 0b00)


class GpioKnob(_StepNotifier):
    """A quadrature rotary encoder on two GPIO pins.

    The decoder emits one encoder step at each rest state, ``11`` and ``00``,
    so a KY-040 with a detent at every half cycle gives one step per click.
    gpiozero's ``RotaryEncoder`` counts only full cycles, which needs two
    clicks on such a knob. ``steps_per_detent`` groups the encoder steps into
    one knob step: set it to 2 for a knob with a detent at every full cycle.
    ``invert`` swaps the direction, for example when ``CLK`` and ``DT`` are
    wired the other way.
    """

    simulated = False

    def __init__(self, config: AppConfig, pin_factory: object | None = None) -> None:
        super().__init__()
        from gpiozero import DigitalInputDevice

        assert config.knob_clk_pin is not None
        assert config.knob_dt_pin is not None
        self._steps_per_detent = max(1, config.knob_steps_per_detent)
        self._direction = -1 if config.knob_invert else 1
        self._count = 0
        self._quarters = 0
        self._lock = threading.Lock()
        self._clk = DigitalInputDevice(
            config.knob_clk_pin, pull_up=True, pin_factory=pin_factory
        )
        self._dt = DigitalInputDevice(
            config.knob_dt_pin, pull_up=True, pin_factory=pin_factory
        )
        self._state = self._read()
        for device in (self._clk, self._dt):
            device.when_activated = self._changed
            device.when_deactivated = self._changed
        LOGGER.info(
            "Knob ready: CLK pin %d, DT pin %d",
            config.knob_clk_pin,
            config.knob_dt_pin,
        )

    def _read(self) -> int:
        # With the pull-ups, an active (low) pin reads as 1, so invert it.
        return (0 if self._clk.value else 0b10) | (0 if self._dt.value else 0b01)

    def _changed(self) -> None:
        with self._lock:
            new_state = self._read()
            old_state, self._state = self._state, new_state
            delta = (
                _CLOCKWISE_ORDER.index(new_state) - _CLOCKWISE_ORDER.index(old_state)
            ) % 4
            if delta == 1:
                self._quarters += 1
            elif delta == 3:
                self._quarters -= 1
            # delta 2 means a missed edge: the direction is not known, so wait.
            if new_state not in _REST_STATES:
                return
            quarters, self._quarters = self._quarters, 0
            if abs(quarters) < 2:
                # Contact bounce, or the knob went back to the same rest state.
                return
            self._count += 1 if quarters > 0 else -1
            if abs(self._count) < self._steps_per_detent:
                return
            step = 1 if self._count > 0 else -1
            self._count = 0
        self._notify(step * self._direction)

    def close(self) -> None:
        self._clk.close()
        self._dt.close()


def create_knob(config: AppConfig) -> Knob | None:
    if config.knob_clk_pin is None or config.knob_dt_pin is None:
        return None
    if config.input_backend == "simulated":
        LOGGER.info("Using a simulated knob")
        return SimulatedKnob()
    return GpioKnob(config)

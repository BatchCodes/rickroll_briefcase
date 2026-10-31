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


class GpioKnob(_StepNotifier):
    """A quadrature rotary encoder on two GPIO pins.

    ``steps_per_detent`` groups the encoder steps into one knob step. Most
    KY-040 modules give one encoder step per detent. ``invert`` swaps the
    direction, for example when ``CLK`` and ``DT`` are wired the other way.
    """

    simulated = False

    def __init__(self, config: AppConfig, pin_factory: object | None = None) -> None:
        super().__init__()
        from gpiozero import RotaryEncoder

        assert config.knob_clk_pin is not None
        assert config.knob_dt_pin is not None
        self._steps_per_detent = max(1, config.knob_steps_per_detent)
        self._direction = -1 if config.knob_invert else 1
        self._count = 0
        self._count_lock = threading.Lock()
        self._encoder = RotaryEncoder(
            config.knob_clk_pin,
            config.knob_dt_pin,
            max_steps=0,
            pin_factory=pin_factory,
        )
        self._encoder.when_rotated_clockwise = lambda: self._raw_step(1)
        self._encoder.when_rotated_counter_clockwise = lambda: self._raw_step(-1)
        LOGGER.info(
            "Knob ready: CLK pin %d, DT pin %d",
            config.knob_clk_pin,
            config.knob_dt_pin,
        )

    def _raw_step(self, raw: int) -> None:
        with self._count_lock:
            self._count += raw
            if abs(self._count) < self._steps_per_detent:
                return
            step = 1 if self._count > 0 else -1
            self._count = 0
        self._notify(step * self._direction)

    def close(self) -> None:
        self._encoder.close()


def create_knob(config: AppConfig) -> Knob | None:
    if config.knob_clk_pin is None or config.knob_dt_pin is None:
        return None
    if config.input_backend == "simulated":
        LOGGER.info("Using a simulated knob")
        return SimulatedKnob()
    return GpioKnob(config)

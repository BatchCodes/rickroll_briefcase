"""The power switch: a clean shutdown when the switch goes off.

The switch connects its GPIO pin (normally GPIO 3) to ground when it is on.
When it goes off and stays off for the delay, the controller stops the video
and asks the host to power off. Then:

- Without the power latch hardware, the Pi halts. Switching on again pulls
  GPIO 3 low, and a halted Pi wakes on GPIO 3.
- With the power latch, the ``gpio-poweroff`` overlay signals the latch at
  the end of the shutdown, and the latch disconnects the power.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from enum import StrEnum
from typing import Protocol

from briefcase.config import AppConfig
from briefcase.inputs import Inputs, InputState

LOGGER = logging.getLogger(__name__)

LOGIND_BUS_NAME = "org.freedesktop.login1"
LOGIND_PATH = "/org/freedesktop/login1"
LOGIND_INTERFACE = "org.freedesktop.login1.Manager"


class PowerError(RuntimeError):
    pass


class PowerState(StrEnum):
    NO_SWITCH = "no_switch"
    ON = "on"
    OFF_PENDING = "off_pending"
    SHUTTING_DOWN = "shutting_down"
    SIMULATED_OFF = "simulated_off"


class PowerAction(Protocol):
    simulated: bool

    async def power_off(self) -> None: ...


class ShutdownTarget(Protocol):
    async def prepare_shutdown(self) -> None: ...

    async def resume_after_shutdown(self) -> None: ...


class LogindPowerAction:
    """Ask the host ``systemd-logind`` to power off, through the system D-Bus."""

    simulated = False

    async def power_off(self) -> None:
        await asyncio.to_thread(self._power_off)

    def _power_off(self) -> None:
        try:
            from jeepney import DBusAddress, new_method_call
            from jeepney.io.blocking import open_dbus_connection
        except ImportError as error:
            raise PowerError("The jeepney package is not installed.") from error
        address = DBusAddress(
            LOGIND_PATH, bus_name=LOGIND_BUS_NAME, interface=LOGIND_INTERFACE
        )
        message = new_method_call(address, "PowerOff", "b", (False,))
        try:
            with open_dbus_connection(bus="SYSTEM") as connection:
                reply = connection.send_and_get_reply(message, timeout=10)
        except (OSError, TimeoutError) as error:
            raise PowerError(f"Cannot reach logind: {error}") from error
        if reply.header.message_type.name == "error":
            raise PowerError(f"logind refused the power-off: {reply.body}")


class SimulatedPowerAction:
    """Laptop mode: log the power-off, but do nothing to the host."""

    simulated = True

    def __init__(self) -> None:
        self.calls = 0

    async def power_off(self) -> None:
        self.calls += 1
        LOGGER.warning("Simulated power switch: the Pi would shut down now")


class PowerManager:
    def __init__(
        self,
        inputs: Inputs,
        target: ShutdownTarget,
        action: PowerAction,
        delay_sec: float,
    ) -> None:
        self._inputs = inputs
        self._target = target
        self._action = action
        self._delay_sec = delay_sec
        self._loop: asyncio.AbstractEventLoop | None = None
        self._pending: asyncio.Task[None] | None = None
        self._shutting_down = False
        self._error: str | None = None

    @property
    def enabled(self) -> bool:
        return self._inputs.read().power_on is not None

    def status(self) -> dict[str, object]:
        state = self._state()
        return {
            "state": state.value,
            "switch_on": self._inputs.read().power_on,
            "delay_sec": self._delay_sec,
            "error": self._error,
        }

    def _state(self) -> PowerState:
        if not self.enabled:
            return PowerState.NO_SWITCH
        if self._shutting_down:
            if self._action.simulated:
                return PowerState.SIMULATED_OFF
            return PowerState.SHUTTING_DOWN
        if self._pending is not None and not self._pending.done():
            return PowerState.OFF_PENDING
        return PowerState.ON

    async def start(self) -> None:
        if not self.enabled:
            return
        self._loop = asyncio.get_running_loop()
        self._inputs.subscribe(self._on_inputs_threadsafe)
        LOGGER.info("The power switch is enabled")
        await self.inputs_changed()

    async def close(self) -> None:
        if self._pending is not None:
            self._pending.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._pending

    def _on_inputs_threadsafe(self, _state: InputState) -> None:
        if self._loop is None:
            return
        self._loop.call_soon_threadsafe(
            lambda: asyncio.ensure_future(self.inputs_changed())
        )

    async def inputs_changed(self) -> None:
        power_on = self._inputs.read().power_on
        if power_on is None:
            return
        if power_on:
            await self._switched_on()
        else:
            self._switched_off()

    async def _switched_on(self) -> None:
        if self._pending is not None and not self._pending.done():
            LOGGER.info("The power switch is on again. The shutdown is cancelled")
            self._pending.cancel()
            self._pending = None
        if self._shutting_down and self._action.simulated:
            self._shutting_down = False
            await self._target.resume_after_shutdown()

    def _switched_off(self) -> None:
        if self._shutting_down:
            return
        if self._pending is not None and not self._pending.done():
            return
        LOGGER.info("The power switch is off. Shutting down in %.1f s", self._delay_sec)
        self._pending = asyncio.ensure_future(self._shutdown_after_delay())

    async def _shutdown_after_delay(self) -> None:
        await asyncio.sleep(self._delay_sec)
        if self._inputs.read().power_on:
            return
        self._shutting_down = True
        self._error = None
        await self._target.prepare_shutdown()
        try:
            await self._action.power_off()
        except PowerError as error:
            LOGGER.error("The shutdown failed: %s", error)
            self._error = str(error)
            self._shutting_down = False
            await self._target.resume_after_shutdown()


def create_power(
    config: AppConfig, inputs: Inputs, target: ShutdownTarget
) -> PowerManager:
    action: PowerAction
    if config.input_backend == "simulated":
        action = SimulatedPowerAction()
    else:
        action = LogindPowerAction()
    return PowerManager(inputs, target, action, config.power_off_delay_sec)

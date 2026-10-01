import pytest
from gpiozero.pins.mock import MockFactory

from briefcase.config import AppConfig
from briefcase.inputs import GpioInputs, InputState, SimulatedInputs


def test_simulated_inputs_notify_only_on_change():
    inputs = SimulatedInputs()
    events = []
    inputs.subscribe(events.append)

    inputs.set(lid_open=True)
    inputs.set(lid_open=True)
    inputs.set(armed=False)

    assert events == [
        InputState(lid_open=True, armed=True),
        InputState(lid_open=True, armed=False),
    ]
    assert inputs.read() == InputState(lid_open=True, armed=False)


@pytest.fixture
def factory():
    mock_factory = MockFactory()
    yield mock_factory
    mock_factory.reset()


def make_gpio(factory, **overrides):
    config = AppConfig(lid_pin=17, arm_pin=27, debounce_sec=0, **overrides)
    return GpioInputs(config, pin_factory=factory)


def test_gpio_default_wiring(factory):
    inputs = make_gpio(factory)
    lid = factory.pin(17)
    arm = factory.pin(27)

    lid.drive_low()
    arm.drive_low()
    assert inputs.read() == InputState(lid_open=False, armed=True)

    lid.drive_high()
    assert inputs.read() == InputState(lid_open=True, armed=True)

    arm.drive_high()
    assert inputs.read() == InputState(lid_open=True, armed=False)
    inputs.close()


def test_gpio_inverted_wiring(factory):
    inputs = make_gpio(factory, lid_closed_when_low=False, armed_when_low=False)
    factory.pin(17).drive_low()
    factory.pin(27).drive_low()
    assert inputs.read() == InputState(lid_open=True, armed=False)
    inputs.close()


def test_gpio_notifies_listener(factory):
    inputs = make_gpio(factory)
    events = []
    inputs.subscribe(events.append)
    lid = factory.pin(17)
    arm = factory.pin(27)
    arm.drive_low()
    lid.drive_low()
    events.clear()

    lid.drive_high()

    assert events[-1] == InputState(lid_open=True, armed=True)
    inputs.close()


def test_gpio_power_switch(factory):
    inputs = make_gpio(factory, power_switch_pin=3)
    power = factory.pin(3)
    power.drive_low()
    assert inputs.read().power_on is True
    power.drive_high()
    assert inputs.read().power_on is False
    inputs.close()


def test_gpio_without_power_switch(factory):
    inputs = make_gpio(factory)
    assert inputs.read().power_on is None
    inputs.close()

import pytest
from gpiozero.pins.mock import MockFactory

from briefcase.config import AppConfig
from briefcase.knob import GpioKnob, SimulatedKnob, create_knob


def test_no_knob_without_pins():
    assert create_knob(AppConfig()) is None


def test_simulated_knob_when_pins_set_in_laptop_mode():
    config = AppConfig(input_backend="simulated", knob_clk_pin=22, knob_dt_pin=23)
    assert isinstance(create_knob(config), SimulatedKnob)


def test_simulated_knob_reports_steps():
    knob = SimulatedKnob()
    steps = []
    knob.subscribe(steps.append)
    knob.turn(1)
    knob.turn(-1)
    assert steps == [1, -1]
    with pytest.raises(ValueError):
        knob.turn(2)


@pytest.fixture
def factory():
    mock_factory = MockFactory()
    yield mock_factory
    mock_factory.reset()


def drive(clk, dt, levels):
    for clk_level, dt_level in levels:
        clk.drive_low() if clk_level == 0 else clk.drive_high()
        dt.drive_low() if dt_level == 0 else dt.drive_high()


def clockwise(clk, dt):
    """One full quadrature cycle: 11, 01, 00, 10, 11."""
    drive(clk, dt, ((0, 1), (0, 0), (1, 0), (1, 1)))


def anticlockwise(clk, dt):
    drive(clk, dt, ((1, 0), (0, 0), (0, 1), (1, 1)))


def make_knob(factory, **overrides):
    config = AppConfig(knob_clk_pin=22, knob_dt_pin=23, **overrides)
    knob = GpioKnob(config, pin_factory=factory)
    steps = []
    knob.subscribe(steps.append)
    clk, dt = factory.pin(22), factory.pin(23)
    clk.drive_high()
    dt.drive_high()
    return knob, steps, clk, dt


def test_gpio_knob_one_step_per_half_cycle(factory):
    knob, steps, clk, dt = make_knob(factory)
    drive(clk, dt, ((0, 1), (0, 0)))
    assert steps == [1]
    drive(clk, dt, ((1, 0), (1, 1)))
    assert steps == [1, 1]
    knob.close()


def test_gpio_knob_directions(factory):
    knob, steps, clk, dt = make_knob(factory)
    clockwise(clk, dt)
    anticlockwise(clk, dt)
    assert steps == [1, 1, -1, -1]
    knob.close()


def test_gpio_knob_ignores_bounce(factory):
    knob, steps, clk, dt = make_knob(factory)
    drive(clk, dt, ((0, 1), (1, 1), (0, 1), (1, 1)))
    assert steps == []
    knob.close()


def test_gpio_knob_invert(factory):
    knob, steps, clk, dt = make_knob(factory, knob_invert=True)
    clockwise(clk, dt)
    assert steps == [-1, -1]
    knob.close()


def test_gpio_knob_steps_per_detent(factory):
    knob, steps, clk, dt = make_knob(factory, knob_steps_per_detent=2)
    drive(clk, dt, ((0, 1), (0, 0)))
    assert steps == []
    drive(clk, dt, ((1, 0), (1, 1)))
    assert steps == [1]
    knob.close()

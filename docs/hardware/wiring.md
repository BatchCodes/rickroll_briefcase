# Wiring

This guide tells you how to connect the switches and the knob to the Raspberry Pi. The controller container reads these parts through the GPIO pins. It then plays, pauses or selects the video. The power bank, the monitor and the HDMI cable are also in this guide.

All supported boards have the same 40-pin GPIO header, so the GPIO wiring is the same on each board. The boards are different in the power input, the HDMI connector and the power switch support. Each board has its own section below.

![Wiring diagram for the Raspberry Pi 4, Pi 5 and Pi Zero 2 W](../images/wiring.svg)

Fig 1. The GPIO connections on the left are the same for all supported boards. The sketches on the right show each board turned so that the GPIO header is on the right, with pin 1 at the top. The red connector is the monitor port.

## Supported Boards

| Board                                           | Power input                   | Monitor connector  | Power switch without the latch |
| ----------------------------------------------- | ----------------------------- | ------------------ | ------------------------------ |
| [Raspberry Pi 4](#raspberry-pi-4)               | USB-C, 5 V 3 A                | micro-HDMI, HDMI 0 | yes                            |
| [Raspberry Pi 5](#raspberry-pi-5)               | USB-C, 5 V 5 A recommended    | micro-HDMI, HDMI 0 | no                             |
| [Raspberry Pi Zero 2 W](#raspberry-pi-zero-2-w) | micro-USB `PWR IN`, 5 V 2.5 A | mini-HDMI          | yes                            |

## Safety Rules

- Disconnect the power before you connect or disconnect a wire.
- Connect the `+` pin of a module to 3.3 V only. **Never connect 5 V to a GPIO pin or to a module that connects to a GPIO pin.** The GPIO pins operate at 3.3 V, and 5 V can damage the Pi.
- Find pin 1 before you connect a wire. Pin 1 has a square pad. It is at the end of the header that is farthest from the USB ports.
- Do not connect a GPIO pin directly to 3.3 V or to another GPIO pin.

## GPIO Connections

The pin numbers are the physical pin numbers on the 40-pin header. The GPIO numbers are the BCM numbers that the software uses. You can use any `GND` pin for a ground connection. The table gives the ground pins that the diagram uses.

| Part            | Part pin     | Pi pin | Pi signal | Required | `setup.sh` option                     |
| --------------- | ------------ | ------ | --------- | -------- | ------------------------------------- |
| Lid reed switch | `S`          | 11     | GPIO 17   | yes      | none                                  |
| Lid reed switch | `-`          | 9      | GND       | yes      | none                                  |
| Lid reed switch | `+`          | none   | none      | no       | none                                  |
| Arm switch      | contact 1    | 13     | GPIO 27   | yes      | none                                  |
| Arm switch      | contact 2    | 14     | GND       | yes      | none                                  |
| Power switch    | contact 1    | 5      | GPIO 3    | no       | `--power-switch` or `--power-latch`   |
| Power switch    | contact 2    | 6      | GND       | no       | `--power-switch` or `--power-latch`   |
| Power latch     | `OFF` inputs | 37     | GPIO 26   | no       | `--power-latch`                       |
| Power latch     | `GND`        | 39     | GND       | no       | `--power-latch`                       |
| Video knob      | `CLK`        | 15     | GPIO 22   | no       | `--knob`                              |
| Video knob      | `DT`         | 16     | GPIO 23   | no       | `--knob`                              |
| Video knob      | `SW`         | 18     | GPIO 24   | no       | none. The button has no function yet. |
| Video knob      | `+`          | 17     | 3.3 V     | no       | `--knob`                              |
| Video knob      | `GND`        | 20     | GND       | no       | `--knob`                              |

The controller turns on the internal pull-up resistor of each input pin. Thus a switch only connects its GPIO pin to ground. You do not need an external resistor.

## Lid Reed Switch

The KY-021 module has a reed switch between `S` and `-`. A magnet near the switch closes it. Put the module in the case body and the magnet in the lid, so that the magnet is near the module when the lid is closed.

Leave the `+` pin unconnected. The module has a resistor from `+` to `S`, and the internal pull-up of the Pi does the same work. If you connect `+`, connect it to 3.3 V on pin 1 or pin 17. Never connect it to 5 V.

With the default wiring, the lid is closed when GPIO 17 is low. Some sensors are open when the magnet is near. For such a sensor, run `setup.sh --lid-closed-when-high`.

## Arm Switch

The arm switch is a toggle switch on the outside of the case. When the switch is closed, the briefcase is armed. To invert the switch, set `BRIEFCASE_ARMED_WHEN_LOW=false` in `.env`. Refer to the [configuration reference](../software/configuration.md).

## Power Switch

The power switch is optional. It connects GPIO 3 to ground when it is on. When a person turns it off for 2 s, the Pi shuts down cleanly. `setup.sh` turns off I2C, because I2C also uses GPIO 3.

- Without the power latch (`--power-switch`), the switch halts the Pi, and the switch wakes the halted Pi again. The halted Pi still draws some power. A Pi 5 does not wake from halt on GPIO 3, so this mode is not available on a Pi 5.
- With the power latch (`--power-latch`), GPIO 26 also signals the latch at the end of the shutdown, and the latch disconnects the power. This mode operates on all supported boards.

**The power latch circuit is not final.** The diagram shows only the connections between the Pi and the latch `OFF` inputs.

## Video Knob

The KY-040 module is a rotary encoder. It selects the next or the previous video while the briefcase is disarmed. Connect its `+` pin to 3.3 V on pin 17. The module has pull-up resistors to `+`, so 5 V on `+` puts 5 V on the GPIO pins.

If one click moves two videos, set `BRIEFCASE_KNOB_STEPS_PER_DETENT=2` in `.env`. If the knob turns the wrong way, set `BRIEFCASE_KNOB_INVERT=true`, or swap the `CLK` and `DT` wires.

## Power and Monitor

The power bank has two USB-C outputs. Connect one output to the Pi and the other output to the monitor. Connect the Pi to the monitor with an HDMI cable. The board sections give the correct cable and port for each board. The monitor plays the sound through HDMI.

![System overview](../images/system_overview.svg)

## Raspberry Pi 4

The Raspberry Pi 4 is the primary test board of the briefcase.

| Connector                                      | Connect to                                      |
| ---------------------------------------------- | ----------------------------------------------- |
| USB-C power input                              | a USB-C output of the power bank. Use 5 V 3 A.  |
| micro-HDMI port HDMI 0, next to the USB-C port | the monitor, with a micro-HDMI to HDMI cable.   |
| micro-HDMI port HDMI 1                         | nothing.                                        |
| 3.5 mm audio jack                              | the optional amplifier, if you add one.         |
| Ethernet                                       | your router, to update the software (optional). |

The Pi 4 wakes from halt when GPIO 3 goes low. Thus you can use the power switch before you have the power latch. Use `--power-switch` for the switch alone, and `--power-latch` when the latch is fitted.

`setup.sh --power-switch` checks the bootloader setting `WAKE_ON_GPIO`. If it is `0`, the script shows a warning. Then run `sudo rpi-eeprom-config --edit` and set `WAKE_ON_GPIO=1`.

## Raspberry Pi 5

The Raspberry Pi 5 is a supported board.

| Connector                                      | Connect to                                    |
| ---------------------------------------------- | --------------------------------------------- |
| USB-C power input                              | a USB-C output of the power bank.             |
| micro-HDMI port HDMI 0, next to the USB-C port | the monitor, with a micro-HDMI to HDMI cable. |
| micro-HDMI port HDMI 1                         | nothing.                                      |

The Pi 5 has no 3.5 mm audio jack. The sound goes through HDMI to the monitor.

HDMI 1 also works. `setup.sh` finds the port that has the monitor and sends the picture and the sound to that port. Connect the monitor and turn it on before you run `setup.sh`. If you move the cable to the other port later, run `setup.sh` again.

The Pi 5 asks for a 5 V 5 A supply. A normal USB-C power bank gives 5 V 3 A. With 3 A, the Pi 5 can show a warning, and it limits the current of its USB ports. The briefcase does not use the USB ports, so it operates with 3 A.

**A Pi 5 does not wake from halt when GPIO 3 goes low.** Only its power button wakes it. Thus the power switch alone could shut the Pi down, but it could not start it again. `setup.sh` refuses `--power-switch` on a Pi 5. Use the power switch only with the power latch, with `--power-latch`. The latch applies the power, and a Pi 5 starts when it gets power. Until the latch is fitted, do not connect the power switch.

## Raspberry Pi Zero 2 W

The Raspberry Pi Zero 2 W is a supported board for lower power.

| Connector               | Connect to                                                                        |
| ----------------------- | --------------------------------------------------------------------------------- |
| micro-USB port `PWR IN` | a USB-C output of the power bank, with a USB-C to micro-USB cable. Use 5 V 2.5 A. |
| micro-USB port `USB`    | nothing. This is the data port. It does not power the board well.                 |
| mini-HDMI port          | the monitor, with a mini-HDMI to HDMI cable.                                      |

The Zero 2 W has no 3.5 mm audio jack. The sound goes through HDMI to the monitor.

Many Zero 2 W boards have no header pins. Solder a 2×20 male header to the board, or buy the Zero 2 WH, which has the header fitted. The header has the same pin layout as the Pi 4 and the Pi 5.

The Zero 2 W wakes from halt when GPIO 3 goes low. Thus you can use the power switch before you have the power latch. Use `--power-switch` for the switch alone, and `--power-latch` when the latch is fitted.

The Zero 2 W has 512 MB of memory and decodes H.264 only. Use H.264 videos at 1080p30 or less. The [transcode script](../../tools/transcode.sh) makes such a file.

## Set Up Command

Run `setup.sh` with the options for the parts that you connected. For example, on a Pi 4 or a Zero 2 W with the knob and the power switch:

```bash
sudo ~/rickroll_briefcase/scripts/setup.sh --knob --power-switch
```

On a Pi 5, use `--power-latch` instead of `--power-switch`, and only when the latch is fitted.

## Diagram Source

[wiring_diagrams.py](../../tools/wiring_diagrams.py) makes the wiring diagram. After you change it, run this command from the repository root:

```bash
python3 tools/wiring_diagrams.py
```

## See also

- [Configuration](../software/configuration.md)
- [Architecture](../software/architecture.md)
- [Video and diagram tools](../../tools/README.md)

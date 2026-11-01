"""Make the power latch diagram docs/images/power_latch.svg.

Two Pololu power switches cut the VBUS wire of the Pi cable and of the monitor
cable. The other cable wires stay connected. Run it from the repository root:

    python3 tools/latch_diagram.py
"""

from __future__ import annotations

from pathlib import Path

from wiring_diagrams import (
    BACKGROUND,
    GROUND,
    LATCH,
    MUTED,
    POWER_3V3,
    POWER_SWITCH,
    TEXT,
    component,
    text,
    wire,
)

OUTPUT_FILE = (
    Path(__file__).resolve().parent.parent / "docs" / "images" / "power_latch.svg"
)

WIDTH = 900
HEIGHT = 640
VBUS = POWER_3V3
ON_PULSE = "#8c564b"


def dot(x: float, y: float, colour: str) -> str:
    return f'<circle cx="{x:g}" cy="{y:g}" r="4" fill="{colour}"/>'


def boxes() -> str:
    return "".join(
        [
            component(40, 100, 170, 300, "Power bank", ["Anker 737"], TEXT),
            text(200, 144, "USB-C 1", 11, MUTED, anchor="end"),
            text(200, 324, "USB-C 2", 11, MUTED, anchor="end"),
            component(330, 100, 170, 110, "Power latch 1: Pi", [], LATCH),
            component(330, 290, 170, 110, "Power latch 2: monitor", [], LATCH),
            component(640, 100, 230, 170, "Raspberry Pi", ["USB-C power in"], TEXT),
            text(650, 194, "pin 5, GPIO 3", 11, MUTED),
            text(650, 239, "pin 37, GPIO 26", 11, MUTED),
            component(640, 290, 230, 70, "Monitor", ["USB-C power in"], TEXT),
            component(640, 440, 230, 120, "Power switch", ["2-pole toggle switch"], POWER_SWITCH),
            text(650, 494, "pole 1", 11, MUTED),
            text(650, 544, "pole 2", 11, MUTED),
            component(
                300, 470, 230, 110, "ON pulse",
                [
                    "C1 1 µF from pole 2 to ON",
                    "R1 100 kΩ from ON to GND",
                    "R2 1 MΩ from pole 2 to GND",
                    "D1 BAT85, cathode to ON",
                ],
                ON_PULSE,
            ),
        ]
    )  # fmt: skip


def latch_pins() -> str:
    labels = []
    for top in (100, 290):
        labels += [
            text(336, top + 44, "VIN", 10, MUTED),
            text(336, top + 84, "GND", 10, MUTED),
            text(494, top + 44, "VOUT", 10, MUTED, anchor="end"),
            text(380, top + 104, "ON", 10, MUTED, anchor="middle"),
            text(450, top + 104, "OFF", 10, MUTED, anchor="middle"),
        ]
    return "".join(labels)


def wires() -> str:
    return "".join(
        [
            # Each cable: only VBUS goes through the latch.
            wire([(210, 155), (240, 155), (240, 85), (610, 85), (610, 150), (640, 150)], MUTED, dashed=True),
            wire([(210, 335), (240, 335), (240, 270), (610, 270), (610, 330), (640, 330)], MUTED, dashed=True),
            wire([(330, 180), (255, 180), (255, 85)], GROUND),
            wire([(330, 370), (255, 370), (255, 270)], GROUND),
            wire([(210, 140), (330, 140)], VBUS),
            wire([(500, 140), (640, 140)], VBUS),
            wire([(210, 320), (330, 320)], VBUS),
            wire([(500, 320), (640, 320)], VBUS),
            # Pole 2 takes 5 V from the Pi line, before the latch.
            wire([(290, 140), (290, 610), (620, 610), (620, 540), (640, 540)], VBUS),
            wire([(640, 520), (560, 520), (560, 525), (530, 525)], ON_PULSE),
            # The ON pulse goes to both ON inputs.
            wire([(380, 470), (380, 400)], ON_PULSE),
            wire([(380, 210), (380, 250), (315, 250), (315, 440), (380, 440)], ON_PULSE),
            # GPIO 26 goes to both OFF inputs.
            wire([(450, 400), (450, 440), (590, 440), (590, 235), (640, 235)], LATCH),
            wire([(450, 210), (450, 250), (520, 250), (520, 440)], LATCH),
            # Pole 1 connects GPIO 3 to ground.
            wire([(640, 190), (625, 190), (625, 470), (640, 470)], POWER_SWITCH),
            wire([(640, 490), (600, 490)], GROUND),
        ]
    )  # fmt: skip


def labels() -> str:
    return "".join(
        [
            text(218, 132, "VBUS: cut", 11, VBUS),
            text(262, 78, "CC, GND, D+ and D−: not cut", 11, MUTED),
            text(262, 263, "CC, GND, D+ and D−: not cut", 11, MUTED),
            text(596, 494, "GND", 11, TEXT, anchor="end"),
            text(586, 460, "R3 10 kΩ in series, R4 100 kΩ to GND", 10, MUTED, anchor="end"),
            dot(290, 140, VBUS),
            dot(255, 85, GROUND),
            dot(255, 270, GROUND),
            dot(380, 440, ON_PULSE),
            dot(520, 440, LATCH),
        ]
    )  # fmt: skip


def render() -> str:
    return "\n".join(
        [
            (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {HEIGHT}" '
            f'width="{WIDTH}" height="{HEIGHT}" font-family="Helvetica, Arial, '
            f'sans-serif">'),
            "  <title>Power latch wiring for the Rickroll Briefcase</title>",
            f'  <rect x="0" y="0" width="{WIDTH}" height="{HEIGHT}" fill="{BACKGROUND}"/>',
            "  " + text(40, 40, "Power latch wiring", 22, TEXT, weight="bold"),
            "  "
            + text(
                40, 62, "Two Pololu Big Pushbutton Power Switch MP boards in the VBUS "
                "wires of two cut USB-C cables", 12, MUTED,
            ),
            "  " + boxes(),
            "  " + wires(),
            "  " + latch_pins(),
            "  " + labels(),
            "</svg>",
            "",
        ]
    )  # fmt: skip


def main() -> None:
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(render(), encoding="utf-8")
    print(f"Wrote {OUTPUT_FILE}")


if __name__ == "__main__":
    main()

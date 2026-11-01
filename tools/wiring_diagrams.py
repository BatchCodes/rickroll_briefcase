"""Make the wiring diagram docs/images/wiring.svg for the supported Raspberry Pis.

All supported boards have the same 40-pin GPIO header, so the diagram shows the
pin connections once. A sketch of each board shows where its header and its
connectors are. Run it from the repository root:

    python3 tools/wiring_diagrams.py
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from xml.sax.saxutils import escape

OUTPUT_FILE = Path(__file__).resolve().parent.parent / "docs" / "images" / "wiring.svg"

WIDTH = 900
HEIGHT = 760
PITCH = 22
ROW1_Y = 180
LEFT_PIN_X = 430
RIGHT_PIN_X = 456

# The 40-pin header, by physical pin number.
PIN_NAMES = {
    1: "3.3 V", 2: "5 V", 3: "GPIO 2", 4: "5 V", 5: "GPIO 3", 6: "GND",
    7: "GPIO 4", 8: "GPIO 14", 9: "GND", 10: "GPIO 15", 11: "GPIO 17",
    12: "GPIO 18", 13: "GPIO 27", 14: "GND", 15: "GPIO 22", 16: "GPIO 23",
    17: "3.3 V", 18: "GPIO 24", 19: "GPIO 10", 20: "GND", 21: "GPIO 9",
    22: "GPIO 25", 23: "GPIO 11", 24: "GPIO 8", 25: "GND", 26: "GPIO 7",
    27: "ID_SD", 28: "ID_SC", 29: "GPIO 5", 30: "GND", 31: "GPIO 6",
    32: "GPIO 12", 33: "GPIO 13", 34: "GND", 35: "GPIO 19", 36: "GPIO 16",
    37: "GPIO 26", 38: "GPIO 20", 39: "GND", 40: "GPIO 21",
}  # fmt: skip

BACKGROUND = "#f6f6f6"
TEXT = "#111111"
MUTED = "#555555"
GROUND = "#222222"
POWER_3V3 = "#d62728"
LID = "#1f77b4"
ARM = "#2ca02c"
POWER_SWITCH = "#d08a00"
LATCH = "#17868f"
KNOB = "#7b3fbf"
ACCENT = "#c51a4a"


@dataclass
class Connector:
    label: str
    centre_mm: float
    length_mm: float
    highlight: bool = False


@dataclass
class Board:
    name: str
    width_mm: float
    height_mm: float
    header_start_mm: float
    connectors: list[Connector]
    far_edge_label: str


BOARDS = [
    Board(
        name="Raspberry Pi 4",
        width_mm=85,
        height_mm=56,
        header_start_mm=7.1,
        connectors=[
            Connector("USB-C power in", 11.2, 9),
            Connector("HDMI 0: monitor", 26.0, 7, highlight=True),
            Connector("HDMI 1: not used", 39.5, 7),
            Connector("3.5 mm audio", 53.5, 6),
        ],
        far_edge_label="USB and Ethernet",
    ),
    Board(
        name="Raspberry Pi 5",
        width_mm=85,
        height_mm=56,
        header_start_mm=7.1,
        connectors=[
            Connector("USB-C power in", 11.2, 9),
            Connector("HDMI 0: monitor", 25.8, 7, highlight=True),
            Connector("HDMI 1: not used", 39.2, 7),
        ],
        far_edge_label="USB and Ethernet",
    ),
    Board(
        name="Raspberry Pi Zero 2 W",
        width_mm=65,
        height_mm=30,
        header_start_mm=7.1,
        connectors=[
            Connector("mini-HDMI: monitor", 12.4, 11, highlight=True),
            Connector("micro-USB data", 41.4, 8),
            Connector("micro-USB PWR IN", 54.0, 8),
        ],
        far_edge_label="",
    ),
]

# The top of each board sketch.
BOARD_TOPS = (222, 410, 598)
BOARD_SCALE = 1.8


def row_y(pin: int) -> float:
    return ROW1_Y + ((pin + 1) // 2 - 1) * PITCH


def pin_x(pin: int) -> float:
    return LEFT_PIN_X if pin % 2 else RIGHT_PIN_X


def text(x, y, content, size=12, colour=TEXT, anchor="start", weight="normal"):
    return (
        f'<text x="{x:g}" y="{y:g}" font-size="{size}" fill="{colour}" '
        f'text-anchor="{anchor}" font-weight="{weight}">{escape(content)}</text>'
    )


def wire(points, colour, dashed=False):
    """A wire with a wide background underlay, so crossings show a gap."""
    path = " ".join(
        f"{'M' if index == 0 else 'L'}{x:g},{y:g}"
        for index, (x, y) in enumerate(points)
    )
    dash = ' stroke-dasharray="6 4"' if dashed else ""
    return (
        f'<path d="{path}" stroke="{BACKGROUND}" stroke-width="7" fill="none"/>'
        f'<path d="{path}" stroke="{colour}" stroke-width="2.5" fill="none" '
        f'stroke-linejoin="round"{dash}/>'
    )


def component(x, y, width, height, title, subtitle, colour, dashed=False):
    dash = ' stroke-dasharray="6 4"' if dashed else ""
    parts = [
        (
            f'<rect x="{x}" y="{y}" width="{width}" height="{height}" rx="8" '
            f'fill="#ffffff" stroke="{colour}" stroke-width="2"{dash}/>'
        ),
        text(x + 10, y + 22, title, 13, TEXT, weight="bold"),
    ]
    for index, line in enumerate(subtitle):
        parts.append(text(x + 10, y + 40 + index * 15, line, 11, MUTED))
    return "".join(parts)


# Each connection: (pin, colour, points from the pin to the component, dashed).
def connections() -> list[tuple[int, str, list[tuple[float, float]], bool]]:
    left = LEFT_PIN_X
    right = RIGHT_PIN_X
    return [
        # Power switch above the header.
        (5, POWER_SWITCH, [(left, row_y(5)), (322, row_y(5)), (322, 118), (340, 118)], False),
        (6, GROUND, [(right, row_y(6)), (556, row_y(6)), (556, 118), (540, 118)], False),
        # Lid reed switch on the left.
        (9, GROUND, [(left, row_y(9)), (240, row_y(9))], False),
        (11, LID, [(left, row_y(11)), (240, row_y(11))], False),
        # Arm switch on the left.
        (13, ARM, [(left, row_y(13)), (270, row_y(13)), (270, 400), (240, 400)], False),
        # Pin 14 is on the other side, so the wire goes round below the knob.
        (
            14,
            GROUND,
            [
                (right, row_y(14)),
                (604, row_y(14)),
                (604, 736),
                (286, 736),
                (286, 444),
                (240, 444),
            ],
            False,
        ),
        # Power latch OFF input on the left.
        (37, LATCH, [(left, row_y(37)), (240, row_y(37))], True),
        (39, GROUND, [(left, row_y(39)), (240, row_y(39))], True),
        # Knob below the header.
        (17, POWER_3V3, [(left, row_y(17)), (310, row_y(17)), (310, 660), (360, 660)], False),
        (15, KNOB, [(left, row_y(15)), (298, row_y(15)), (298, 690), (360, 690)], False),
        (20, GROUND, [(right, row_y(20)), (568, row_y(20)), (568, 656), (520, 656)], False),
        (18, KNOB, [(right, row_y(18)), (580, row_y(18)), (580, 680), (520, 680)], True),
        (16, KNOB, [(right, row_y(16)), (592, row_y(16)), (592, 704), (520, 704)], False),
    ]  # fmt: skip


def header(used: dict[int, str]) -> str:
    top = row_y(1) - 14
    bottom = row_y(39) + 14
    parts = [
        (
            f'<rect x="418" y="{top}" width="50" height="{bottom - top}" rx="4" '
            f'fill="#2b2b2b"/>'
        )
    ]
    for pin in range(1, 41):
        x, y = pin_x(pin), row_y(pin)
        colour = used.get(pin)
        fill = colour or "#9a9a9a"
        if pin == 1:
            parts.append(
                f'<rect x="{x - 8}" y="{y - 8}" width="16" height="16" fill="{fill}" '
                f'stroke="#ffffff" stroke-width="1"/>'
            )
        else:
            parts.append(
                f'<circle cx="{x}" cy="{y}" r="8" fill="{fill}" stroke="#ffffff" '
                f'stroke-width="1"/>'
            )
        parts.append(text(x, y + 3.5, str(pin), 8, "#ffffff", "middle", "bold"))
        name = PIN_NAMES[pin]
        name_colour = TEXT if colour else "#8a8a8a"
        weight = "bold" if colour else "normal"
        label_width = len(name) * 7 + 6
        label_x = 411 - label_width if pin % 2 else 475
        if colour:
            # Hide the wire behind the label of a used pin.
            parts.append(
                f'<rect x="{label_x}" y="{y - 8}" width="{label_width}" height="16" '
                f'fill="{BACKGROUND}"/>'
            )
        if pin % 2:
            parts.append(text(408, y + 4, name, 11, name_colour, "end", weight))
        else:
            parts.append(text(478, y + 4, name, 11, name_colour, "start", weight))
    return "".join(parts)


def components() -> str:
    power_note = ["optional: --power-switch or", "--power-latch. Pi 5: latch only."]
    parts = [
        component(340, 72, 200, 72, "Power switch", power_note, POWER_SWITCH),
        component(40, 238, 200, 84, "Lid reed switch", ["KY-021 module", "+ not connected"], LID),
        text(232, row_y(9) + 4, "–", 12, TEXT, "end", "bold"),
        text(232, row_y(11) + 4, "S", 12, TEXT, "end", "bold"),
        component(40, 370, 200, 96, "Arm switch", ["toggle switch,", "closed = armed"], ARM),
        component(40, 544, 200, 84, "Power latch", ["OFF inputs, optional.", "The latch circuit is", "not final yet."], LATCH, dashed=True),
        text(232, row_y(37) + 4, "OFF", 11, TEXT, "end", "bold"),
        text(232, row_y(39) + 4, "GND", 11, TEXT, "end", "bold"),
        (f'<rect x="360" y="634" width="160" height="86" rx="8" fill="#ffffff" '
        f'stroke="{KNOB}" stroke-width="2"/>'),
        text(440, 674, "Video knob", 13, TEXT, "middle", "bold"),
        text(440, 690, "KY-040", 11, MUTED, "middle"),
        text(368, 664, "+", 11, TEXT, weight="bold"),
        text(368, 694, "CLK", 11, TEXT, weight="bold"),
        text(512, 660, "GND", 11, TEXT, "end", "bold"),
        text(512, 684, "SW", 11, TEXT, "end", "bold"),
        text(512, 708, "DT", 11, TEXT, "end", "bold"),
    ]  # fmt: skip
    return "".join(parts)


def legend() -> str:
    x, y = 40, 676
    items = [
        (POWER_3V3, False, "3.3 V, never 5 V"),
        (GROUND, False, "ground (any GND pin works)"),
        (KNOB, False, "signal, in the colour of its part"),
        (MUTED, True, "optional"),
    ]
    parts = []
    for index, (colour, dashed, label) in enumerate(items):
        line_y = y + index * 18
        dash = ' stroke-dasharray="6 4"' if dashed else ""
        parts.append(
            f'<path d="M{x},{line_y} L{x + 30},{line_y}" stroke="{colour}" '
            f'stroke-width="2.5"{dash}/>'
        )
        parts.append(text(x + 38, line_y + 4, label, 11, MUTED))
    return "".join(parts)


def board_sketch(board: Board, y0: float) -> str:
    """The board turned so that the GPIO header is on the right, pin 1 at the top."""
    scale = BOARD_SCALE
    width = board.height_mm * scale
    height = board.width_mm * scale
    x0 = WIDTH - 26 - width
    parts = [
        text(615, y0 - 8, board.name, 12, TEXT, weight="bold"),
        (
            f'<rect x="{x0:g}" y="{y0}" width="{width:g}" height="{height:g}" rx="6" '
            f'fill="#2f7d4a" stroke="#1d5531" stroke-width="2"/>'
        ),
    ]
    header_x = x0 + width - 6.5 * scale
    header_top = y0 + board.header_start_mm * scale
    header_height = 50.8 * scale
    parts.append(
        f'<rect x="{header_x:g}" y="{header_top:g}" width="{5 * scale:g}" '
        f'height="{header_height:g}" fill="#2b2b2b"/>'
    )
    parts.append(
        f'<rect x="{header_x + 0.3:g}" y="{header_top + 0.3:g}" width="5" height="5" '
        f'fill="{ACCENT}"/>'
    )
    parts.append(
        text(x0 + width / 2 - 4, header_top + 10, "pin 1", 9, "#ffffff", "middle")
    )
    parts.append(
        text(
            x0 + width / 2 - 4, header_top + header_height / 2, "GPIO", 9, "#ffffff",
            "middle",
        )
    )  # fmt: skip
    for connector in board.connectors:
        centre = y0 + connector.centre_mm * scale
        length = connector.length_mm * scale
        colour = ACCENT if connector.highlight else "#b8b8b8"
        parts.append(
            f'<rect x="{x0 - 5:g}" y="{centre - length / 2:g}" width="13" '
            f'height="{length:g}" rx="2" fill="{colour}" stroke="#555555"/>'
        )
        weight = "bold" if connector.highlight else "normal"
        parts.append(
            text(x0 - 10, centre + 4, connector.label, 11, TEXT, "end", weight)
        )
    if board.far_edge_label:
        parts.append(
            text(x0 + width / 2, y0 + height - 7, board.far_edge_label, 9, "#ffffff",
                 "middle")
        )  # fmt: skip
    return "".join(parts)


def render() -> str:
    used: dict[int, str] = {}
    wires = []
    # Straight wires first, then the routed ones, so these bridge over them.
    for pin, colour, points, dashed in sorted(connections(), key=lambda c: len(c[2])):
        used[pin] = colour
        wires.append(wire(points, colour, dashed))
    sketches = "".join(
        board_sketch(board, top) for board, top in zip(BOARDS, BOARD_TOPS, strict=True)
    )
    return "\n".join(
        [
            (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {HEIGHT}" '
            f'width="{WIDTH}" height="{HEIGHT}" font-family="Helvetica, Arial, '
            f'sans-serif">'),
            "  <title>Raspberry Pi wiring for the Rickroll Briefcase</title>",
            f'  <rect x="0" y="0" width="{WIDTH}" height="{HEIGHT}" fill="{BACKGROUND}"/>',
            "  " + text(40, 40, "Raspberry Pi wiring", 22, TEXT, weight="bold"),
            "  "
            + text(
                40, 62, "Pi 4, Pi 5 and Pi Zero 2 W: the same 40-pin GPIO header, "
                "seen from above, pin 1 at the top", 12, MUTED,
            ),
            "  " + "".join(wires),
            "  " + header(used),
            "  " + components(),
            "  " + legend(),
            "  " + text(615, 184, "The boards, turned to match", 13, TEXT, weight="bold"),
            "  " + sketches,
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

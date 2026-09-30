"""Runtime configuration from environment variables.

These values describe the installation (paths, pins, backends). They do not
change at runtime. User settings that the web app changes live in
``settings.py`` instead.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

InputBackend = Literal["gpio", "simulated"]
DisplayBackend = Literal["none", "command"]
NetworkBackendName = Literal["none", "nmcli", "simulated"]

ENV_PREFIX = "BRIEFCASE_"


def _env(name: str, default: str) -> str:
    return os.environ.get(ENV_PREFIX + name, default)


def _env_bool(name: str, default: bool) -> bool:
    value = _env(name, "true" if default else "false").strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{ENV_PREFIX}{name} must be true or false, not {value!r}")


@dataclass(frozen=True)
class AppConfig:
    videos_dir: Path = Path("/data/videos")
    config_dir: Path = Path("/data/config")
    mpv_socket: Path = Path("/run/briefcase/mpv.sock")
    input_backend: InputBackend = "gpio"
    lid_pin: int = 17
    arm_pin: int = 27
    lid_closed_when_low: bool = True
    armed_when_low: bool = True
    debounce_sec: float = 0.05
    display_backend: DisplayBackend = "none"
    display_off_command: str = ""
    display_on_command: str = ""
    http_host: str = "0.0.0.0"
    http_port: int = 8080
    max_upload_bytes: int = 4 * 1024**3
    network_backend: NetworkBackendName = "none"
    hotspot_connection: str = "briefcase-hotspot"
    wifi_interface: str = "wlan0"
    network_fallback_sec: float = 60.0

    @property
    def settings_path(self) -> Path:
        return self.config_dir / "settings.json"

    @classmethod
    def from_env(cls) -> AppConfig:
        input_backend = _env("INPUT_BACKEND", "gpio")
        if input_backend not in ("gpio", "simulated"):
            raise ValueError(
                f"{ENV_PREFIX}INPUT_BACKEND must be gpio or simulated, "
                f"not {input_backend!r}"
            )
        display_backend = _env("DISPLAY_BACKEND", "none")
        if display_backend not in ("none", "command"):
            raise ValueError(
                f"{ENV_PREFIX}DISPLAY_BACKEND must be none or command, "
                f"not {display_backend!r}"
            )
        network_backend = _env("NETWORK_BACKEND", "none")
        if network_backend not in ("none", "nmcli", "simulated"):
            raise ValueError(
                f"{ENV_PREFIX}NETWORK_BACKEND must be none, nmcli or simulated, "
                f"not {network_backend!r}"
            )
        return cls(
            videos_dir=Path(_env("VIDEOS_DIR", "/data/videos")),
            config_dir=Path(_env("CONFIG_DIR", "/data/config")),
            mpv_socket=Path(_env("MPV_SOCKET", "/run/briefcase/mpv.sock")),
            input_backend=input_backend,  # type: ignore[arg-type]
            lid_pin=int(_env("LID_PIN", "17")),
            arm_pin=int(_env("ARM_PIN", "27")),
            lid_closed_when_low=_env_bool("LID_CLOSED_WHEN_LOW", True),
            armed_when_low=_env_bool("ARMED_WHEN_LOW", True),
            debounce_sec=float(_env("DEBOUNCE_SEC", "0.05")),
            display_backend=display_backend,  # type: ignore[arg-type]
            display_off_command=_env("DISPLAY_OFF_COMMAND", ""),
            display_on_command=_env("DISPLAY_ON_COMMAND", ""),
            http_host=_env("HTTP_HOST", "0.0.0.0"),
            http_port=int(_env("HTTP_PORT", "8080")),
            max_upload_bytes=int(_env("MAX_UPLOAD_BYTES", str(4 * 1024**3))),
            network_backend=network_backend,  # type: ignore[arg-type]
            hotspot_connection=_env("HOTSPOT_CONNECTION", "briefcase-hotspot"),
            wifi_interface=_env("WIFI_INTERFACE", "wlan0"),
            network_fallback_sec=float(_env("NETWORK_FALLBACK_SEC", "60")),
        )

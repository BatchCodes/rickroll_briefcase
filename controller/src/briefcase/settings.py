"""User settings that the web app changes, with defaults and atomic storage."""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
import threading
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError, field_validator

LOGGER = logging.getLogger(__name__)

DEFAULT_START_SEC = 30.0
DEFAULT_VOLUME = 80
TIME_PATTERN = re.compile(r"^(?:(?P<h>\d+):)?(?P<m>\d+):(?P<s>\d+(?:\.\d+)?)$")


class SelectionMode(StrEnum):
    SINGLE = "single"
    CYCLE = "cycle"
    SHUFFLE = "shuffle"


class StartMode(StrEnum):
    FIXED = "fixed"
    BEGINNING = "beginning"
    RANDOM = "random"
    RESUME = "resume"


class EndAction(StrEnum):
    LOOP = "loop"
    STOP = "stop"


def parse_time(value: str | float | int) -> float:
    """Convert ``"1:02:03"``, ``"00:30"`` or ``30`` to seconds."""
    if isinstance(value, int | float):
        seconds = float(value)
    else:
        text = value.strip()
        match = TIME_PATTERN.match(text)
        if match:
            hours = int(match.group("h") or 0)
            seconds = (
                hours * 3600 + int(match.group("m")) * 60 + float(match.group("s"))
            )
        else:
            try:
                seconds = float(text)
            except ValueError as error:
                raise ValueError(
                    f"{value!r} is not a time. Use seconds or mm:ss, for example 00:30."
                ) from error
    if seconds < 0:
        raise ValueError("A time must not be negative.")
    return seconds


def format_time(seconds: float) -> str:
    whole = int(seconds)
    fraction = seconds - whole
    hours, rest = divmod(whole, 3600)
    minutes, secs = divmod(rest, 60)
    text = f"{minutes:02d}:{secs:02d}"
    if hours:
        text = f"{hours}:{text}"
    if fraction >= 0.001:
        text += f"{fraction:.3f}"[1:]
    return text


class VideoSettings(BaseModel):
    """Per-video settings. ``None`` means "use the global default"."""

    start_mode: StartMode = StartMode.FIXED
    start_sec: float | None = None
    cue_points_sec: list[float] = Field(default_factory=list)
    end_action: EndAction = EndAction.LOOP
    resume_sec: float = 0.0

    @field_validator("start_sec", mode="before")
    @classmethod
    def _parse_start(cls, value: object) -> object:
        if value is None or value == "":
            return None
        return parse_time(value)  # type: ignore[arg-type]

    @field_validator("cue_points_sec", mode="before")
    @classmethod
    def _parse_cues(cls, value: object) -> object:
        if isinstance(value, str):
            value = [part for part in re.split(r"[,\s]+", value) if part]
        if isinstance(value, list):
            return sorted({parse_time(item) for item in value})
        return value


class Settings(BaseModel):
    selection_mode: SelectionMode = SelectionMode.SINGLE
    armed_video: str | None = None
    default_start_sec: float = DEFAULT_START_SEC
    volume: int = Field(default=DEFAULT_VOLUME, ge=0, le=100)
    videos: dict[str, VideoSettings] = Field(default_factory=dict)

    @field_validator("default_start_sec", mode="before")
    @classmethod
    def _parse_default_start(cls, value: object) -> object:
        return parse_time(value)  # type: ignore[arg-type]

    def video(self, name: str) -> VideoSettings:
        return self.videos.get(name, VideoSettings())

    def start_sec_for(self, name: str) -> float:
        video = self.video(name)
        if video.start_sec is None:
            return self.default_start_sec
        return video.start_sec


class SettingsStore:
    """Load and save ``settings.json``.

    Writes go to a temporary file in the same directory, then ``os.replace``
    moves it into place. A power loss during a write leaves the old file or
    the new file, never a partial file.
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.Lock()
        self._settings = self._load()

    @property
    def path(self) -> Path:
        return self._path

    def get(self) -> Settings:
        with self._lock:
            return self._settings.model_copy(deep=True)

    def replace(self, settings: Settings) -> Settings:
        with self._lock:
            self._write(settings)
            self._settings = settings.model_copy(deep=True)
            return self._settings.model_copy(deep=True)

    def update_video(self, name: str, video: VideoSettings) -> Settings:
        settings = self.get()
        settings.videos[name] = video
        return self.replace(settings)

    def reset(self) -> Settings:
        return self.replace(Settings())

    def _load(self) -> Settings:
        if not self._path.exists():
            return Settings()
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            return Settings.model_validate(data)
        except (OSError, json.JSONDecodeError, ValidationError) as error:
            broken = self._path.with_suffix(".json.broken")
            LOGGER.error(
                "Cannot read %s (%s). Using defaults. The old file is now %s.",
                self._path,
                error,
                broken,
            )
            try:
                os.replace(self._path, broken)
            except OSError:
                LOGGER.exception("Cannot move the broken settings file")
            return Settings()

    def _write(self, settings: Settings) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = settings.model_dump_json(indent=2) + "\n"
        file_descriptor, temp_name = tempfile.mkstemp(
            dir=self._path.parent, prefix=".settings.", suffix=".tmp"
        )
        try:
            with os.fdopen(file_descriptor, "w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, self._path)
            directory = os.open(self._path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        except BaseException:
            Path(temp_name).unlink(missing_ok=True)
            raise

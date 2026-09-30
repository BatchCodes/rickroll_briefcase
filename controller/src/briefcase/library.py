"""The video library: the video files in one directory."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import shutil
import subprocess
import tempfile
import unicodedata
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path

LOGGER = logging.getLogger(__name__)

VIDEO_EXTENSIONS = frozenset({".mp4", ".m4v", ".mkv", ".mov", ".webm", ".avi"})
MAX_NAME_LENGTH = 120
MAX_WIDTH = 1920
MAX_HEIGHT = 1080
MAX_FPS = 30.5
PROBE_TIMEOUT_SEC = 20


class LibraryError(ValueError):
    pass


@dataclass(frozen=True)
class VideoInfo:
    codec: str | None = None
    width: int | None = None
    height: int | None = None
    fps: float | None = None
    duration_sec: float | None = None
    warnings: list[str] = field(default_factory=list)


def sanitize_filename(name: str) -> str:
    """Make a safe file name, keep the extension and reject other file types."""
    base = Path(name).name
    normalized = unicodedata.normalize("NFKD", base)
    ascii_name = normalized.encode("ascii", "ignore").decode()
    stem = Path(ascii_name).stem
    suffix = Path(ascii_name).suffix.lower()
    if suffix not in VIDEO_EXTENSIONS:
        allowed = ", ".join(sorted(VIDEO_EXTENSIONS))
        raise LibraryError(f"{name!r} is not a video file. Use one of: {allowed}.")
    stem = re.sub(r"[^A-Za-z0-9._ -]+", "_", stem).strip(" ._-")
    if not stem:
        stem = "video"
    return stem[: MAX_NAME_LENGTH - len(suffix)] + suffix


def check_video_info(info: VideoInfo) -> VideoInfo:
    warnings = []
    if info.codec and info.codec.upper() not in {"AVC", "H264", "H.264"}:
        warnings.append(
            f"The video codec is {info.codec}. Use H.264: the Pi Zero 2 W "
            "cannot decode other codecs in hardware."
        )
    if (info.width or 0) > MAX_WIDTH or (info.height or 0) > MAX_HEIGHT:
        warnings.append(
            f"The resolution is {info.width}x{info.height}. "
            f"Use {MAX_WIDTH}x{MAX_HEIGHT} or less."
        )
    if (info.fps or 0) > MAX_FPS:
        warnings.append(f"The frame rate is {info.fps:g} fps. Use 30 fps or less.")
    return VideoInfo(
        codec=info.codec,
        width=info.width,
        height=info.height,
        fps=info.fps,
        duration_sec=info.duration_sec,
        warnings=warnings,
    )


def _number(value: object) -> float | None:
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None


def parse_mediainfo(output: str) -> VideoInfo:
    data = json.loads(output)
    tracks = data.get("media", {}).get("track", [])
    general = next((t for t in tracks if t.get("@type") == "General"), {})
    video = next((t for t in tracks if t.get("@type") == "Video"), {})
    width = _number(video.get("Width"))
    height = _number(video.get("Height"))
    return check_video_info(
        VideoInfo(
            codec=video.get("Format"),
            width=int(width) if width else None,
            height=int(height) if height else None,
            fps=_number(video.get("FrameRate")),
            duration_sec=_number(general.get("Duration")),
        )
    )


class Library:
    def __init__(self, videos_dir: Path) -> None:
        self._dir = videos_dir
        self._probe_cache: dict[tuple[str, float], VideoInfo | None] = {}

    @property
    def directory(self) -> Path:
        return self._dir

    def names(self) -> list[str]:
        if not self._dir.is_dir():
            return []
        return sorted(
            (
                entry.name
                for entry in self._dir.iterdir()
                if entry.is_file()
                and not entry.name.startswith(".")
                and entry.suffix.lower() in VIDEO_EXTENSIONS
            ),
            key=str.casefold,
        )

    def path(self, name: str) -> Path:
        if name != Path(name).name or name.startswith("."):
            raise LibraryError(f"{name!r} is not a valid video name.")
        path = self._dir / name
        if not path.is_file():
            raise LibraryError(f"The video {name!r} does not exist.")
        return path

    def _unique_name(self, name: str) -> str:
        candidate = name
        stem, suffix = Path(name).stem, Path(name).suffix
        counter = 2
        while (self._dir / candidate).exists():
            candidate = f"{stem}-{counter}{suffix}"
            counter += 1
        return candidate

    async def save_stream(
        self, filename: str, chunks: AsyncIterator[bytes], max_bytes: int
    ) -> str:
        """Write an upload to a hidden temporary file, then move it into place.

        A partial upload never shows in the library.
        """
        name = sanitize_filename(filename)
        self._dir.mkdir(parents=True, exist_ok=True)
        handle = tempfile.NamedTemporaryFile(  # noqa: SIM115
            dir=self._dir, prefix=".upload-", delete=False
        )
        temp_path = Path(handle.name)
        try:
            written = 0
            async for chunk in chunks:
                written += len(chunk)
                if written > max_bytes:
                    raise LibraryError(
                        f"The file is larger than {max_bytes // 1024**2} MB."
                    )
                await asyncio.to_thread(handle.write, chunk)
            await asyncio.to_thread(handle.close)
            if written == 0:
                raise LibraryError("The upload is empty.")
            final_name = self._unique_name(name)
            temp_path.replace(self._dir / final_name)
            return final_name
        except BaseException:
            handle.close()
            temp_path.unlink(missing_ok=True)
            raise

    def rename(self, old_name: str, new_name: str) -> str:
        source = self.path(old_name)
        target_name = sanitize_filename(new_name)
        if target_name == old_name:
            return old_name
        if (self._dir / target_name).exists():
            raise LibraryError(f"A video with the name {target_name!r} exists.")
        source.rename(self._dir / target_name)
        return target_name

    def delete(self, name: str) -> None:
        self.path(name).unlink()

    def probe(self, name: str) -> VideoInfo | None:
        path = self.path(name)
        key = (name, path.stat().st_mtime)
        if key in self._probe_cache:
            return self._probe_cache[key]
        info = self._run_probe(path)
        self._probe_cache[key] = info
        return info

    def _run_probe(self, path: Path) -> VideoInfo | None:
        executable = shutil.which("mediainfo")
        if executable is None:
            return None
        try:
            result = subprocess.run(
                [executable, "--Output=JSON", str(path)],
                capture_output=True,
                check=True,
                text=True,
                timeout=PROBE_TIMEOUT_SEC,
            )
            return parse_mediainfo(result.stdout)
        except (subprocess.SubprocessError, OSError, json.JSONDecodeError):
            LOGGER.exception("Cannot read the video information of %s", path)
            return None

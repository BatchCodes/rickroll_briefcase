"""The web app: an HTML page for a phone browser, and a JSON API."""

from __future__ import annotations

import hashlib
import shutil
from dataclasses import asdict
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field, ValidationError

from briefcase import __version__
from briefcase.config import AppConfig
from briefcase.controller import BriefcaseController, ControllerError
from briefcase.inputs import Inputs, SimulatedInputs
from briefcase.knob import Knob, SimulatedKnob
from briefcase.library import Library, LibraryError
from briefcase.network import Mode, NetworkController, NetworkError
from briefcase.power import PowerManager
from briefcase.settings import (
    SelectionMode,
    SettingsStore,
    VideoSettings,
    format_time,
    parse_time,
)
from briefcase.updates import UpdateError, UpdateManager

PACKAGE_DIR = Path(__file__).parent
RESERVED_FREE_BYTES = 200 * 1024**2


class GlobalSettingsUpdate(BaseModel):
    selection_mode: SelectionMode | None = None
    armed_video: str | None = None
    default_start: str | float | None = None
    volume: int | None = None
    resume_window: str | float | None = None


class VolumeRequest(BaseModel):
    volume: int = Field(ge=0, le=100)


class RenameRequest(BaseModel):
    new_name: str


class PlayRequest(BaseModel):
    active: bool


class PauseRequest(BaseModel):
    paused: bool


class SeekRequest(BaseModel):
    offset_sec: float | None = None
    position_sec: float | None = None


class UsePositionRequest(BaseModel):
    target: Literal["start", "cue"]


class ModeRequest(BaseModel):
    mode: Literal["hotspot", "client"]


class UpdateRequest(BaseModel):
    target: Literal["release", "prerelease", "main"] = "release"


class AddNetworkRequest(BaseModel):
    ssid: str
    password: str = ""


class SimulateRequest(BaseModel):
    lid_open: bool | None = None
    armed: bool | None = None
    power_on: bool | None = None
    knob: Literal[-1, 1] | None = None


def _asset_version(static_dir: Path) -> str:
    """Hash the static files, so a browser loads them again after an update."""
    digest = hashlib.sha256()
    for path in sorted(static_dir.iterdir()):
        if path.is_file():
            digest.update(path.name.encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()[:12]


def _bad_request(error: Exception) -> HTTPException:
    if isinstance(error, ValidationError):
        messages = "; ".join(item["msg"] for item in error.errors())
        return HTTPException(status_code=400, detail=messages)
    return HTTPException(status_code=400, detail=str(error))


def create_app(
    config: AppConfig,
    controller: BriefcaseController,
    library: Library,
    store: SettingsStore,
    inputs: Inputs,
    network: NetworkController | None = None,
    updates: UpdateManager | None = None,
    power: PowerManager | None = None,
    knob: Knob | None = None,
    lifespan: Any = None,
) -> FastAPI:
    network = network or NetworkController(None, 60)
    app = FastAPI(title="Briefcase", version=__version__, lifespan=lifespan)
    templates = Jinja2Templates(directory=str(PACKAGE_DIR / "templates"))
    app.mount(
        "/static", StaticFiles(directory=str(PACKAGE_DIR / "static")), name="static"
    )
    asset_version = _asset_version(PACKAGE_DIR / "static")

    def video_entry(name: str) -> dict[str, Any]:
        settings = store.get()
        video = settings.video(name)
        path = library.path(name)
        info = library.probe(name)
        return {
            "name": name,
            "size_bytes": path.stat().st_size,
            "settings": video.model_dump(mode="json"),
            "effective_start": format_time(settings.start_sec_for(name)),
            "info": asdict(info) if info else None,
        }

    def settings_payload() -> dict[str, Any]:
        settings = store.get()
        return {
            "selection_mode": settings.selection_mode.value,
            "armed_video": settings.armed_video,
            "default_start": format_time(settings.default_start_sec),
            "default_start_sec": settings.default_start_sec,
            "volume": settings.volume,
            "resume_window_sec": settings.resume_window_sec,
        }

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(
            request,
            "index.html",
            {"version": __version__, "asset_version": asset_version},
            headers={"Cache-Control": "no-cache"},
        )

    @app.get("/healthz")
    async def healthz() -> dict[str, Any]:
        return {"ok": True, "state": controller.state.value}

    @app.get("/api/status")
    async def status() -> dict[str, Any]:
        return await full_status()

    async def full_status() -> dict[str, Any]:
        data = (await controller.status_with_position()).to_dict()
        data["power"] = power.status() if power else {"state": "no_switch"}
        data["knob"] = {"enabled": knob is not None}
        data["volume"] = store.get().volume
        settings = store.get()
        names = library.names()
        if settings.armed_video in names:
            data["armed_video"] = settings.armed_video
        else:
            data["armed_video"] = names[0] if names else None
        return data

    @app.get("/api/settings")
    async def get_settings() -> dict[str, Any]:
        return settings_payload()

    @app.put("/api/settings")
    async def put_settings(update: GlobalSettingsUpdate) -> dict[str, Any]:
        settings = store.get()
        try:
            if update.selection_mode is not None:
                settings.selection_mode = update.selection_mode
            if update.armed_video is not None:
                if update.armed_video not in library.names():
                    raise LibraryError(
                        f"The video {update.armed_video!r} does not exist."
                    )
                settings.armed_video = update.armed_video
            if update.default_start is not None:
                settings.default_start_sec = parse_time(update.default_start)
            if update.resume_window is not None:
                settings.resume_window_sec = parse_time(update.resume_window)
            if update.volume is not None:
                if not 0 <= update.volume <= 100:
                    raise ValueError("The volume must be from 0 to 100.")
                settings.volume = update.volume
        except (LibraryError, ValueError) as error:
            raise _bad_request(error) from error
        store.replace(settings)
        await controller.settings_changed()
        return settings_payload()

    @app.post("/api/volume")
    async def put_volume(body: VolumeRequest) -> dict[str, Any]:
        settings = store.get()
        settings.volume = body.volume
        store.replace(settings)
        await controller.volume_changed()
        return settings_payload()

    @app.post("/api/settings/reset")
    async def reset_settings() -> dict[str, Any]:
        store.reset()
        await controller.settings_changed()
        return settings_payload()

    @app.get("/api/videos")
    async def list_videos() -> list[dict[str, Any]]:
        return [video_entry(name) for name in library.names()]

    @app.get("/api/storage")
    async def storage() -> dict[str, Any]:
        library.directory.mkdir(parents=True, exist_ok=True)
        usage = shutil.disk_usage(library.directory)
        return {"free_bytes": usage.free, "total_bytes": usage.total}

    @app.put("/api/videos/{filename}")
    async def upload_video(filename: str, request: Request) -> dict[str, Any]:
        length = request.headers.get("content-length")
        if length and length.isdigit():
            library.directory.mkdir(parents=True, exist_ok=True)
            free = shutil.disk_usage(library.directory).free
            if int(length) > free - RESERVED_FREE_BYTES:
                raise HTTPException(
                    status_code=507,
                    detail="The SD card does not have enough space for this video.",
                )
        try:
            name = await library.save_stream(
                filename, request.stream(), config.max_upload_bytes
            )
        except LibraryError as error:
            raise _bad_request(error) from error
        await controller.library_changed()
        return video_entry(name)

    @app.patch("/api/videos/{name}")
    async def rename_video(name: str, body: RenameRequest) -> dict[str, Any]:
        try:
            new_name = library.rename(name, body.new_name)
        except LibraryError as error:
            raise _bad_request(error) from error
        settings = store.get()
        if name in settings.videos:
            settings.videos[new_name] = settings.videos.pop(name)
        if settings.armed_video == name:
            settings.armed_video = new_name
        store.replace(settings)
        await controller.library_changed()
        return video_entry(new_name)

    @app.delete("/api/videos/{name}")
    async def delete_video(name: str) -> dict[str, Any]:
        try:
            library.delete(name)
        except LibraryError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        settings = store.get()
        settings.videos.pop(name, None)
        if settings.armed_video == name:
            settings.armed_video = None
        store.replace(settings)
        await controller.library_changed()
        return {"deleted": name}

    @app.put("/api/videos/{name}/settings")
    async def put_video_settings(name: str, body: dict[str, Any]) -> dict[str, Any]:
        try:
            library.path(name)
            current = store.get().video(name)
            merged = current.model_dump() | body
            video = VideoSettings.model_validate(merged)
        except LibraryError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except (ValidationError, ValueError) as error:
            raise _bad_request(error) from error
        store.update_video(name, video)
        await controller.settings_changed()
        return video_entry(name)

    @app.post("/api/play")
    async def play(body: PlayRequest) -> dict[str, Any]:
        await controller.set_test_play(body.active)
        return (await controller.status_with_position()).to_dict()

    @app.post("/api/pause")
    async def pause(body: PauseRequest) -> dict[str, Any]:
        try:
            await controller.set_paused(body.paused)
        except ControllerError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        return (await controller.status_with_position()).to_dict()

    @app.post("/api/seek")
    async def seek(body: SeekRequest) -> dict[str, Any]:
        if (body.offset_sec is None) == (body.position_sec is None):
            raise HTTPException(
                status_code=400, detail="Give offset_sec or position_sec."
            )
        try:
            if body.position_sec is not None:
                await controller.seek_to(body.position_sec)
            else:
                await controller.seek(body.offset_sec)
        except ControllerError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        return (await controller.status_with_position()).to_dict()

    @app.post("/api/use-position")
    async def use_position(body: UsePositionRequest) -> dict[str, Any]:
        try:
            position = await controller.use_position(body.target == "cue")
        except ControllerError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        return {"position_sec": position, "position": format_time(position)}

    @app.get("/api/network")
    async def network_status() -> dict[str, Any]:
        return (await network.status()).to_dict()

    @app.post("/api/network/mode")
    async def network_mode(body: ModeRequest) -> dict[str, Any]:
        try:
            network.request_mode(Mode(body.mode))
        except NetworkError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        return (await network.status()).to_dict()

    @app.post("/api/network/known")
    async def add_network(body: AddNetworkRequest) -> dict[str, Any]:
        try:
            await network.add_network(body.ssid.strip(), body.password)
        except NetworkError as error:
            raise _bad_request(error) from error
        return (await network.status()).to_dict()

    @app.delete("/api/network/known/{name}")
    async def forget_network(name: str) -> dict[str, Any]:
        try:
            await network.forget_network(name)
        except NetworkError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        return (await network.status()).to_dict()

    @app.get("/api/updates")
    async def updates_status() -> dict[str, Any]:
        if updates is None:
            return {"available": False, "running": False, "status": None}
        return updates.status()

    @app.post("/api/updates")
    async def request_update(body: UpdateRequest) -> dict[str, Any]:
        if updates is None:
            raise HTTPException(status_code=409, detail="Updates are not available.")
        try:
            return updates.request(body.target)
        except UpdateError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @app.post("/api/simulate")
    async def simulate(body: SimulateRequest) -> dict[str, Any]:
        if not isinstance(inputs, SimulatedInputs):
            raise HTTPException(
                status_code=404, detail="The inputs are not simulated on this system."
            )
        if body.knob is not None:
            if not isinstance(knob, SimulatedKnob):
                raise HTTPException(
                    status_code=404, detail="This system has no simulated knob."
                )
            await controller.knob_turned(body.knob)
        inputs.set(lid_open=body.lid_open, armed=body.armed, power_on=body.power_on)
        await controller.inputs_changed()
        if power:
            await power.inputs_changed()
        return await full_status()

    return app

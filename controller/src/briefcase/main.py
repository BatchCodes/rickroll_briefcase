"""Entry point: build the components and start the web server."""

from __future__ import annotations

import contextlib
import logging
import os
from collections.abc import AsyncIterator

import uvicorn
from fastapi import FastAPI

from briefcase.config import AppConfig
from briefcase.controller import BriefcaseController
from briefcase.display import create_display
from briefcase.inputs import create_inputs
from briefcase.library import Library
from briefcase.mpv import MpvClient, MpvPlayer
from briefcase.settings import SettingsStore
from briefcase.web import create_app

LOGGER = logging.getLogger("briefcase")


def build_app(config: AppConfig) -> FastAPI:
    inputs = create_inputs(config)
    client = MpvClient(config.mpv_socket)
    player = MpvPlayer(client)
    library = Library(config.videos_dir)
    store = SettingsStore(config.settings_path)
    controller = BriefcaseController(
        inputs, player, create_display(config), library, store
    )

    @contextlib.asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        config.videos_dir.mkdir(parents=True, exist_ok=True)
        await controller.start()
        client.start()
        LOGGER.info("The briefcase controller is running")
        try:
            yield
        finally:
            await client.close()
            inputs.close()

    return create_app(config, controller, library, store, inputs, lifespan=lifespan)


def main() -> None:
    logging.basicConfig(
        level=os.environ.get("BRIEFCASE_LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    config = AppConfig.from_env()
    uvicorn.run(
        build_app(config),
        host=config.http_host,
        port=config.http_port,
        log_level="warning",
    )


if __name__ == "__main__":
    main()

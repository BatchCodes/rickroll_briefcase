import pytest
from fakes import FakeDisplay, FakePlayer
from fastapi.testclient import TestClient

from briefcase.config import AppConfig
from briefcase.controller import BriefcaseController
from briefcase.inputs import SimulatedInputs
from briefcase.library import Library
from briefcase.settings import SettingsStore
from briefcase.web import create_app


@pytest.fixture
def setup(tmp_path):
    videos = tmp_path / "videos"
    videos.mkdir()
    (videos / "rickroll.mp4").write_bytes(b"x" * 10)
    (videos / "other.mp4").write_bytes(b"y" * 10)
    inputs = SimulatedInputs(lid_open=False, armed=True)
    player = FakePlayer()
    library = Library(videos)
    store = SettingsStore(tmp_path / "config" / "settings.json")
    controller = BriefcaseController(inputs, player, FakeDisplay(), library, store)
    config = AppConfig(videos_dir=videos, max_upload_bytes=1000)
    app = create_app(config, controller, library, store, inputs)

    with TestClient(app) as client:
        client.portal.call(controller.start)
        yield client, controller, player, store, videos


def test_index_page(setup):
    client, *_ = setup
    response = client.get("/")
    assert response.status_code == 200
    assert "Rickroll Briefcase" in response.text


def test_healthz_and_status(setup):
    client, *_ = setup
    assert client.get("/healthz").json()["ok"] is True
    status = client.get("/api/status").json()
    assert status["state"] == "ready"
    assert status["current_video"] == "other.mp4"
    assert status["simulated_inputs"] is True


def test_list_videos(setup):
    client, *_ = setup
    names = [video["name"] for video in client.get("/api/videos").json()]
    assert names == ["other.mp4", "rickroll.mp4"]


def test_put_settings_changes_armed_video(setup):
    client, _, player, store, _ = setup
    response = client.put(
        "/api/settings",
        json={"armed_video": "rickroll.mp4", "default_start": "00:45", "volume": 60},
    )
    assert response.status_code == 200
    assert response.json()["default_start"] == "00:45"
    assert player.loaded[0].name == "rickroll.mp4"
    assert player.loaded[1] == 45.0
    assert store.get().volume == 60


def test_put_settings_rejects_bad_values(setup):
    client, *_ = setup
    assert client.put("/api/settings", json={"default_start": "abc"}).status_code == 400
    assert client.put("/api/settings", json={"volume": 101}).status_code == 400
    assert client.put("/api/settings", json={"armed_video": "x.mp4"}).status_code == 400


def test_video_settings(setup):
    client, *_ = setup
    response = client.put(
        "/api/videos/other.mp4/settings",
        json={"start_mode": "random", "cue_points_sec": "00:10, 00:20"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["settings"]["cue_points_sec"] == [10.0, 20.0]
    assert body["settings"]["start_mode"] == "random"

    bad = client.put("/api/videos/other.mp4/settings", json={"start_mode": "nope"})
    assert bad.status_code == 400
    missing = client.put("/api/videos/missing.mp4/settings", json={})
    assert missing.status_code == 404


def test_upload_rename_delete(setup):
    client, _, _, store, videos = setup
    response = client.put("/api/videos/My Vïdeo!.mp4", content=b"z" * 100)
    assert response.status_code == 200
    name = response.json()["name"]
    assert name == "My Video.mp4"
    assert (videos / name).read_bytes() == b"z" * 100

    client.put("/api/settings", json={"armed_video": name})
    renamed = client.patch(f"/api/videos/{name}", json={"new_name": "new.mp4"})
    assert renamed.status_code == 200
    assert store.get().armed_video == "new.mp4"

    assert client.delete("/api/videos/new.mp4").status_code == 200
    assert not (videos / "new.mp4").exists()
    assert store.get().armed_video is None


def test_upload_rejects_wrong_type_and_large_files(setup):
    client, _, _, _, videos = setup
    assert client.put("/api/videos/notes.txt", content=b"x").status_code == 400
    assert client.put("/api/videos/big.mp4", content=b"x" * 2000).status_code == 400
    assert not list(videos.glob(".upload-*"))


def test_path_traversal_is_rejected(setup):
    client, *_ = setup
    response = client.delete("/api/videos/..%2Fsettings.json")
    assert response.status_code in {404, 405}


def test_simulate_and_play(setup):
    client, *_ = setup
    status = client.post("/api/simulate", json={"lid_open": True}).json()
    assert status["state"] == "playing"
    status = client.post("/api/simulate", json={"lid_open": False}).json()
    assert status["state"] == "ready"

    assert client.post("/api/play", json={"active": True}).json()["state"] == "playing"
    assert client.post("/api/play", json={"active": False}).json()["state"] == "ready"


def test_reset_settings(setup):
    client, *_ = setup
    client.put("/api/settings", json={"volume": 10})
    assert client.post("/api/settings/reset").json()["volume"] == 80


def test_pause_seek_use_position_api(setup):
    client, *_ = setup
    assert client.post("/api/pause", json={"paused": True}).status_code == 409
    client.post("/api/play", json={"active": True})
    status = client.post("/api/pause", json={"paused": True}).json()
    assert status["paused"] is True
    status = client.post("/api/seek", json={"offset_sec": -10}).json()
    assert status["position_sec"] == 20.0
    body = client.post("/api/use-position", json={"target": "start"}).json()
    assert body == {"position_sec": 20.0, "position": "00:20"}
    videos = {video["name"]: video for video in client.get("/api/videos").json()}
    assert videos["other.mp4"]["effective_start"] == "00:20"


def test_network_api_without_backend(setup):
    client, *_ = setup
    assert client.get("/api/network").json()["mode"] == "unavailable"
    response = client.post("/api/network/mode", json={"mode": "client"})
    assert response.status_code == 409

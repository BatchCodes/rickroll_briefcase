import json
import os
import time

import pytest

from briefcase.updates import STALE_SEC, UpdateError, UpdateManager


@pytest.fixture
def manager(tmp_path):
    return UpdateManager(tmp_path / "update", enabled=True, installed_version="0.1.0")


def test_status_without_files(manager):
    status = manager.status()
    assert status == {
        "available": True,
        "installed_version": "0.1.0",
        "pending": False,
        "running": False,
        "status": None,
    }


def test_request_writes_the_request_file(manager):
    status = manager.request("prerelease")
    request = json.loads(manager.request_file.read_text())
    assert request["target"] == "prerelease"
    assert status["pending"] is True
    assert status["running"] is True
    assert not list(manager.request_file.parent.glob(".request.*"))


def test_second_request_while_pending_fails(manager):
    manager.request("release")
    with pytest.raises(UpdateError):
        manager.request("release")


def test_running_status_blocks_a_request(manager):
    manager.status_file.parent.mkdir(parents=True)
    manager.status_file.write_text(json.dumps({"state": "installing", "message": "x"}))
    assert manager.status()["running"] is True
    with pytest.raises(UpdateError):
        manager.request("release")


def test_final_or_stale_status_allows_a_request(manager):
    manager.status_file.parent.mkdir(parents=True)
    manager.status_file.write_text(json.dumps({"state": "done", "message": "x"}))
    assert manager.status()["running"] is False

    manager.status_file.write_text(json.dumps({"state": "installing", "message": "x"}))
    old = time.time() - STALE_SEC - 10
    os.utime(manager.status_file, (old, old))
    assert manager.status()["running"] is False
    manager.request("main")


def test_disabled_updates_refuse_a_request(tmp_path):
    manager = UpdateManager(tmp_path, enabled=False, installed_version="latest")
    with pytest.raises(UpdateError):
        manager.request("release")
    assert manager.status()["available"] is False

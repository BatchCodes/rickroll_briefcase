import json

import pytest

from briefcase.settings import (
    DEFAULT_START_SEC,
    Settings,
    SettingsStore,
    StartMode,
    VideoSettings,
    format_time,
    parse_time,
)


@pytest.mark.parametrize(
    ("text", "seconds"),
    [
        ("00:30", 30.0),
        ("1:02:03", 3723.0),
        ("90", 90.0),
        ("01:30.5", 90.5),
        (12, 12.0),
    ],
)
def test_parse_time(text, seconds):
    assert parse_time(text) == seconds


@pytest.mark.parametrize("text", ["abc", "-1", "1:xx"])
def test_parse_time_rejects_bad_values(text):
    with pytest.raises(ValueError):
        parse_time(text)


def test_format_time():
    assert format_time(30) == "00:30"
    assert format_time(3723) == "1:02:03"
    assert format_time(90.5) == "01:30.500"


def test_defaults_match_brief():
    settings = Settings()
    assert settings.default_start_sec == DEFAULT_START_SEC == 30.0
    assert settings.start_sec_for("any.mp4") == 30.0
    assert settings.video("any.mp4").start_mode is StartMode.FIXED


def test_video_start_overrides_default():
    settings = Settings(videos={"a.mp4": VideoSettings(start_sec="01:00")})
    assert settings.start_sec_for("a.mp4") == 60.0
    assert settings.start_sec_for("b.mp4") == 30.0


def test_cue_points_parse_from_text():
    video = VideoSettings(cue_points_sec="00:30, 10 1:00")
    assert video.cue_points_sec == [10.0, 30.0, 60.0]


def test_store_round_trip(tmp_path):
    path = tmp_path / "config" / "settings.json"
    store = SettingsStore(path)
    store.update_video("a.mp4", VideoSettings(start_sec=5))
    assert json.loads(path.read_text())["videos"]["a.mp4"]["start_sec"] == 5.0

    reloaded = SettingsStore(path)
    assert reloaded.get().start_sec_for("a.mp4") == 5.0
    assert not list(path.parent.glob(".settings.*"))


def test_store_recovers_from_broken_file(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("{not json")
    store = SettingsStore(path)
    assert store.get() == Settings()
    assert (tmp_path / "settings.json.broken").exists()


def test_store_reset(tmp_path):
    store = SettingsStore(tmp_path / "settings.json")
    store.replace(Settings(volume=10))
    assert store.reset().volume == 80

"""Tests for the DeskBuddy PC-context and companion state layer."""
import asyncio

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.activity import (
    ActivityService,
    ActivityType,
    Expression,
    SleepStage,
    classify_activity,
    expression_for,
    sleep_stage_for,
)
from app.services.companion import CompanionService


@pytest.fixture
def client():
    return TestClient(app)


class TestClassification:
    def test_foreground_wins_over_background_audio(self):
        activity = classify_activity(
            "Code.exe",
            "main.py - Visual Studio Code",
            audio_active=True,
        )
        assert activity == ActivityType.CODING

    def test_music_app(self):
        assert classify_activity("Spotify.exe", "Spotify Premium") == ActivityType.MUSIC

    def test_youtube_music_is_music_not_video(self):
        assert classify_activity("chrome.exe", "YouTube Music") == ActivityType.MUSIC

    def test_youtube_video_is_watching(self):
        assert classify_activity("chrome.exe", "YouTube - Lo-fi beats") == ActivityType.WATCHING

    def test_browser(self):
        assert classify_activity("msedge.exe", "GitHub") == ActivityType.BROWSING

    def test_meeting(self):
        assert classify_activity("Zoom.exe", "Zoom Meeting") == ActivityType.MEETING

    def test_unreal_game_is_gaming(self):
        assert (
            classify_activity("TekkenGame-Win64-Shipping.exe", "TEKKEN 7")
            == ActivityType.GAMING
        )

    def test_desktop_with_audio_is_music(self):
        assert (
            classify_activity("explorer.exe", "Program Manager", audio_active=True)
            == ActivityType.MUSIC
        )

    def test_unknown(self):
        assert classify_activity("", "") == ActivityType.UNKNOWN


class TestSleepEngine:
    def test_stages(self):
        assert sleep_stage_for(0) == SleepStage.ACTIVE
        assert sleep_stage_for(30) == SleepStage.SLEEPY
        assert sleep_stage_for(119) == SleepStage.SLEEPY
        assert sleep_stage_for(120) == SleepStage.SLEEPING
        assert sleep_stage_for(299) == SleepStage.SLEEPING
        assert sleep_stage_for(300) == SleepStage.DEEP_SLEEP

    def test_sleepy_overrides_activity_expression(self):
        assert expression_for(ActivityType.CODING, SleepStage.SLEEPY) == Expression.SLEEPY
        assert expression_for(ActivityType.CODING, SleepStage.SLEEPING) == Expression.SLEEPING
        assert expression_for(ActivityType.CODING, SleepStage.DEEP_SLEEP) == Expression.DEEP_SLEEP

    def test_active_expression(self):
        assert expression_for(ActivityType.CODING, SleepStage.ACTIVE) == Expression.CODING
        assert expression_for(ActivityType.MUSIC, SleepStage.ACTIVE) == Expression.MUSIC
        assert expression_for(ActivityType.UNKNOWN, SleepStage.ACTIVE) == Expression.RELAXED


class TestCompanionAPI:
    def test_context(self, client):
        response = client.get("/api/v1/companion/context")
        assert response.status_code == 200
        data = response.json()
        assert "activity" in data
        assert "expression" in data
        assert "sleep_stage" in data
        assert "device" in data

    def test_summary(self, client):
        response = client.get("/api/v1/companion/summary")
        assert response.status_code == 200
        data = response.json()
        for key in (
            "activity",
            "expression",
            "music",
            "metrics",
            "pomodoro",
            "lyrics",
            "microphone",
            "clock",
        ):
            assert key in data

    def test_device_state_is_flat(self, client):
        response = client.get("/api/v1/companion/device-state")
        assert response.status_code == 200
        data = response.json()
        for key in (
            "act",
            "expr",
            "sleep",
            "cpu",
            "gtemp",
            "m_title",
            "pomo_rem",
            "lyr_cur",
            "batt_v",
            "mic",
            "clock",
        ):
            assert key in data

    def test_expressions(self, client):
        response = client.get("/api/v1/companion/expressions")
        assert response.status_code == 200
        expressions = response.json()["expressions"]
        assert "happy" in expressions
        assert "sleeping" in expressions

    def test_manual_emotion_and_clear(self, client):
        response = client.post(
            "/api/v1/companion/emotion",
            json={"expression": "surprised", "duration_seconds": 5},
        )
        assert response.status_code == 200
        assert response.json()["expression"] == "surprised"

        context = client.get("/api/v1/companion/context?force=true").json()
        assert context["expression"] == "surprised"
        assert context["manual_expression"] == "surprised"

        cleared = client.delete("/api/v1/companion/emotion")
        assert cleared.status_code == 200
        assert cleared.json()["context"]["manual_expression"] is None

    def test_invalid_emotion(self, client):
        response = client.post(
            "/api/v1/companion/emotion",
            json={"expression": "not-a-face"},
        )
        assert response.status_code == 400

    def test_heartbeat(self, client):
        response = client.post("/api/v1/companion/heartbeat")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"


class TestDeviceTelemetry:
    def test_sensor_message_updates_telemetry(self):
        activity = ActivityService()
        service = CompanionService(activity=activity)

        events = asyncio.run(
            service.handle_device_message(
                {
                    "type": "sensor_data",
                    "data": {
                        "temp": 24.5,
                        "humidity": 51.0,
                        "pressure": 1009.2,
                        "battery": 11.8,
                        "battery_pct": 72,
                        "mic_level": 34,
                        "accel": {"x": 0.1, "y": 0.2, "z": 9.8},
                    },
                }
            )
        )

        assert service.device.sensors["temperature"] == 24.5
        assert service.device.sensors["humidity"] == 51.0
        assert service.device.battery == 11.8
        assert service.device.battery_pct == 72
        assert service.device.mic_level == 34
        assert service.device.accel["z"] == 9.8
        assert service.device_online is True
        assert any(event["channel"] == "sensor_data" for event in events)

    def test_gesture_message_updates_telemetry(self):
        activity = ActivityService()
        service = CompanionService(activity=activity)

        events = asyncio.run(
            service.handle_device_message(
                {
                    "type": "gesture",
                    "gesture": "triple_tap",
                    "page": "home",
                    "mode": "desk_buddy",
                }
            )
        )

        assert service.device.last_gesture == "triple_tap"
        assert service.device.last_gesture_at is not None
        assert any(event["channel"] == "gesture" for event in events)

    def test_heartbeat_message_updates_page(self):
        activity = ActivityService()
        service = CompanionService(activity=activity)

        asyncio.run(
            service.handle_device_message(
                {
                    "type": "heartbeat",
                    "page": "music",
                    "mode": "desk_buddy",
                    "expression": "happy",
                }
            )
        )

        assert service.device.page == "music"
        assert service.device.expression == "happy"
        assert service.device_online is True

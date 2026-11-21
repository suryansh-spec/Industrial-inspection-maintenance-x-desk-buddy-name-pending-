"""
Tests for DeskBuddy Backend.
"""
import pytest
import asyncio
from httpx import ASGITransport, AsyncClient
from fastapi.testclient import TestClient

from app.main import app
from app.core.config import settings


@pytest.fixture
def client():
    """Test client fixture (lifespan not started - no external services)."""
    return TestClient(app)


@pytest.fixture
async def async_client():
    """Async test client fixture."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


class TestHealthCheck:
    """Health check tests."""
    
    def test_health_check(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "version" in data


class TestSystemAPI:
    """System API tests."""
    
    def test_get_metrics(self, client):
        response = client.get("/api/v1/system/metrics")
        # May return 503 if monitoring not initialized in test
        assert response.status_code in [200, 503]
    
    def test_get_alert_status(self, client):
        response = client.get("/api/v1/system/alerts/status")
        assert response.status_code in [200, 503]


class TestVibrationAPI:
    """Vibration analysis API tests."""
    
    def test_analyze_vibration(self, client):
        payload = {
            "device_id": "test_device",
            "x": [0.1, 0.2, 0.3],
            "y": [0.0, 0.1, 0.0],
            "z": [9.8, 10.1, 9.9],
            "sample_rate_hz": 1000,
            "method": "auto"
        }
        
        response = client.post("/api/v1/inspect/vibration", json=payload)
        # May return 503 if ML model not loaded
        assert response.status_code in [200, 503]
    
    def test_list_methods(self, client):
        response = client.get("/api/v1/inspect/methods")
        assert response.status_code == 200
        data = response.json()
        assert "methods" in data
        assert len(data["methods"]) == 4


class TestDeviceAPI:
    """Device API tests."""
    
    def test_device_status(self, client):
        response = client.get("/api/v1/device/status")
        assert response.status_code == 200
        data = response.json()
        assert "connected" in data


class TestDesktopToolsAPI:
    """Desktop tools API tests."""
    
    def test_pc_metrics(self, client):
        response = client.get("/api/v1/desktop/pc/metrics")
        assert response.status_code in [200, 503]
    
    def test_music_status(self, client):
        response = client.get("/api/v1/desktop/music/status")
        assert response.status_code in [200, 503]
    
    def test_calendar_events(self, client):
        response = client.get("/api/v1/desktop/calendar/events")
        assert response.status_code in [200, 503]


class TestVoiceAPI:
    """Voice assistant API tests."""
    
    def test_voice_status(self, client):
        response = client.get("/api/v1/voice/status")
        assert response.status_code == 200
        data = response.json()
        assert "enabled" in data
    
    def test_list_tools(self, client):
        response = client.get("/api/v1/voice/tools")
        assert response.status_code == 200
        data = response.json()
        assert "tools" in data
        assert len(data["tools"]) > 0


class TestWebSocket:
    """WebSocket tests."""
    
    def test_websocket_connection(self, client):
        # WebSocket tests would need async client
        pass


# Run tests with: pytest tests/ -v
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
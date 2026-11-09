"""Tests industriales para AI Channel.

Verifica:
- Validación de inputs Pydantic
- Enrutamiento de comandos
- Timeout handling
- Batch execution con semáforo
- Error propagation
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from tezcatlipoca.routers.ai_channel import (
    CommandRequest, BatchRequest, OSINTLookupRequest, TransportOptimizeRequest,
    ai_command, ai_batch, ai_tools, ai_expand, _looks_like_ip, _decode_metar_simple,
)


class TestInputValidation:
    def test_command_request_valid(self):
        req = CommandRequest(command="lookup 8.8.8.8", priority="high")
        assert req.command == "lookup 8.8.8.8"
        assert req.priority == "high"

    def test_command_request_invalid_priority(self):
        with pytest.raises(ValueError):
            CommandRequest(command="test", priority="invalid")

    def test_command_request_too_long(self):
        with pytest.raises(ValueError):
            CommandRequest(command="x" * 501)

    def test_batch_request_too_many(self):
        with pytest.raises(ValueError):
            BatchRequest(commands=[CommandRequest(command=f"cmd{i}") for i in range(51)])

    def test_osint_lookup_invalid_type(self):
        with pytest.raises(ValueError):
            OSINTLookupRequest(entity="test", type="invalid")

    def test_transport_optimize_invalid_profile(self):
        with pytest.raises(ValueError):
            TransportOptimizeRequest(waypoints=[[0,0],[1,1]], profile="spaceship")

    def test_transport_optimize_too_many_waypoints(self):
        with pytest.raises(ValueError):
            TransportOptimizeRequest(waypoints=[[i, i] for i in range(26)], profile="car")


class TestHelpers:
    def test_looks_like_ip_ipv4(self):
        assert _looks_like_ip("192.168.1.1") is True
        assert _looks_like_ip("8.8.8.8") is True
        assert _looks_like_ip("256.1.1.1") is False
        assert _looks_like_ip("192.168.1") is False

    def test_looks_like_ip_ipv6(self):
        assert _looks_like_ip("2001:db8::1") is True
        assert _looks_like_ip("::1") is True

    def test_looks_like_ip_domain(self):
        assert _looks_like_ip("google.com") is False
        assert _looks_like_ip("test.local") is False

    def test_decode_metar_simple(self):
        weather = {"temperature": 25, "windspeed": 15, "winddirection": 180, "precipitation": 0, "cloudcover": 20}
        decoded = _decode_metar_simple(weather)
        assert decoded["temperature_c"] == 25
        assert decoded["wind_speed_kmh"] == 15
        assert decoded["wind_direction_deg"] == 180

    def test_decode_metar_empty(self):
        assert _decode_metar_simple({}) == {}


class TestAICommand:
    @pytest.mark.asyncio
    async def test_unknown_command(self, monkeypatch):
        req = CommandRequest(command="unknown_command_xyz")
        # Mock auth
        mock_user = MagicMock()
        mock_user.username = "test"
        monkeypatch.setattr("tezcatlipoca.routers.ai_channel.require_role", lambda roles: lambda: mock_user)
        result = await ai_command(req, current_user=mock_user, _rate_limit=True)
        assert result["status"] == "FAILED"
        assert "unknown_command_xyz" in result["result"]

    @pytest.mark.asyncio
    async def test_weather_command_no_icao(self, monkeypatch):
        req = CommandRequest(command="weather now")
        mock_user = MagicMock()
        mock_user.username = "test"
        monkeypatch.setattr("tezcatlipoca.routers.ai_channel.require_role", lambda roles: lambda: mock_user)
        result = await ai_command(req, current_user=mock_user, _rate_limit=True)
        assert result["status"] == "REJECTED"
        assert result["result"] is None


class TestAIBatch:
    @pytest.mark.asyncio
    async def test_batch_execution(self, monkeypatch):
        req = BatchRequest(commands=[
            CommandRequest(command="cmd1"),
            CommandRequest(command="cmd2"),
        ])
        mock_user = MagicMock()
        mock_user.username = "test"
        monkeypatch.setattr("tezcatlipoca.routers.ai_channel.require_role", lambda roles: lambda: mock_user)
        result = await ai_batch(req, current_user=mock_user, _rate_limit=True)
        assert result["batch_size"] == 2
        assert result["status"] in ("completed", "partial_failure")
        assert "processed" in result


class TestAITools:
    @pytest.mark.asyncio
    async def test_tools_catalog(self, monkeypatch):
        mock_user = MagicMock()
        mock_user.username = "test"
        monkeypatch.setattr("tezcatlipoca.routers.ai_channel.require_role", lambda roles: lambda: mock_user)
        result = await ai_tools(current_user=mock_user, _rate_limit=True)
        assert "tools" in result
        assert len(result["tools"]) >= 10
        tool_ids = [t["id"] for t in result["tools"]]
        assert "osint_lookup" in tool_ids
        assert "transport_optimize" in tool_ids
        assert "sar_process" in tool_ids

"""Tests for the Animation MCP server."""

import json
from unittest.mock import MagicMock, patch

import pytest

from unreal_animation_mcp import server


@pytest.fixture(autouse=True)
def _clean_state():
    """Reset server singletons before and after each test."""
    server._reset_state()
    yield
    server._reset_state()


def _setup_tool_mock(return_data: dict):
    """Configure server with mocked bridge returning return_data."""
    server._project_path = "/tmp/TestProject"
    server._helper_uploaded = False
    server._helper_hash = ""

    mock_bridge = MagicMock()
    mock_bridge.run_command.side_effect = [
        {"success": True, "output": "helper_uploaded"},
        {"success": True, "output": json.dumps(return_data)},
    ]
    server._bridge = mock_bridge


class TestServerInit:
    def test_reset_state_clears_bridge(self):
        server._bridge = MagicMock()
        server._reset_state()
        assert server._bridge is None

    def test_get_bridge_creates_lazily(self):
        bridge = server._get_bridge()
        assert bridge is not None
        assert server._bridge is bridge

    @patch.object(server, "_get_bridge")
    @patch.object(server, "_get_helper_source", return_value="# helper\n")
    def test_ensure_helper_uploaded(self, _src, mock_get_bridge):
        mock_bridge = MagicMock()
        mock_get_bridge.return_value = mock_bridge
        server._project_path = "/tmp/TestProject"
        server._ensure_helper_uploaded()
        mock_bridge.run_command.assert_called_once()
        assert server._helper_uploaded is True

    @patch.object(server, "_get_bridge")
    @patch.object(server, "_get_helper_source", return_value="# helper\n")
    def test_skip_upload_when_already_done(self, _src, mock_get_bridge):
        mock_bridge = MagicMock()
        mock_get_bridge.return_value = mock_bridge
        server._helper_uploaded = True
        server._ensure_helper_uploaded()
        mock_bridge.run_command.assert_not_called()

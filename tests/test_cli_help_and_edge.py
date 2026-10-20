import json
import subprocess
import sys
from unittest.mock import patch

from typer.testing import CliRunner

from voices.cli import app

runner = CliRunner()


def test_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for command_name in (
        "ui",
        "doctor",
        "languages",
        "design",
        "design-batch",
        "clone",
        "record",
        "list",
        "resolve",
        "show",
        "say",
        "render",
        "align",
        "transcribe",
        "outputs",
        "edge",
        "delete",
    ):
        assert command_name in result.output


def test_console_entrypoint_emits_json_for_usage_errors():
    """Keep `voices --json` machine-readable even for Typer usage failures."""

    result = subprocess.run(
        [sys.executable, "-c", "from voices.cli_entrypoint import main; main()", "--json", "show"],
        check=False,
        capture_output=True,
        text=True,
    )

    payload = json.loads(result.stdout)
    assert result.returncode == 2
    assert result.stderr == ""
    assert payload["error"]["code"] == "invalid_input"
    assert payload["error"]["exit_code"] == 2
    assert "voice_id" in payload["error"]["message"]


def test_console_entrypoint_emits_json_for_unknown_commands():
    """Keep retired commands machine-readable under global JSON mode."""

    result = subprocess.run(
        [sys.executable, "-c", "from voices.cli_entrypoint import main; main()", "--json", "status"],
        check=False,
        capture_output=True,
        text=True,
    )

    payload = json.loads(result.stdout)
    assert result.returncode == 2
    assert result.stderr == ""
    assert payload["error"]["code"] == "invalid_input"
    assert payload["error"]["exit_code"] == 2
    assert "No such command" in payload["error"]["message"]


@patch("voices.cli_diagnostics.launch_edge_server")
def test_ui_launches_edge_server(mock_launch_edge_server, tmp_path):
    result = runner.invoke(
        app,
        ["ui", "--library", str(tmp_path / "voices"), "--host", "127.0.0.1", "--port", "9901", "--no-open"],
    )
    assert result.exit_code == 0, result.output
    mock_launch_edge_server.assert_called_once()
    kwargs = mock_launch_edge_server.call_args.kwargs
    assert kwargs["library"] == tmp_path / "voices"
    assert kwargs["launch"].host == "127.0.0.1"
    assert kwargs["launch"].port == 9901
    assert kwargs["launch"].open_browser is False


@patch("voices.cli_diagnostics.launch_edge_server")
def test_ui_rejects_non_loopback_host(mock_launch_edge_server, tmp_path):
    result = runner.invoke(
        app,
        ["ui", "--library", str(tmp_path / "voices"), "--host", "0.0.0.0", "--port", "9901", "--no-open"],
    )
    assert result.exit_code == 2
    assert "loopback" in result.output
    mock_launch_edge_server.assert_not_called()


@patch("voices.cli_diagnostics.launch_edge_server")
def test_ui_formats_ipv6_loopback_url(mock_launch_edge_server, tmp_path):
    result = runner.invoke(
        app,
        ["ui", "--library", str(tmp_path / "voices"), "--host", "::1", "--port", "9901", "--no-open"],
    )
    assert result.exit_code == 0, result.output
    assert "http://[::1]:9901" in result.output
    mock_launch_edge_server.assert_called_once()

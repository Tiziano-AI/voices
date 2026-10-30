"""Exercise the console boundary rather than bypassing it with CliRunner."""

import json
import subprocess
import sys

import pytest
import typer

from voices import cli_entrypoint


def _run(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", "from voices.cli_entrypoint import main; main()", *arguments],
        check=False,
        capture_output=True,
        text=True,
    )


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        (["--not-an-option"], "No such option"),
        (["ui", "--port", "not-a-number"], "not a valid int"),
        (["show", "--not-an-option"], "No such option"),
        (["--compute", "dgx", "languages"], "explicit SSH host alias"),
    ],
)
def test_json_usage_failures_have_one_envelope_and_no_traceback(arguments: list[str], message: str):
    result = _run("--json", *arguments)

    assert result.returncode == 2
    assert result.stderr == ""
    payload = json.loads(result.stdout)
    assert set(payload) == {"error"}
    assert payload["error"]["code"] == "invalid_input"
    assert payload["error"]["exit_code"] == 2
    assert message in payload["error"]["message"]


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        (["show"], "Missing argument"),
        (["status"], "No such command"),
        (["--not-an-option"], "No such option"),
    ],
)
def test_human_usage_failures_keep_native_rich_errors(arguments: list[str], message: str):
    result = _run(*arguments)

    assert result.returncode == 2
    assert result.stdout == ""
    assert "Usage:" in result.stderr
    assert "╭─" in result.stderr
    assert message in result.stderr
    assert "Traceback" not in result.stderr


@pytest.mark.parametrize("arguments", [["--help"], ["--json", "--help"]])
def test_help_exits_successfully_without_traceback(arguments: list[str]):
    result = _run(*arguments)

    assert result.returncode == 0
    assert "Usage:" in result.stdout
    assert result.stderr == ""


def test_json_success_remains_machine_readable():
    result = _run("--json", "languages")

    assert result.returncode == 0
    assert result.stderr == ""
    assert isinstance(json.loads(result.stdout), dict)


@pytest.mark.parametrize("exit_code", [0, 7, 130])
def test_json_entrypoint_preserves_explicit_typer_exit(monkeypatch: pytest.MonkeyPatch, exit_code: int):
    test_app = typer.Typer(invoke_without_command=True)

    @test_app.callback()
    def stop(json_output: bool = typer.Option(False, "--json")) -> None:
        assert json_output
        raise typer.Exit(exit_code)

    monkeypatch.setattr(cli_entrypoint, "app", test_app)
    monkeypatch.setattr(sys, "argv", ["voices", "--json"])

    with pytest.raises(SystemExit) as error:
        cli_entrypoint.main()

    assert error.value.code == exit_code

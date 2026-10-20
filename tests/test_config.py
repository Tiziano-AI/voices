from pathlib import Path

from voices.config import DEFAULT_LIBRARY, get_library_path


def test_get_library_path_prefers_cli_override(monkeypatch, tmp_path):
    monkeypatch.setenv("VOICES_LIBRARY", str(tmp_path / "from-env"))
    override = tmp_path / "from-cli"
    assert get_library_path(override) == override.resolve(strict=False)


def test_get_library_path_uses_env(monkeypatch, tmp_path):
    env_path = tmp_path / "from-env"
    monkeypatch.setenv("VOICES_LIBRARY", str(env_path))
    assert get_library_path() == env_path.resolve(strict=False)


def test_get_library_path_defaults(monkeypatch):
    monkeypatch.delenv("VOICES_LIBRARY", raising=False)
    assert get_library_path() == DEFAULT_LIBRARY.resolve(strict=False)


def test_get_library_path_expands_and_resolves_cli_override(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    resolved = get_library_path(Path("relative-library"))
    assert resolved == (tmp_path / "relative-library").resolve()


def test_get_library_path_expands_env_home(monkeypatch, tmp_path):
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("VOICES_LIBRARY", "~/voices")

    assert get_library_path() == home / "voices"

"""Bundle selection must work in both editable and wheel installations."""

from pathlib import Path

import pytest

from voices import studio_bundle
from voices.domain.errors import MissingDependencyError


def test_editable_bundle_uses_source_build(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    package = tmp_path / "src" / "voices"
    package.mkdir(parents=True)
    monkeypatch.setattr(studio_bundle, "__file__", str(package / "studio_bundle.py"))
    assert studio_bundle.studio_bundle_path() == tmp_path / "web" / "dist"


def test_wheel_bundle_is_selected_before_checkout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    package = tmp_path / "site-packages" / "voices"
    bundle = package / "web_dist"
    bundle.mkdir(parents=True)
    (bundle / "index.html").write_text("<!doctype html>", encoding="utf-8")
    monkeypatch.setattr(studio_bundle, "__file__", str(package / "studio_bundle.py"))
    assert studio_bundle.resolve_web_dist() == bundle


def test_missing_bundle_remains_a_setup_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(studio_bundle, "__file__", str(tmp_path / "voices" / "studio_bundle.py"))
    with pytest.raises(MissingDependencyError, match="Bundled UI assets are missing"):
        studio_bundle.resolve_web_dist()

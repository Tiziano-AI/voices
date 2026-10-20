"""The source digest describes installed bytes, not a Git checkout or path."""

import shutil
import sys
from importlib.metadata import version

from voices import runtime_identity


def test_source_digest_is_location_independent_and_ignores_generated_content(tmp_path):
    source = tmp_path / "checkout" / "voices"
    source.mkdir(parents=True)
    (source / "__init__.py").write_text("VERSION = 1\n")
    (source / "adapter").mkdir()
    (source / "adapter" / "runtime.py").write_text("def run(): return 1\n")
    installed = tmp_path / "different-location" / "site-packages" / "voices"
    shutil.copytree(source, installed)
    (installed / "__pycache__").mkdir()
    (installed / "__pycache__" / "ignored.py").write_text("not source")
    (installed / "reference.wav").write_bytes(b"audio bytes")
    (installed / "web_dist").mkdir()
    (installed / "web_dist" / "ignored.py").write_text("generated web asset")
    assert runtime_identity.source_sha256(source) == runtime_identity.source_sha256(installed)
    (installed / "adapter" / "runtime.py").write_text("def run(): return 2\n")
    assert runtime_identity.source_sha256(source) != runtime_identity.source_sha256(installed)


def test_source_digest_includes_relative_file_names(tmp_path):
    source = tmp_path / "voices"
    source.mkdir()
    path = source / "one.py"
    path.write_text("same bytes")
    first = runtime_identity.source_sha256(source)
    path.rename(source / "two.py")
    assert runtime_identity.source_sha256(source) != first


def test_runtime_identity_reports_current_interpreter_and_selected_packages():
    identity = runtime_identity.get_runtime_identity()
    assert identity.executable == sys.executable
    assert identity.voices_version == version("voices")
    assert identity.packages == {name: version(name) for name in runtime_identity.SELECTED_RUNTIME_PACKAGES}
    assert identity.package_scope == "selected-runtime-dependencies"
    assert identity.source_sha256 == runtime_identity.get_runtime_identity().source_sha256

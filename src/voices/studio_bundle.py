"""Locate the generated studio bundle in an editable checkout or installed wheel."""

from pathlib import Path

from voices.domain.errors import MissingDependencyError


def studio_bundle_path() -> Path:
    """Select packaged assets, or the source-owned build for an editable install."""
    package_root = Path(__file__).resolve().parent
    packaged = package_root / "web_dist"
    if packaged.is_dir():
        return packaged
    return package_root.parents[1] / "web" / "dist"


def resolve_web_dist() -> Path:
    """Require the selected bundle without building or changing it at runtime."""
    web_dist = studio_bundle_path()
    if not (web_dist / "index.html").is_file():
        raise MissingDependencyError(
            "Bundled UI assets are missing. Run 'pnpm --dir web install' and 'pnpm --dir web build', "
            "then rebuild the Python package if using a wheel."
        )
    return web_dist

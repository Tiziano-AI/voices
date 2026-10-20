"""Local FastAPI/browser edge for the bundled voices studio."""

from voices.edge.app import create_edge_app, launch_edge_server, resolve_web_dist

__all__ = ["create_edge_app", "launch_edge_server", "resolve_web_dist"]

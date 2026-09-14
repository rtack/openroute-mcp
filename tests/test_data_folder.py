"""Test the default generated-routes data folder resolution."""

import os

from openroute_mcp.server import default_data_folder


def test_default_data_folder_is_absolute() -> None:
    """The default folder must be an absolute path."""
    assert os.path.isabs(default_data_folder()), "Default data folder should be an absolute path"


def test_default_data_folder_not_under_cwd() -> None:
    """The default folder must not resolve relative to the current working directory.

    MCP server subprocesses inherit whatever directory the launching client
    happens to be rooted in as their cwd, so a cwd-relative default would leak
    a generated-files directory into whatever unrelated repo/folder a session
    was started from.
    """
    cwd = os.getcwd()
    folder = default_data_folder()
    assert not folder.startswith(cwd), f"Default data folder {folder!r} should not be under the cwd {cwd!r}"
    assert "generated_routes" in folder


def test_default_data_folder_respects_xdg_cache_home(monkeypatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    """XDG_CACHE_HOME, when set, should be honored."""
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    folder = default_data_folder()
    assert folder == os.path.join(str(tmp_path), "openroute-mcp", "generated_routes")


def test_default_data_folder_falls_back_to_home_cache(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Without XDG_CACHE_HOME, the default should fall back under ~/.cache."""
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
    folder = default_data_folder()
    expected = os.path.join(os.path.expanduser("~"), ".cache", "openroute-mcp", "generated_routes")
    assert folder == expected

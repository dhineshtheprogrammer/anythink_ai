"""Tests for plugins/manager.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from anythink.plugins.manager import PluginManager
from anythink.plugins.models import PluginInfo


def _make_ep(
    pkg_name: str,
    group: str,
    version: str = "1.0.0",
    summary: str = "A plugin",
    author: str = "Dev",
) -> MagicMock:
    """Build a mock EntryPoint with a realistic .dist."""
    metadata = MagicMock()
    metadata.__getitem__ = MagicMock(side_effect=lambda k: pkg_name if k == "Name" else "")
    metadata.get = MagicMock(
        side_effect=lambda k, default="": {
            "Summary": summary,
            "Author": author,
            "Home-page": "",
        }.get(k, default)
    )
    dist = MagicMock()
    dist.metadata = metadata
    dist.version = version

    ep = MagicMock()
    ep.dist = dist
    return ep


def _patch_eps(eps_by_group: dict[str, list[MagicMock]]):
    """Context-manager that patches entry_points() in manager.py."""

    def _side_effect(*, group: str) -> list[MagicMock]:
        return eps_by_group.get(group, [])

    return patch("anythink.plugins.manager.entry_points", side_effect=_side_effect)


class TestListPlugins:
    def test_returns_empty_when_no_eps(self) -> None:
        with _patch_eps({}):
            assert PluginManager().list_plugins() == []

    def test_returns_plugin_info_for_single_package(self) -> None:
        ep = _make_ep("anythink-groq", "anythink.providers", version="2.0.0", summary="Groq")
        with _patch_eps({"anythink.providers": [ep]}):
            plugins = PluginManager().list_plugins()
        assert len(plugins) == 1
        assert isinstance(plugins[0], PluginInfo)
        assert plugins[0].name == "anythink-groq"
        assert plugins[0].version == "2.0.0"
        assert plugins[0].description == "Groq"

    def test_deduplicates_packages_across_groups(self) -> None:
        ep1 = _make_ep("multi-plugin", "anythink.providers")
        ep2 = _make_ep("multi-plugin", "anythink.search_backends")
        with _patch_eps(
            {
                "anythink.providers": [ep1],
                "anythink.search_backends": [ep2],
            }
        ):
            plugins = PluginManager().list_plugins()
        assert len(plugins) == 1
        assert plugins[0].name == "multi-plugin"

    def test_tracks_all_groups_for_multi_group_package(self) -> None:
        ep1 = _make_ep("multi-plugin", "anythink.providers")
        ep2 = _make_ep("multi-plugin", "anythink.search_backends")
        with _patch_eps(
            {
                "anythink.providers": [ep1],
                "anythink.search_backends": [ep2],
            }
        ):
            plugins = PluginManager().list_plugins()
        groups = plugins[0].entry_point_groups
        assert "anythink.providers" in groups
        assert "anythink.search_backends" in groups

    def test_skips_eps_without_dist(self) -> None:
        ep = MagicMock()
        ep.dist = None
        with _patch_eps({"anythink.providers": [ep]}):
            assert PluginManager().list_plugins() == []

    def test_returns_plugins_sorted_by_name(self) -> None:
        ep_b = _make_ep("b-plugin", "anythink.providers")
        ep_a = _make_ep("a-plugin", "anythink.providers")
        with _patch_eps({"anythink.providers": [ep_b, ep_a]}):
            plugins = PluginManager().list_plugins()
        assert [p.name for p in plugins] == ["a-plugin", "b-plugin"]

    def test_stores_author_from_metadata(self) -> None:
        ep = _make_ep("mypkg", "anythink.providers", author="Alice")
        with _patch_eps({"anythink.providers": [ep]}):
            plugins = PluginManager().list_plugins()
        assert plugins[0].author == "Alice"


class TestGetPlugin:
    def test_returns_plugin_when_found(self) -> None:
        ep = _make_ep("anythink-groq", "anythink.providers")
        with _patch_eps({"anythink.providers": [ep]}):
            result = PluginManager().get_plugin("anythink-groq")
        assert result is not None
        assert result.name == "anythink-groq"

    def test_returns_none_when_not_found(self) -> None:
        with _patch_eps({}):
            assert PluginManager().get_plugin("missing") is None

    def test_case_insensitive_lookup(self) -> None:
        ep = _make_ep("Anythink-Groq", "anythink.providers")
        with _patch_eps({"anythink.providers": [ep]}):
            result = PluginManager().get_plugin("anythink-groq")
        assert result is not None


class TestInstall:
    def test_install_returns_true_on_success(self) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Successfully installed anythink-groq-1.0.0\n"
        mock_result.stderr = ""

        with patch("anythink.plugins.manager.subprocess.run", return_value=mock_result):
            ok, output = PluginManager().install("anythink-groq")

        assert ok is True
        assert "Successfully installed" in output

    def test_install_returns_false_on_failure(self) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "ERROR: Could not find package\n"

        with patch("anythink.plugins.manager.subprocess.run", return_value=mock_result):
            ok, output = PluginManager().install("no-such-package")

        assert ok is False
        assert "Could not find" in output

    def test_install_calls_pip_with_package_name(self) -> None:
        mock_result = MagicMock(returncode=0, stdout="", stderr="")
        with patch("anythink.plugins.manager.subprocess.run", return_value=mock_result) as mock_run:
            PluginManager().install("myplugin")
        args = mock_run.call_args[0][0]
        assert "pip" in " ".join(args)
        assert "install" in args
        assert "myplugin" in args


class TestRemove:
    def test_remove_returns_true_on_success(self) -> None:
        mock_result = MagicMock(returncode=0, stdout="Successfully uninstalled\n", stderr="")
        with patch("anythink.plugins.manager.subprocess.run", return_value=mock_result):
            ok, output = PluginManager().remove("anythink-groq")
        assert ok is True

    def test_remove_returns_false_on_failure(self) -> None:
        mock_result = MagicMock(returncode=1, stdout="", stderr="WARNING: not installed\n")
        with patch("anythink.plugins.manager.subprocess.run", return_value=mock_result):
            ok, output = PluginManager().remove("no-such-pkg")
        assert ok is False

    def test_remove_calls_pip_uninstall_with_y(self) -> None:
        mock_result = MagicMock(returncode=0, stdout="", stderr="")
        with patch("anythink.plugins.manager.subprocess.run", return_value=mock_result) as mock_run:
            PluginManager().remove("myplugin")
        args = mock_run.call_args[0][0]
        assert "uninstall" in args
        assert "-y" in args
        assert "myplugin" in args

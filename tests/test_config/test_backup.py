"""Tests for config backup and restore."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from anythink.config.backup import export_config, import_config
from anythink.config.manager import Paths


def _make_ctx(xdg_dirs: Paths) -> MagicMock:
    ctx = MagicMock()
    ctx.paths = xdg_dirs
    return ctx


class TestExportConfig:
    def test_creates_json_file(self, xdg_dirs: Paths, tmp_path: Path) -> None:
        ctx = _make_ctx(xdg_dirs)
        out = tmp_path / "backup.json"
        export_config(ctx, out)
        assert out.exists()

    def test_json_has_version_field(self, xdg_dirs: Paths, tmp_path: Path) -> None:
        ctx = _make_ctx(xdg_dirs)
        out = tmp_path / "backup.json"
        export_config(ctx, out)
        data = json.loads(out.read_text())
        assert data["version"] == 3

    def test_exported_at_present(self, xdg_dirs: Paths, tmp_path: Path) -> None:
        ctx = _make_ctx(xdg_dirs)
        out = tmp_path / "backup.json"
        export_config(ctx, out)
        data = json.loads(out.read_text())
        assert "exported_at" in data

    def test_models_section_present(self, xdg_dirs: Paths, tmp_path: Path) -> None:
        ctx = _make_ctx(xdg_dirs)
        out = tmp_path / "backup.json"
        export_config(ctx, out)
        data = json.loads(out.read_text())
        assert "models" in data


class TestImportConfig:
    def test_import_restores_models(self, xdg_dirs: Paths, tmp_path: Path) -> None:
        import yaml

        ctx = _make_ctx(xdg_dirs)

        # Prepare a bundle with a models entry
        models_data = [
            {
                "alias": "test-model",
                "provider": "groq",
                "model_id": "llama3-8b",
                "context_window": 8192,
            }
        ]
        bundle = {
            "version": 3,
            "exported_at": "2025-01-01T00:00:00",
            "models": models_data,
            "config": None,
            "personas": None,
            "templates": None,
            "schedules": None,
        }
        bundle_path = tmp_path / "bundle.json"
        bundle_path.write_text(json.dumps(bundle))

        import_config(ctx, bundle_path)

        restored = yaml.safe_load(xdg_dirs.models_file.read_text())
        assert len(restored) == 1
        assert restored[0]["alias"] == "test-model"

    def test_import_validates_config_section(self, xdg_dirs: Paths, tmp_path: Path) -> None:
        ctx = _make_ctx(xdg_dirs)
        bundle = {
            "version": 3,
            "exported_at": "2025-01-01T00:00:00",
            "config": {"active_theme": "invalid-theme-name"},
            "models": None,
            "personas": None,
            "templates": None,
            "schedules": None,
        }
        bundle_path = tmp_path / "bad_bundle.json"
        bundle_path.write_text(json.dumps(bundle))

        with pytest.raises(ValueError, match="invalid config"):
            import_config(ctx, bundle_path)

    def test_import_rejects_future_version(self, xdg_dirs: Paths, tmp_path: Path) -> None:
        ctx = _make_ctx(xdg_dirs)
        bundle = {"version": 99, "exported_at": "2099-01-01T00:00:00"}
        bundle_path = tmp_path / "future.json"
        bundle_path.write_text(json.dumps(bundle))

        with pytest.raises(ValueError, match="newer"):
            import_config(ctx, bundle_path)

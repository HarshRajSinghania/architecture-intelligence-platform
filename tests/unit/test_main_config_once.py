"""`create_app` parses config.yaml exactly once and the lifespan runs on that same snapshot; the
config path is an explicit parameter (default: the `CONFIG_PATH` env var or `config.yaml`)."""

from pathlib import Path
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

import app.main
from app.settings import DEFAULT_CONFIG_PATH, config_path_from_env

_CONFIG = (
    "architecture_intelligence:\n"
    "  graph:\n"
    "    database: custom-db\n"
    "  llm:\n"
    "    max-result-rows: 7\n"
)


def _write_config(tmp_path: Path) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(_CONFIG.replace("max-result-rows", "max_result_rows"))
    return path


def test_config_path_from_env_defaults_and_honours_the_env_var(monkeypatch, tmp_path):
    monkeypatch.delenv("CONFIG_PATH", raising=False)
    assert config_path_from_env() == DEFAULT_CONFIG_PATH
    monkeypatch.setenv("CONFIG_PATH", str(tmp_path / "other.yaml"))
    assert config_path_from_env() == tmp_path / "other.yaml"


def test_create_app_takes_an_explicit_config_path_and_needs_no_secrets(monkeypatch, tmp_path):
    monkeypatch.delenv("NEO4J_PASSWORD", raising=False)
    monkeypatch.delenv("NEO4J_URI", raising=False)
    application = app.main.create_app(_write_config(tmp_path))
    assert application.state.config.graph.database == "custom-db"
    assert application.state.config.llm.max_result_rows == 7


def test_lifespan_runs_on_the_config_create_app_parsed_without_rereading_the_file(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("NEO4J_PASSWORD", "unused")
    config_path = _write_config(tmp_path)
    application = app.main.create_app(config_path)
    config_path.unlink()  # a second parse at startup would now raise FileNotFoundError
    driver = Mock()
    monkeypatch.setattr(app.main, "build_driver", lambda *_args: driver)
    monkeypatch.setattr(app.main, "build_production_service", lambda *_a, **_k: Mock())
    with TestClient(application):
        assert application.state.settings.config is application.state.config
        assert application.state.settings.config.graph.database == "custom-db"
    driver.close.assert_called_once()


def test_create_app_fails_clearly_for_a_missing_config_path(tmp_path):
    with pytest.raises(FileNotFoundError):
        app.main.create_app(tmp_path / "missing.yaml")

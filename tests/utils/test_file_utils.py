import yaml
import pytest
from pathlib import Path
from unittest.mock import MagicMock

from utils.file_utils import FileUtils


# Basic filesystem helpers
def test_ensure_dir_creates_directory(tmp_path):
    new_dir = tmp_path / "nested" / "dir"
    assert not new_dir.exists()

    FileUtils.ensure_dir(new_dir)

    assert new_dir.exists()
    assert new_dir.is_dir()


def test_file_exists(tmp_path):
    file = tmp_path / "test.txt"
    assert FileUtils.file_exists(file) is False

    file.write_text("hello")
    assert FileUtils.file_exists(file) is True


# YAML helpers
def test_write_and_read_yaml_roundtrip(tmp_path):
    path = tmp_path / "data.yaml"
    data = {"a": 1, "b": {"c": True}}

    FileUtils.write_yaml(path, data)
    result = FileUtils.read_yaml(path)

    assert result == data


def test_read_yaml_missing_file_returns_empty(tmp_path):
    path = tmp_path / "missing.yaml"

    result = FileUtils.read_yaml(path)
    assert result == {}


# Snippet import / export (no dialogs)
def test_export_and_import_snippets_yaml(tmp_path):
    yaml_path = tmp_path / "snippets.yaml"

    snippets = [
        {
            "enabled": True,
            "label": "Test",
            "trigger": "/t",
            "snippet": "hello",
            "paste_style": "clipboard",
            "return_press": False,
            "folder": "",
            "tags": "a,b",
        }
    ]

    FileUtils.export_snippets_yaml(yaml_path, snippets)
    assert yaml_path.exists()

    imported = FileUtils.import_snippets_yaml(yaml_path)
    assert imported == snippets


def test_import_snippets_yaml_invalid_format(tmp_path):
    yaml_path = tmp_path / "bad.yaml"

    FileUtils.write_yaml(yaml_path, {"snippets": "not-a-list"})

    with pytest.raises(ValueError):
        FileUtils.import_snippets_yaml(yaml_path)


# Default file creators
def test_create_config_file(tmp_path):
    default_dir = tmp_path / "default_dir"
    user_path = tmp_path / "config.yaml"

    FileUtils.create_config_file(default_dir, user_path)

    assert user_path.exists()

    data = FileUtils.read_yaml(user_path)
    assert data["program_name"] == "QSnippet"
    assert "colors" in data
    assert "images" in data

def test_create_settings_file(tmp_path):
    default_dir = tmp_path / "default_dir"
    user_path = tmp_path / "settings.yaml"

    FileUtils.create_settings_file(default_dir, user_path)

    assert user_path.exists()

    data = FileUtils.read_yaml(user_path)
    assert "general" in data
    assert data["general"]["start_at_boot"] is False


def test_create_snippets_db_file(tmp_path):
    path = tmp_path / "snippets.db"

    FileUtils.create_snippets_db_file(path)

    assert path.exists()
    assert path.stat().st_size > 0

# get_default_paths
def test_get_default_paths_structure(monkeypatch, tmp_path):
    """
    Validate keys and path types without touching real OS locations.
    """
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("ProgramData", str(tmp_path))

    paths = FileUtils.get_default_paths()

    required_keys = {
        "app_data",
        "documents",
        "log_dir",
        "working_dir",
        "resource_dir",
    }

    assert required_keys.issubset(paths.keys())

    for key, value in paths.items():
        assert isinstance(value, Path)

import yaml
import pytest
from pathlib import Path
from unittest.mock import MagicMock

from utils.file_utils import FileUtils


# Basic filesystem helpers
def test_ensure_dir_creates_directory(tmp_path):
    """
    Test that ensure_dir creates nested directory structure.

    Verifies that parent directories are created as needed.
    """
    new_dir = tmp_path / "nested" / "dir"
    assert not new_dir.exists()

    FileUtils.ensure_dir(new_dir)

    assert new_dir.exists()
    assert new_dir.is_dir()


def test_file_exists(tmp_path):
    """
    Test file existence checking.

    Verifies that file_exists returns False for missing files and True for existing ones.
    """
    file = tmp_path / "test.txt"
    assert FileUtils.file_exists(file) is False

    file.write_text("hello")
    assert FileUtils.file_exists(file) is True


# YAML helpers
def test_write_and_read_yaml_roundtrip(tmp_path):
    """
    Test YAML write and read operations are symmetric.

    Verifies that data survives a write-read cycle without corruption.
    """
    path = tmp_path / "data.yaml"
    data = {"a": 1, "b": {"c": True}}

    FileUtils.write_yaml(path, data)
    result = FileUtils.read_yaml(path)

    assert result == data


def test_read_yaml_missing_file_returns_empty(tmp_path):
    """
    Test that reading a missing YAML file returns empty dict.

    Verifies graceful handling of missing files.
    """
    path = tmp_path / "missing.yaml"

    result = FileUtils.read_yaml(path)
    assert result == {}


# Snippet import / export (no dialogs)
def test_export_and_import_snippets_yaml(tmp_path):
    """
    Test snippet export to YAML and import back are symmetric.

    Verifies that snippet data survives export-import cycle.
    """
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
    """
    Test that importing malformed YAML raises ValueError.

    Verifies error handling for invalid snippet data.
    """
    yaml_path = tmp_path / "bad.yaml"

    FileUtils.write_yaml(yaml_path, {"snippets": "not-a-list"})

    with pytest.raises(ValueError):
        FileUtils.import_snippets_yaml(yaml_path)


# Default file creators
def test_create_config_file(tmp_path):
    """
    Test that config file is created from default template.

    Verifies that default config values are copied to user config.
    """
    default_dir = tmp_path / "default_dir"
    default_dir.mkdir()

    default_config = default_dir / "config.yaml"
    default_config.write_text(
        """
program_name: QSnippet
colors: {}
images: {}
""",
        encoding="utf-8"
    )

    user_path = tmp_path / "config.yaml"

    FileUtils.create_config_file(default_dir, user_path)

    assert user_path.exists()

    data = FileUtils.read_yaml(user_path)
    assert data["program_name"] == "QSnippet"
    assert "colors" in data
    assert "images" in data

def test_create_settings_file(tmp_path):
    """
    Test that settings file is created from default template.

    Verifies that default settings values are copied to user settings.
    """
    default_dir = tmp_path / "default_dir"
    default_dir.mkdir()

    default_settings = default_dir / "settings.yaml"
    default_settings.write_text(
        """
general:
  start_at_boot: false
""",
        encoding="utf-8"
    )

    user_path = tmp_path / "settings.yaml"

    FileUtils.create_settings_file(default_dir, user_path)

    assert user_path.exists()

    data = FileUtils.read_yaml(user_path)
    assert "general" in data
    assert data["general"]["start_at_boot"] is False

def test_create_snippets_db_file(tmp_path):
    """
    Test that SQLite database file is created.

    Verifies that a valid database file is generated.
    """
    path = tmp_path / "snippets.db"

    FileUtils.create_snippets_db_file(path)

    assert path.exists()
    assert path.stat().st_size > 0

# get_default_paths
def test_get_default_paths_structure(monkeypatch, tmp_path):
    """
    Validate default path structure and types without touching real OS locations.

    Verifies that all required path keys are present and contain Path objects.
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


# merge_dict
class TestMergeDict:
    def test_missing_key_added_from_default(self):
        default = {"a": 1, "b": 2}
        user = {"a": 10}
        result = FileUtils.merge_dict(default, user)
        assert result == {"a": 10, "b": 2}

    def test_user_value_preserved_at_correct_path(self):
        default = {"color": "blue"}
        user = {"color": "red"}
        result = FileUtils.merge_dict(default, user)
        assert result["color"] == "red"

    def test_orphan_key_pruned(self):
        default = {"a": 1}
        user = {"a": 1, "orphan": "gone"}
        result = FileUtils.merge_dict(default, user)
        assert "orphan" not in result

    def test_moved_key_uses_default_at_new_path(self):
        # 'foo' moved from top-level to nested in default; user still has old location
        default = {"category": {"foo": 42}}
        user = {"foo": 99, "category": {}}
        result = FileUtils.merge_dict(default, user)
        assert "foo" not in result             # old top-level entry removed
        assert result["category"]["foo"] == 42  # new path uses default value

    def test_setting_leaf_value_preserved(self):
        default = {
            "start_at_boot": {
                "type": "bool", "value": True, "default": True,
                "description": "Launch on boot."
            }
        }
        user = {
            "start_at_boot": {
                "type": "bool", "value": False, "default": True,
                "description": "Launch on boot."
            }
        }
        result = FileUtils.merge_dict(default, user)
        assert result["start_at_boot"]["value"] is False

    def test_setting_leaf_metadata_refreshed(self):
        default = {
            "start_at_boot": {
                "type": "bool", "value": True, "default": True,
                "description": "New description from update."
            }
        }
        user = {
            "start_at_boot": {
                "type": "bool", "value": False, "default": False,
                "description": "Old description."
            }
        }
        result = FileUtils.merge_dict(default, user)
        assert result["start_at_boot"]["value"] is False          # user value kept
        assert result["start_at_boot"]["default"] is True         # default refreshed
        assert result["start_at_boot"]["description"] == "New description from update."

    def test_type_mismatch_uses_default(self):
        default = {"nested": {"x": 1}}
        user = {"nested": "not-a-dict"}
        result = FileUtils.merge_dict(default, user)
        assert result["nested"] == {"x": 1}

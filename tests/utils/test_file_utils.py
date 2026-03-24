import yaml
import pytest
from pathlib import Path
from unittest.mock import MagicMock

from utils.file_utils import FileUtils, validate_snippet_fields


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


class TestSettingsValidation:
    """Tests for validate_setting_leaf and validate_merged_settings."""

    def _leaf(self, type_, value, default):
        return {"type": type_, "value": value, "default": default}

    def test_valid_string_leaf_returns_true(self):
        """String value for type='string' should return True and leave value unchanged."""
        leaf = self._leaf("string", "hello", "world")
        assert FileUtils.validate_setting_leaf("key", leaf) is True
        assert leaf["value"] == "hello"

    def test_valid_boolean_leaf_returns_true(self):
        """Bool value for type='boolean' should return True."""
        leaf = self._leaf("boolean", True, False)
        assert FileUtils.validate_setting_leaf("key", leaf) is True

    def test_valid_integer_leaf_returns_true(self):
        """Integer value for type='integer' should return True."""
        leaf = self._leaf("integer", 42, 0)
        assert FileUtils.validate_setting_leaf("key", leaf) is True

    def test_valid_float_leaf_returns_true(self):
        """Float value for type='float' should return True."""
        leaf = self._leaf("float", 3.14, 0.0)
        assert FileUtils.validate_setting_leaf("key", leaf) is True

    def test_invalid_type_resets_to_default(self):
        """Wrong type value should return False and reset leaf value to default."""
        leaf = self._leaf("boolean", "yes", False)
        result = FileUtils.validate_setting_leaf("key", leaf)
        assert result is False
        assert leaf["value"] is False

    def test_no_type_declared_returns_true(self):
        """Leaf without a 'type' key should return True without modification."""
        leaf = {"value": "anything", "default": "fallback"}
        assert FileUtils.validate_setting_leaf("key", leaf) is True
        assert leaf["value"] == "anything"

    def test_unknown_type_returns_true(self):
        """Unrecognised type string should return True (skip validation)."""
        leaf = self._leaf("custom", object(), None)
        assert FileUtils.validate_setting_leaf("key", leaf) is True

    def test_validate_merged_settings_fixes_nested_leaf(self):
        """A bad value nested inside a settings dict should be reset to its default."""
        merged = {
            "general": {
                "count": {"type": "integer", "value": "not-a-number", "default": 0}
            }
        }
        FileUtils.validate_merged_settings(merged)
        assert merged["general"]["count"]["value"] == 0

    def test_validate_merged_settings_skips_non_dict(self):
        """Scalar values at the top level should not cause errors."""
        merged = {"scalar_key": "just a string"}
        FileUtils.validate_merged_settings(merged)

    def test_load_and_merge_yaml_resets_bad_value(self, tmp_path):
        """End-to-end: a type-mismatched value in the user file is fixed on load."""
        default_path = tmp_path / "default.yaml"
        user_path = tmp_path / "user.yaml"

        import yaml

        default_path.write_text(yaml.dump({
            "theme": {
                "type": "string",
                "value": "light",
                "default": "light",
            }
        }), encoding="utf-8")

        user_path.write_text(yaml.dump({
            "theme": {
                "type": "string",
                "value": 12345,
                "default": "light",
            }
        }), encoding="utf-8")

        merged = FileUtils.load_and_merge_yaml(default_path, user_path)
        assert merged["theme"]["value"] == "light"


class TestValidateSnippetFieldsControlChars:
    """Tests for the control-character check added to validate_snippet_fields."""

    _VALID = {
        "enabled": True,
        "label": "My Label",
        "trigger": "/cmd",
        "snippet": "Hello",
        "paste_style": "clipboard",
        "return_press": False,
        "folder": "Misc",
        "tags": "a,b",
    }

    def test_control_char_in_trigger_raises(self):
        """Null byte in trigger should raise ValueError."""
        snippet = {**self._VALID, "trigger": "/cm\x00d"}
        with pytest.raises(ValueError, match="trigger"):
            validate_snippet_fields(snippet)

    def test_control_char_in_snippet_raises(self):
        """Escape char (0x1b) in snippet body should raise ValueError."""
        snippet = {**self._VALID, "snippet": "Hello\x1bWorld"}
        with pytest.raises(ValueError, match="snippet"):
            validate_snippet_fields(snippet)

    def test_del_char_in_label_raises(self):
        """DEL character (0x7f) in label should raise ValueError."""
        snippet = {**self._VALID, "label": "bad\x7flabel"}
        with pytest.raises(ValueError, match="label"):
            validate_snippet_fields(snippet)

    def test_control_char_in_optional_field_raises(self):
        """SOH character (0x01) in folder should raise ValueError."""
        snippet = {**self._VALID, "folder": "fold\x01er"}
        with pytest.raises(ValueError, match="folder"):
            validate_snippet_fields(snippet)

    def test_clean_snippet_passes(self):
        """Snippet with no control characters should raise no exception."""
        validate_snippet_fields(dict(self._VALID))

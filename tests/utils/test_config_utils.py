import yaml
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from utils.config_utils import ConfigLoader, SettingsLoader


def write_yaml(path: Path, data: dict):
    """
    Helper function to write YAML data to a file.

    Args:
        path (Path): The file path to write to.
        data (dict): The data dictionary to serialize as YAML.

    Returns:
        None
    """
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f)


def test_config_loader_initial_load(temp_config_file, mock_qt_app):
    """
    ConfigLoader should load YAML on init and emit configChanged.
    """
    data = {
        "program_name": "QSnippet",
        "version": "0.0.1",
    }
    write_yaml(temp_config_file, data)

    loader = ConfigLoader(temp_config_file)

    assert loader.config == data


def test_config_loader_empty_yaml(temp_config_file, mock_qt_app):
    """
    Empty YAML should load as empty dict.
    """
    temp_config_file.write_text("", encoding="utf-8")

    loader = ConfigLoader(temp_config_file)

    assert loader.config == {}


def test_config_loader_emits_signal_on_load(temp_config_file, mock_qt_app):
    """
    configChanged should emit on initial load.
    """
    data = {"key": "value"}
    write_yaml(temp_config_file, data)

    loader = ConfigLoader(temp_config_file)

    spy = MagicMock()
    loader.configChanged.connect(spy)

    # Manually reload
    loader.load_config()

    spy.assert_called_once_with(data)


def test_config_loader_reload_on_file_change(temp_config_file, mock_qt_app):
    """
    File change should reload config.
    """
    write_yaml(temp_config_file, {"a": 1})
    loader = ConfigLoader(temp_config_file, debounce_delay_ms=0)

    write_yaml(temp_config_file, {"a": 2})
    loader.on_file_changed(str(temp_config_file))

    assert loader.config["a"] == 2


def test_config_loader_stop(temp_config_file, mock_qt_app):
    """
    stop() should remove file from watcher.
    """
    write_yaml(temp_config_file, {"x": 1})
    loader = ConfigLoader(temp_config_file)

    watcher = loader._watcher
    remove_spy = MagicMock()
    watcher.removePath = remove_spy

    loader.stop()

    remove_spy.assert_called_once()


# SettingsLoader tests
def test_settings_loader_initial_load(temp_settings_file, mock_qt_app):
    """
    Test that SettingsLoader correctly loads and wraps YAML settings.

    Verifies that settings are loaded and wrapped with type information.
    """
    data = {
        "general": {
            "start_at_boot": True
        }
    }
    write_yaml(temp_settings_file, data)

    loader = SettingsLoader(temp_settings_file)

    assert loader.settings == {
        "general": {
            "start_at_boot": {
                "type": "bool",
                "value": True
            }
        }
    }


def test_settings_loader_empty_yaml(temp_settings_file, mock_qt_app):
    """
    Empty YAML should load as empty dict.
    """
    temp_settings_file.write_text("", encoding="utf-8")

    loader = SettingsLoader(temp_settings_file)

    assert loader.settings == {}


def test_settings_loader_emits_signal_on_load(temp_settings_file, mock_qt_app):
    """
    Test that settingsChanged signal is emitted on load.

    Verifies that the signal includes wrapped settings with type information.
    """
    data = {
        "general": {
            "foo": "bar"
        }
    }
    write_yaml(temp_settings_file, data)

    loader = SettingsLoader(temp_settings_file)

    spy = MagicMock()
    loader.settingsChanged.connect(spy)

    loader.load_settings()

    spy.assert_called_once_with({
        "general": {
            "foo": {
                "type": "string",
                "value": "bar"
            }
        }
    })


def test_settings_loader_reload_on_file_change(temp_settings_file, mock_qt_app):
    """
    Test that SettingsLoader reloads when the settings file changes.

    Verifies that file changes trigger reload with updated values.
    """
    write_yaml(temp_settings_file, {
        "general": {
            "enabled": False
        }
    })
    loader = SettingsLoader(temp_settings_file, debounce_delay_ms=0)

    write_yaml(temp_settings_file, {
        "general": {
            "enabled": True
        }
    })
    loader.on_file_changed(str(temp_settings_file))

    assert loader.settings["general"]["enabled"]["value"] is True


def test_settings_loader_stop(temp_settings_file, mock_qt_app):
    """
    stop() should remove file from watcher.
    """
    write_yaml(temp_settings_file, {"x": 1})
    loader = SettingsLoader(temp_settings_file)

    watcher = loader._watcher
    remove_spy = MagicMock()
    watcher.removePath = remove_spy

    loader.stop()

    remove_spy.assert_called_once()

import sys
from unittest.mock import MagicMock
import pytest

import utils.reg_utils as reg_utils
from utils.reg_utils import RegUtils


# ---------------------------
# Non-Windows behavior
# ---------------------------

def test_reg_utils_noop_on_non_windows(monkeypatch):
    """
    On non-Windows systems, registry functions should safely no-op.
    """
    # Force non-Windows platform
    monkeypatch.setattr(reg_utils.sys, "platform", "linux")
    monkeypatch.setattr(reg_utils, "winreg", None)

    RegUtils.add_to_run_key("fake.exe")
    RegUtils.remove_from_run_key("FakeApp")

    assert RegUtils.is_in_run_key("FakeApp") is False


# ---------------------------
# Windows behavior (mocked)
# ---------------------------

@pytest.fixture
def mock_windows_env(monkeypatch):
    """
    Mock Windows platform and winreg module.
    """
    # Force Windows platform
    monkeypatch.setattr(reg_utils.sys, "platform", "win32")

    mock = MagicMock()

    mock.HKEY_CURRENT_USER = object()
    mock.KEY_SET_VALUE = 1
    mock.KEY_READ = 2
    mock.REG_SZ = 1

    monkeypatch.setattr(reg_utils, "winreg", mock)
    return mock


def test_add_to_run_key_windows(mock_windows_env):
    """
    add_to_run_key should write correct registry value.
    """
    key = MagicMock()
    mock_windows_env.OpenKey.return_value.__enter__.return_value = key

    RegUtils.add_to_run_key("C:\\Test\\App.exe", "TestApp")

    mock_windows_env.OpenKey.assert_called_once()
    mock_windows_env.SetValueEx.assert_called_once()

    args, _ = mock_windows_env.SetValueEx.call_args
    assert args[1] == "TestApp"
    assert args[3] == mock_windows_env.REG_SZ
    assert args[4] == "\"C:\\Test\\App.exe\""


def test_remove_from_run_key_windows(mock_windows_env):
    """
    remove_from_run_key should delete registry value.
    """
    key = MagicMock()
    mock_windows_env.OpenKey.return_value.__enter__.return_value = key

    RegUtils.remove_from_run_key("TestApp")

    mock_windows_env.DeleteValue.assert_called_once_with(key, "TestApp")


def test_remove_from_run_key_missing_value(mock_windows_env):
    """
    Removing a missing key should not raise.
    """
    mock_windows_env.DeleteValue.side_effect = FileNotFoundError

    key = MagicMock()
    mock_windows_env.OpenKey.return_value.__enter__.return_value = key

    RegUtils.remove_from_run_key("MissingApp")


def test_is_in_run_key_true(mock_windows_env):
    """
    is_in_run_key should return True when value exists.
    """
    key = MagicMock()
    mock_windows_env.OpenKey.return_value.__enter__.return_value = key
    mock_windows_env.QueryValueEx.return_value = ("value", None)

    assert RegUtils.is_in_run_key("TestApp") is True


def test_is_in_run_key_false(mock_windows_env):
    """
    is_in_run_key should return False when value does not exist.
    """
    mock_windows_env.QueryValueEx.side_effect = FileNotFoundError

    key = MagicMock()
    mock_windows_env.OpenKey.return_value.__enter__.return_value = key

    assert RegUtils.is_in_run_key("MissingApp") is False

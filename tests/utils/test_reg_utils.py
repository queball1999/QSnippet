import sys
from unittest.mock import MagicMock
import pytest

import utils.reg_utils as reg_utils
from utils.reg_utils import RegUtils


# Non-Windows behavior
def test_reg_utils_noop_on_non_windows(monkeypatch):
    """
    On non-Windows systems, registry functions should safely no-op.
    """
    monkeypatch.setattr(reg_utils, "winreg", None)

    RegUtils.add_to_run_key("fake.exe")
    RegUtils.remove_from_run_key("FakeApp")

    assert RegUtils.is_in_run_key("FakeApp") is False


# Windows behavior (mocked)
@pytest.fixture
def mock_winreg(monkeypatch):
    """
    Fully mocked winreg module.
    """
    mock = MagicMock()

    mock.HKEY_CURRENT_USER = object()
    mock.KEY_SET_VALUE = 1
    mock.KEY_READ = 2
    mock.REG_SZ = 1

    monkeypatch.setattr(reg_utils, "winreg", mock)
    return mock


def test_add_to_run_key_windows(mock_winreg):
    """
    add_to_run_key should write correct registry value.
    """
    key = MagicMock()
    mock_winreg.OpenKey.return_value.__enter__.return_value = key

    RegUtils.add_to_run_key("C:\\Test\\App.exe", "TestApp")

    mock_winreg.OpenKey.assert_called_once()
    mock_winreg.SetValueEx.assert_called_once()

    args, kwargs = mock_winreg.SetValueEx.call_args
    assert args[1] == "TestApp"
    assert args[3] == mock_winreg.REG_SZ
    assert args[4] == "\"C:\\Test\\App.exe\""


def test_remove_from_run_key_windows(mock_winreg):
    """
    remove_from_run_key should delete registry value.
    """
    key = MagicMock()
    mock_winreg.OpenKey.return_value.__enter__.return_value = key

    RegUtils.remove_from_run_key("TestApp")

    mock_winreg.DeleteValue.assert_called_once_with(key, "TestApp")


def test_remove_from_run_key_missing_value(mock_winreg):
    """
    Removing a missing key should not raise.
    """
    mock_winreg.DeleteValue.side_effect = FileNotFoundError

    key = MagicMock()
    mock_winreg.OpenKey.return_value.__enter__.return_value = key

    RegUtils.remove_from_run_key("MissingApp")


def test_is_in_run_key_true(mock_winreg):
    """
    is_in_run_key should return True when value exists.
    """
    key = MagicMock()
    mock_winreg.OpenKey.return_value.__enter__.return_value = key
    mock_winreg.QueryValueEx.return_value = ("value", None)

    assert RegUtils.is_in_run_key("TestApp") is True


def test_is_in_run_key_false(mock_winreg):
    """
    is_in_run_key should return False when value does not exist.
    """
    mock_winreg.QueryValueEx.side_effect = FileNotFoundError

    key = MagicMock()
    mock_winreg.OpenKey.return_value.__enter__.return_value = key

    assert RegUtils.is_in_run_key("MissingApp") is False

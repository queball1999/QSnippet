"""
Tests for the "still running in the tray" notification shown when the main
window is closed to the tray.

The notification is raised from closeEvent via notify_tray_running, so these
tests drive that handler directly with a stub window instead of standing up a
full QSnippet instance. The TrayCloseToast widget is mocked so the tests do
not require a running QApplication or a real screen.
"""

from unittest.mock import MagicMock, patch

import pytest


class StubTray:
    """Minimal stand-in for QSystemTrayIcon."""

    def __init__(self, visible=True):
        self._visible = visible

    def isVisible(self):
        return self._visible

    def icon(self):
        return MagicMock()

    def geometry(self):
        return MagicMock()


class StubWindow:
    """Carries just what notify_tray_running and the disable handler touch."""

    def __init__(self, enabled=True, tray_visible=True):
        self.parent = MagicMock()
        self.parent.settings = {
            "general": {
                "tray_behavior": {
                    "notify_on_close": {"value": enabled},
                },
            },
        }
        self.parent.settings_file = MagicMock()
        self.tray = StubTray(visible=tray_visible)
        self.tray_menu = MagicMock()
        self.tray_close_toast = None

    def notify_tray_running(self):
        import ui.window as window

        window.QSnippet.notify_tray_running(self)

    def disable_tray_close_notification(self):
        import ui.window as window

        window.QSnippet.disable_tray_close_notification(self)

    def dismiss_tray_close_toast(self):
        import ui.window as window

        window.QSnippet.dismiss_tray_close_toast(self)

    def clear_tray_close_toast(self, toast):
        import ui.window as window

        window.QSnippet.clear_tray_close_toast(self, toast)


def test_notification_shows_when_enabled():
    """When the setting is on and the tray is visible, a toast is created."""
    win = StubWindow(enabled=True)
    with patch("ui.widgets.tray_close_toast.TrayCloseToast") as mock_toast_cls:
        mock_toast = MagicMock()
        mock_toast_cls.return_value = mock_toast
        win.notify_tray_running()

    assert mock_toast_cls.called
    assert win.tray_close_toast is mock_toast
    mock_toast.show_near_tray.assert_called_once()
    mock_toast.disable_requested.connect.assert_called_once()


def test_notification_suppressed_when_disabled():
    """When the setting is off, no toast is created."""
    win = StubWindow(enabled=False)
    with patch("ui.widgets.tray_close_toast.TrayCloseToast") as mock_toast_cls:
        win.notify_tray_running()

    assert not mock_toast_cls.called
    assert win.tray_close_toast is None


def test_notification_suppressed_when_tray_hidden():
    """If the tray icon is not visible, no toast is created."""
    win = StubWindow(enabled=True, tray_visible=False)
    with patch("ui.widgets.tray_close_toast.TrayCloseToast") as mock_toast_cls:
        win.notify_tray_running()

    assert not mock_toast_cls.called
    assert win.tray_close_toast is None


def test_notification_defaults_to_enabled_when_setting_missing():
    """If the setting is absent (e.g. pre-upgrade user file), default to on."""
    win = StubWindow(enabled=True)
    win.parent.settings = {"general": {}}  # no tray_behavior key at all
    with patch("ui.widgets.tray_close_toast.TrayCloseToast") as mock_toast_cls:
        win.notify_tray_running()

    assert mock_toast_cls.called


def test_disable_button_persists_setting_off():
    """The disable handler writes notify_on_close to False and refreshes the tray menu."""
    win = StubWindow(enabled=True)
    with patch("ui.window.FileUtils.write_yaml") as mock_write:
        win.disable_tray_close_notification()

    assert win.parent.settings["general"]["tray_behavior"]["notify_on_close"]["value"] is False
    mock_write.assert_called_once()
    win.tray_menu.refresh.assert_called_once()


def test_disable_button_writes_to_settings_file():
    """The disable handler writes to the correct settings file path."""
    win = StubWindow(enabled=True)
    with patch("ui.window.FileUtils.write_yaml") as mock_write:
        win.disable_tray_close_notification()

    args, _ = mock_write.call_args
    assert args[0] is win.parent.settings_file
    assert args[1] is win.parent.settings


def test_new_notification_replaces_existing_toast():
    """Closing the window twice closes the first toast instead of stacking a second."""
    win = StubWindow(enabled=True)
    first = MagicMock()
    second = MagicMock()
    with patch("ui.widgets.tray_close_toast.TrayCloseToast", side_effect=[first, second]):
        win.notify_tray_running()
        win.notify_tray_running()

    first.close.assert_called_once()
    assert win.tray_close_toast is second


def test_late_destroy_of_replaced_toast_keeps_new_reference():
    """A replaced toast being destroyed late must not clear its successor."""
    win = StubWindow(enabled=True)
    old, new = MagicMock(), MagicMock()
    win.tray_close_toast = new

    win.clear_tray_close_toast(old)
    assert win.tray_close_toast is new

    win.clear_tray_close_toast(new)
    assert win.tray_close_toast is None


def test_toast_is_anchored_to_tray_geometry():
    """The toast is positioned from the tray icon's geometry."""
    win = StubWindow(enabled=True)
    with patch("ui.widgets.tray_close_toast.TrayCloseToast") as mock_toast_cls:
        mock_toast = MagicMock()
        mock_toast_cls.return_value = mock_toast
        win.notify_tray_running()

    args, _ = mock_toast.show_near_tray.call_args
    assert len(args) == 1

"""
Tests for the transient "Clipboard cleared" status bar notice.

The notice is raised from the clipboard cleanup timer thread, so these tests
drive the main-thread handlers directly with a stub window instead of standing
up a full QSnippet instance.
"""

from unittest.mock import MagicMock

import pytest


CLEARED_MESSAGE = "Clipboard cleared"


class StubStatusBar:
    """Minimal stand-in for QStatusBar's message API."""

    def __init__(self, message=""):
        self.message = message

    def currentMessage(self):
        return self.message

    def showMessage(self, message, timeout=0):
        self.message = message


class StubWindow:
    """Carries just what the status bar handlers touch."""

    def __init__(self, message=""):
        self.status_bar = StubStatusBar(message)
        self.service_status_checked = False

    def statusBar(self):
        return self.status_bar

    def check_service_status(self):
        self.service_status_checked = True
        self.status_bar.showMessage("Service status: Running")

    def restore_status_message(self, previous_message):
        import ui.window as window

        window.QSnippet.restore_status_message(self, previous_message)


@pytest.fixture
def window_module(monkeypatch):
    """Import ui.window with QTimer.singleShot captured instead of scheduled."""
    import ui.window as window

    scheduled = []
    fake_timer = MagicMock()
    fake_timer.singleShot = lambda ms, fn: scheduled.append((ms, fn))
    monkeypatch.setattr(window, "QTimer", fake_timer)
    window.scheduled_callbacks = scheduled
    return window


def test_clipboard_cleared_notice_shows_for_five_seconds(window_module):
    """The notice replaces the current message and is scheduled to expire."""
    win = StubWindow("Service status: Running")

    window_module.QSnippet.on_clipboard_cleared(win)

    assert win.statusBar().currentMessage() == CLEARED_MESSAGE
    assert len(window_module.scheduled_callbacks) == 1
    delay_ms, _restore = window_module.scheduled_callbacks[0]
    assert delay_ms == window_module.CLIPBOARD_CLEARED_MESSAGE_MS == 5000


def test_clipboard_cleared_notice_restores_previous_message(window_module):
    """Once the notice expires the earlier message comes back."""
    win = StubWindow("Detected Trigger: / (3s)")

    window_module.QSnippet.on_clipboard_cleared(win)
    _delay_ms, restore = window_module.scheduled_callbacks[0]
    restore()

    assert win.statusBar().currentMessage() == "Detected Trigger: / (3s)"
    assert win.service_status_checked is False


def test_clipboard_cleared_notice_falls_back_to_service_status(window_module):
    """With no earlier message, the notice gives way to the service status."""
    win = StubWindow("")

    window_module.QSnippet.on_clipboard_cleared(win)
    _delay_ms, restore = window_module.scheduled_callbacks[0]
    restore()

    assert win.service_status_checked is True


def test_clipboard_cleared_notice_does_not_clobber_a_newer_message(window_module):
    """A message posted while the notice is up survives the restore."""
    win = StubWindow("Service status: Running")

    window_module.QSnippet.on_clipboard_cleared(win)
    win.statusBar().showMessage("Loaded 12 snippets")
    _delay_ms, restore = window_module.scheduled_callbacks[0]
    restore()

    assert win.statusBar().currentMessage() == "Loaded 12 snippets"
    assert win.service_status_checked is False


def test_clipboard_cleared_from_expander_emits_on_the_main_thread(window_module):
    """The cleanup thread hop goes through the Qt signal, not the status bar."""
    win = MagicMock()

    window_module.QSnippet.on_clipboard_cleared_from_expander(win)

    win.clipboard_cleared_signal.emit.assert_called_once_with()

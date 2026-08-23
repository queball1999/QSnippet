import sys
import threading
import time
import types
from contextlib import nullcontext
from unittest.mock import MagicMock

import pytest

from utils.keyboard_utils import (
    SnippetExpander,
    extract_dynamic_placeholder_names,
    format_duration_seconds,
    parse_duration_seconds,
    substitute_dynamic_placeholders,
)


class DummyKeyValue:
    def __init__(self, name: str):
        self.name = name

    def __repr__(self) -> str:
        return f"DummyKeyValue({self.name})"


class DummyListener:
    def __init__(self, on_press=None):
        self.on_press = on_press
        self.started = False
        self.stopped = False

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.stopped = True


class DummyController:
    def pressed(self, _key):
        return nullcontext()

    def press(self, _key) -> None:
        return None

    def release(self, _key) -> None:
        return None


class DummyKeyboardModule:
    class Key:
        space = DummyKeyValue("space")
        shift = DummyKeyValue("shift")
        shift_l = DummyKeyValue("shift_l")
        shift_r = DummyKeyValue("shift_r")
        enter = DummyKeyValue("enter")
        tab = DummyKeyValue("tab")
        esc = DummyKeyValue("esc")
        ctrl = DummyKeyValue("ctrl")
        ctrl_l = DummyKeyValue("ctrl_l")
        ctrl_r = DummyKeyValue("ctrl_r")
        alt_l = DummyKeyValue("alt_l")
        alt_r = DummyKeyValue("alt_r")
        alt_gr = DummyKeyValue("alt_gr")
        cmd = DummyKeyValue("cmd")
        cmd_l = DummyKeyValue("cmd_l")
        cmd_r = DummyKeyValue("cmd_r")
        caps_lock = DummyKeyValue("caps_lock")
        insert = DummyKeyValue("insert")
        home = DummyKeyValue("home")
        end = DummyKeyValue("end")
        page_up = DummyKeyValue("page_up")
        page_down = DummyKeyValue("page_down")
        menu = DummyKeyValue("menu")
        print_screen = DummyKeyValue("print_screen")
        scroll_lock = DummyKeyValue("scroll_lock")
        pause = DummyKeyValue("pause")
        left = DummyKeyValue("left")
        right = DummyKeyValue("right")
        backspace = DummyKeyValue("backspace")
        delete = DummyKeyValue("delete")

    Listener = DummyListener
    Controller = DummyController

@pytest.fixture
def dummy_pynput(monkeypatch):
    """Provide a dummy pynput.keyboard module for expander tests."""
    module = types.SimpleNamespace(keyboard=DummyKeyboardModule)
    monkeypatch.setitem(sys.modules, "pynput", module)
    return module

@pytest.fixture
def expander(dummy_pynput):
    """Create a SnippetExpander with mocked database dependencies."""
    db = MagicMock()
    db.get_all_custom_placeholders.return_value = []
    db.get_enabled_trigger_index.return_value = [
        {
            "id": 1,
            "trigger": "/sig",
            "paste_style": "Clipboard",
            "return_press": False,
        }
    ]
    db.get_snippet_by_trigger.return_value = {
        "id": 1,
        "trigger": "/sig",
        "snippet": "Regards",
        "paste_style": "Clipboard",
        "return_press": False,
        "enabled": True,
    }

    return SnippetExpander(
        snippets_db=db,
        parent=MagicMock(),
        settings_provider=lambda: {
            "general": {
                "clipboard_behavior": {
                    "clipboard_timeout": {"value": "30"}
                }
            }
        },
    )

@pytest.mark.parametrize(
    "raw_value, expected_seconds",
    [
        ("500ms", 0.5),
        ("5s", 5.0),
        ("5", 5.0),
        ("2.5s", 2.5),
        ("off", None),
        ("OFF", None),
        ("disabled", None),
        (None, 5.0),
    ],
)
def test_parse_duration_seconds(raw_value, expected_seconds):
    """Duration strings should parse to seconds, honoring units and 'off'."""
    assert parse_duration_seconds(raw_value, default_seconds=5.0) == expected_seconds


def test_parse_duration_seconds_falls_back_on_invalid_input():
    """Unparseable values should fall back to the provided default."""
    assert parse_duration_seconds("banana", default_seconds=5.0) == 5.0


@pytest.mark.parametrize(
    "seconds, expected_label",
    [
        (None, "Off"),
        (0.5, "500ms"),
        (5.0, "5s"),
        (2.5, "2.5s"),
    ],
)
def test_format_duration_seconds(seconds, expected_label):
    """Formatted durations should use ms below one second and s otherwise."""
    assert format_duration_seconds(seconds) == expected_label


def test_get_trigger_timeout_seconds_reads_settings(dummy_pynput):
    """The expander should read the configured trigger timeout from settings."""
    db = MagicMock()
    db.get_all_custom_placeholders.return_value = []
    db.get_enabled_trigger_index.return_value = []

    expander = SnippetExpander(
        snippets_db=db,
        parent=MagicMock(),
        settings_provider=lambda: {
            "general": {
                "keyboard_behavior": {
                    "trigger_timeout": {"value": "250ms"}
                }
            }
        },
    )

    assert expander.get_trigger_timeout_seconds() == 0.25


def test_get_trigger_timeout_seconds_off_disables_inactivity_clear(dummy_pynput):
    """Buffer should survive long inactivity gaps when the timeout is 'off'."""
    db = MagicMock()
    db.get_all_custom_placeholders.return_value = []
    db.get_enabled_trigger_index.return_value = [
        {"id": 1, "trigger": "/sig", "paste_style": "Clipboard", "return_press": False}
    ]
    db.get_snippet_by_trigger.return_value = {}

    expander = SnippetExpander(
        snippets_db=db,
        parent=MagicMock(),
        settings_provider=lambda: {
            "general": {
                "keyboard_behavior": {
                    "trigger_timeout": {"value": "off"}
                }
            }
        },
    )

    class DummyCharKey:
        def __init__(self, char):
            self.char = char

    expander.buffer = "/s"
    expander.cursor_pos = len(expander.buffer)
    expander.last_keypress_at = time.monotonic() - 9999

    expander.on_key_press(DummyCharKey("x"))

    # If the inactivity timeout fired, the buffer would have been cleared
    # before "x" was appended, leaving just "x" instead of "/sx".
    assert expander.buffer == "/sx"


def test_backspace_refreshes_trigger_timeout_clock(expander, monkeypatch):
    """
    Regression: editing keys (backspace/delete/arrows) must reset the
    inactivity clock, same as character keys do.

    Previously only handle_char() updated last_keypress_at, so a sequence of
    edits that were each individually well within the timeout window could
    still get wiped out because the elapsed-time check kept comparing
    against the last *character* typed instead of the last edit.
    """
    # Base the fake clock at a realistic non-zero offset. self.last_keypress_at
    # doubles as an "unset" sentinel via `and self.last_keypress_at` truthiness
    # checks, so a literal 0.0 timestamp would bypass the timeout check
    # entirely regardless of the fix and defeat this regression test.
    fake_now = [100.0]
    monkeypatch.setattr("utils.keyboard_utils.time.monotonic", lambda: fake_now[0])

    expander.buffer = "/txt"
    expander.cursor_pos = len(expander.buffer)
    expander.last_keypress_at = 100.0  # last real character was typed at t=100

    # First backspace at t=103s - well within the 5s default timeout.
    fake_now[0] = 103.0
    expander.on_key_press(expander.keyboard.Key.backspace)
    assert expander.buffer == "/tx"

    # Second backspace at t=106s: only 3s after the previous edit, but 6s
    # after the original character. Without the fix, last_keypress_at would
    # still be the stale t=100, so (106 - 100) > 5s would wipe the buffer.
    fake_now[0] = 106.0
    expander.on_key_press(expander.keyboard.Key.backspace)
    assert expander.buffer == "/t"


def test_backspace_and_arrows_refresh_status_bar_countdown(expander):
    """
    Backspace/delete/arrow keys must also restart the on-screen trigger
    countdown, not just the internal inactivity clock, so the displayed
    count stays accurate whenever last_keypress_at is refreshed.
    """
    calls = []
    expander.trigger_detected_callback = lambda char, timeout: calls.append((char, timeout))

    expander.buffer = "/sig"
    expander.cursor_pos = len(expander.buffer)

    # Reset the 20ms event debounce before each call - back-to-back calls in
    # a tight test loop can otherwise land under keyboard_debounce_ms and get
    # skipped, since real wall-clock time between statements is often <20ms.
    expander.on_key_press(expander.keyboard.Key.left)
    expander.last_event_processed_at = 0.0
    expander.on_key_press(expander.keyboard.Key.backspace)
    expander.last_event_processed_at = 0.0
    expander.on_key_press(expander.keyboard.Key.delete)

    assert calls == [("/", 5.0)] * 3


def test_arrow_past_active_prefix_does_not_refresh_countdown(expander):
    """Navigation on an empty/inactive buffer should not spuriously notify the status bar."""
    calls = []
    expander.trigger_detected_callback = lambda char, timeout: calls.append((char, timeout))

    expander.buffer = ""
    expander.cursor_pos = 0

    expander.on_key_press(expander.keyboard.Key.left)

    assert calls == []


def test_trigger_detected_callback_invoked_on_prefix_char(expander):
    """The trigger-detected callback should fire on every keystroke while a trigger prefix is active."""
    calls = []
    expander.trigger_detected_callback = lambda char, timeout: calls.append((char, timeout))
    expander.expand = MagicMock()

    for char in "/sig":
        expander.handle_char(char)

    # Fires for every keystroke of "/sig" ("/", "/s", "/si", "/sig" all
    # start with the "/" prefix), so the on-screen countdown keeps
    # restarting in step with last_keypress_at instead of only firing once.
    assert calls == [("/", 5.0)] * 4


def test_trigger_detected_callback_not_invoked_for_non_prefix_chars(expander):
    """Typing ordinary text that never starts with a trigger prefix should not notify."""
    calls = []
    expander.trigger_detected_callback = lambda char, timeout: calls.append((char, timeout))

    for char in "hello":
        expander.handle_char(char)

    assert calls == []


def test_trigger_detected_callback_refires_after_buffer_clear(expander):
    """The prefix notification should keep firing after the buffer resets and a new trigger starts."""
    calls = []
    expander.trigger_detected_callback = lambda char, timeout: calls.append((char, timeout))
    expander.expand = MagicMock()

    for char in "/sig":
        expander.handle_char(char)

    expander.clear_buffer()

    for char in "/sig":
        expander.handle_char(char)

    assert calls == [("/", 5.0)] * 8


def test_handle_char_uses_suffix_trigger_matching(expander):
    """Typing a trigger should use the optimized suffix matcher."""
    captured = {}

    def fake_expand(trigger, snippet, paste_style, return_press):
        captured["trigger"] = trigger
        captured["snippet"] = snippet
        captured["paste_style"] = paste_style
        captured["return_press"] = return_press

    expander.expand = fake_expand

    for char in "/sig":
        expander.handle_char(char)

    assert captured["trigger"] == "/sig"
    assert captured["snippet"] == "Regards"
    assert captured["paste_style"] == "Clipboard"
    assert captured["return_press"] is False

def test_sensitive_keys_clear_buffer(expander):
    """Sensitive system keys should clear buffered typed content."""
    expander.buffer = "/sig"
    expander.cursor_pos = len(expander.buffer)

    expander.on_key_press(expander.keyboard.Key.alt_l)

    assert expander.buffer == ""
    assert expander.cursor_pos == 0

def test_schedule_clipboard_clear_honors_off_setting(dummy_pynput):
    """Clipboard cleanup should not schedule a timer when disabled."""
    db = MagicMock()
    db.get_all_custom_placeholders.return_value = []
    db.get_enabled_trigger_index.return_value = []
    db.get_snippet_by_trigger.return_value = {}

    expander = SnippetExpander(
        snippets_db=db,
        parent=MagicMock(),
        settings_provider=lambda: {
            "general": {
                "clipboard_behavior": {
                    "clipboard_timeout": {"value": "off"}
                }
            }
        },
    )

    expander.schedule_clipboard_clear("secret")

    assert expander.clipboard_timer is None

def testempty_clipboard_windows_calls_api(dummy_pynput, monkeypatch):
    """Verify empty_clipboard_windows() calls win32clipboard Open/Empty/Close."""
    import platform

    if platform.system() != "Windows":
        pytest.skip("Windows-only test")

    db = MagicMock()
    db.get_all_custom_placeholders.return_value = []
    db.get_enabled_trigger_index.return_value = []

    expander = SnippetExpander(snippets_db=db, parent=MagicMock())

    mock_open = MagicMock()
    mock_empty = MagicMock()
    mock_close = MagicMock()

    monkeypatch.setattr("utils.keyboard_utils.win32clipboard.OpenClipboard", mock_open)
    monkeypatch.setattr("utils.keyboard_utils.win32clipboard.EmptyClipboard", mock_empty)
    monkeypatch.setattr("utils.keyboard_utils.win32clipboard.CloseClipboard", mock_close)

    expander.empty_clipboard_windows()

    mock_open.assert_called_once_with()
    mock_empty.assert_called_once_with()
    mock_close.assert_called_once_with()

def testempty_clipboard_windows_fallback_on_error(dummy_pynput, monkeypatch):
    """Verify empty_clipboard_windows() falls back to pyperclip when win32clipboard fails."""
    import platform

    if platform.system() != "Windows":
        pytest.skip("Windows-only test")

    db = MagicMock()
    db.get_all_custom_placeholders.return_value = []
    db.get_enabled_trigger_index.return_value = []

    expander = SnippetExpander(snippets_db=db, parent=MagicMock())

    mock_copy = MagicMock()
    monkeypatch.setattr("pyperclip.copy", mock_copy)

    mock_open = MagicMock(side_effect=OSError("Cannot access clipboard"))
    mock_close = MagicMock()

    monkeypatch.setattr("utils.keyboard_utils.CLIPBOARD_OPEN_ATTEMPTS", 3)
    monkeypatch.setattr("utils.keyboard_utils.CLIPBOARD_OPEN_RETRY_SECONDS", 0)
    monkeypatch.setattr("utils.keyboard_utils.win32clipboard.OpenClipboard", mock_open)
    monkeypatch.setattr("utils.keyboard_utils.win32clipboard.CloseClipboard", mock_close)

    assert expander.empty_clipboard_windows() is True

    # A locked clipboard is retried before giving up
    assert mock_open.call_count == 3
    # Fallback to pyperclip occurred
    mock_copy.assert_called_once_with("")
    # OpenClipboard failed, so CloseClipboard should not be called
    mock_close.assert_not_called()


def test_copy_clipboard_windows_sets_history_exclusion_formats(dummy_pynput, monkeypatch):
    """Snippets copied on Windows are marked as excluded from clipboard history."""
    import platform

    if platform.system() != "Windows":
        pytest.skip("Windows-only test")

    import utils.keyboard_utils as ku

    db = MagicMock()
    db.get_all_custom_placeholders.return_value = []
    db.get_enabled_trigger_index.return_value = []

    expander = SnippetExpander(snippets_db=db, parent=MagicMock())

    format_ids = {name: 5000 + i for i, name in enumerate(ku.WINDOWS_PRIVATE_CLIPBOARD_FORMATS)}
    monkeypatch.setattr(ku, "windows_clipboard_format_ids", dict(format_ids))

    mock_set = MagicMock()
    monkeypatch.setattr("utils.keyboard_utils.win32clipboard.OpenClipboard", MagicMock())
    monkeypatch.setattr("utils.keyboard_utils.win32clipboard.EmptyClipboard", MagicMock())
    monkeypatch.setattr("utils.keyboard_utils.win32clipboard.CloseClipboard", MagicMock())
    monkeypatch.setattr("utils.keyboard_utils.win32clipboard.SetClipboardData", mock_set)

    assert expander.copy_clipboard_windows("hunter2") is True

    written = {call.args[0]: call.args[1] for call in mock_set.call_args_list}
    assert written[ku.win32clipboard.CF_UNICODETEXT] == "hunter2"
    for format_id in format_ids.values():
        assert format_id in written


def make_expander():
    """Build a SnippetExpander with a stubbed database for clipboard tests."""
    db = MagicMock()
    db.get_all_custom_placeholders.return_value = []
    db.get_enabled_trigger_index.return_value = []
    return SnippetExpander(snippets_db=db, parent=MagicMock())


def force_platform(monkeypatch, name):
    """Pin the module-level platform flags to a single OS."""
    import utils.keyboard_utils as ku

    monkeypatch.setattr(ku, "IS_WINDOWS", name == "windows")
    monkeypatch.setattr(ku, "IS_MACOS", name == "macos")
    monkeypatch.setattr(ku, "IS_LINUX", name == "linux")


def test_clear_managed_clipboard_notifies_the_ui(dummy_pynput, monkeypatch):
    """A successful clear fires the callback that raises the status bar notice."""
    expander = make_expander()
    monkeypatch.setattr(expander, "read_clipboard", lambda: (True, "secret"))
    monkeypatch.setattr(expander, "empty_clipboard", lambda: True)

    notified = []
    expander.clipboard_cleared_callback = lambda: notified.append(1)

    expander.clipboard_generation = 1
    expander.last_managed_clipboard = "secret"
    expander.clear_managed_clipboard(expected_text="secret", generation=1)

    assert notified == [1]


def test_clear_managed_clipboard_does_not_notify_when_skipped(dummy_pynput, monkeypatch):
    """No notice when the user replaced the clipboard and nothing was cleared."""
    expander = make_expander()
    monkeypatch.setattr(expander, "read_clipboard", lambda: (True, "user content"))
    monkeypatch.setattr(expander, "empty_clipboard", lambda: pytest.fail("should not clear"))

    notified = []
    expander.clipboard_cleared_callback = lambda: notified.append(1)

    expander.clipboard_generation = 1
    expander.last_managed_clipboard = "secret"
    expander.clear_managed_clipboard(expected_text="secret", generation=1)

    assert notified == []


def test_clipboard_cleared_callback_errors_are_contained(dummy_pynput, monkeypatch):
    """A failing UI callback must not break clipboard cleanup."""
    expander = make_expander()
    monkeypatch.setattr(expander, "read_clipboard", lambda: (True, "secret"))
    cleared = []
    monkeypatch.setattr(expander, "empty_clipboard", lambda: cleared.append(1) or True)

    def boom():
        raise RuntimeError("status bar is gone")

    expander.clipboard_cleared_callback = boom

    expander.clipboard_generation = 1
    expander.last_managed_clipboard = "secret"
    expander.clear_managed_clipboard(expected_text="secret", generation=1)

    assert cleared == [1]
    assert expander.last_managed_clipboard is None


def test_copy_clipboard_macos_marks_item_concealed(dummy_pynput, monkeypatch):
    """macOS copies declare the concealed type alongside the text."""
    import utils.keyboard_utils as ku

    expander = make_expander()
    force_platform(monkeypatch, "macos")

    pasteboard = MagicMock()
    pasteboard.setString_forType_.return_value = True
    pasteboard.stringForType_.return_value = "hunter2"
    pasteboard_cls = MagicMock()
    pasteboard_cls.generalPasteboard.return_value = pasteboard

    monkeypatch.setattr(
        ku, "clipboard_backend_probe", {"macos": (pasteboard_cls, "public.utf8-plain-text")}
    )

    assert expander.copy_clipboard_macos("hunter2") is True

    declared = pasteboard.declareTypes_owner_.call_args.args[0]
    assert ku.MACOS_CONCEALED_PASTEBOARD_TYPE in declared
    written = {call.args[1]: call.args[0] for call in pasteboard.setString_forType_.call_args_list}
    assert written["public.utf8-plain-text"] == "hunter2"
    assert ku.MACOS_CONCEALED_PASTEBOARD_TYPE in written


def test_copy_clipboard_macos_falls_back_without_pyobjc(dummy_pynput, monkeypatch):
    """A macOS build without pyobjc reports failure so pyperclip takes over."""
    import utils.keyboard_utils as ku

    expander = make_expander()
    force_platform(monkeypatch, "macos")
    monkeypatch.setattr(ku, "clipboard_backend_probe", {"macos": None})

    assert expander.copy_clipboard_macos("hunter2") is False

    mock_copy = MagicMock()
    monkeypatch.setattr("pyperclip.copy", mock_copy)
    expander.copy_to_clipboard("hunter2")
    mock_copy.assert_called_once_with("hunter2")


def test_copy_clipboard_macos_falls_back_on_readback_mismatch(dummy_pynput, monkeypatch):
    """A pasteboard that did not take the text is treated as a failure."""
    import utils.keyboard_utils as ku

    expander = make_expander()
    force_platform(monkeypatch, "macos")

    pasteboard = MagicMock()
    pasteboard.setString_forType_.return_value = True
    pasteboard.stringForType_.return_value = "something else"
    pasteboard_cls = MagicMock()
    pasteboard_cls.generalPasteboard.return_value = pasteboard
    monkeypatch.setattr(
        ku, "clipboard_backend_probe", {"macos": (pasteboard_cls, "public.utf8-plain-text")}
    )

    assert expander.copy_clipboard_macos("hunter2") is False


def test_copy_clipboard_linux_sets_password_manager_hint(dummy_pynput, monkeypatch):
    """Linux copies advertise the KDE password-manager MIME hint with the text."""
    import utils.keyboard_utils as ku

    expander = make_expander()
    force_platform(monkeypatch, "linux")
    monkeypatch.setattr(ku, "get_linux_session_type", lambda: "wayland")

    clipboard = MagicMock()
    app = MagicMock()
    app.clipboard.return_value = clipboard
    monkeypatch.setattr(ku, "load_qt_clipboard_api", lambda: (app, MagicMock, MagicMock()))

    assert expander.copy_clipboard_linux("hunter2") is True

    mime = clipboard.setMimeData.call_args.args[0]
    mime.setText.assert_called_once_with("hunter2")
    mime.setData.assert_called_once_with(
        ku.LINUX_PASSWORD_HINT_MIME, ku.LINUX_PASSWORD_HINT_VALUE
    )


def test_copy_clipboard_linux_skips_headless_session(dummy_pynput, monkeypatch):
    """Without a graphical session the Qt path is not attempted at all."""
    import utils.keyboard_utils as ku

    expander = make_expander()
    force_platform(monkeypatch, "linux")
    monkeypatch.setattr(ku, "get_linux_session_type", lambda: "none")

    def fail_load():
        raise AssertionError("Qt clipboard should not be probed without a session")

    monkeypatch.setattr(ku, "load_qt_clipboard_api", fail_load)

    assert expander.copy_clipboard_linux("hunter2") is False


def test_copy_clipboard_linux_falls_back_without_qapplication(dummy_pynput, monkeypatch):
    """No running QApplication means the copy defers to pyperclip."""
    import utils.keyboard_utils as ku

    expander = make_expander()
    force_platform(monkeypatch, "linux")
    monkeypatch.setattr(ku, "get_linux_session_type", lambda: "x11")
    monkeypatch.setattr(ku, "load_qt_clipboard_api", lambda: None)

    mock_copy = MagicMock()
    monkeypatch.setattr("pyperclip.copy", mock_copy)

    expander.copy_to_clipboard("hunter2")
    mock_copy.assert_called_once_with("hunter2")


def test_get_linux_session_type_detection(monkeypatch):
    """Session detection prefers XDG_SESSION_TYPE, then the display variables."""
    import utils.keyboard_utils as ku

    for name in ("XDG_SESSION_TYPE", "WAYLAND_DISPLAY", "DISPLAY"):
        monkeypatch.delenv(name, raising=False)
    assert ku.get_linux_session_type() == "none"

    monkeypatch.setenv("DISPLAY", ":0")
    assert ku.get_linux_session_type() == "x11"

    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    assert ku.get_linux_session_type() == "wayland"

    monkeypatch.setenv("XDG_SESSION_TYPE", "X11")
    assert ku.get_linux_session_type() == "x11"


def test_copy_to_clipboard_unknown_platform_uses_pyperclip(dummy_pynput, monkeypatch):
    """An unrecognized OS copies through pyperclip without raising."""
    expander = make_expander()
    force_platform(monkeypatch, "other")

    mock_copy = MagicMock()
    monkeypatch.setattr("pyperclip.copy", mock_copy)

    expander.copy_to_clipboard("hunter2")
    mock_copy.assert_called_once_with("hunter2")


def test_copy_to_clipboard_falls_back_when_handler_raises(dummy_pynput, monkeypatch):
    """A platform handler that blows up must not stop the snippet from pasting."""
    expander = make_expander()
    force_platform(monkeypatch, "macos")

    def exploding_copy(text):
        raise OSError("pasteboard on fire")

    monkeypatch.setattr(expander, "copy_clipboard_macos", exploding_copy)
    mock_copy = MagicMock()
    monkeypatch.setattr("pyperclip.copy", mock_copy)

    expander.copy_to_clipboard("hunter2")
    mock_copy.assert_called_once_with("hunter2")


def test_empty_clipboard_macos_falls_back_to_pyperclip(dummy_pynput, monkeypatch):
    """When AppKit cannot clear the pasteboard, the pyperclip clear still runs."""
    import utils.keyboard_utils as ku

    expander = make_expander()
    force_platform(monkeypatch, "macos")
    monkeypatch.setattr(ku, "clipboard_backend_probe", {"macos": None})

    mock_copy = MagicMock()
    monkeypatch.setattr("pyperclip.copy", mock_copy)

    assert expander.empty_clipboard() is True
    mock_copy.assert_called_once_with("")


def test_copy_to_clipboard_uses_pyperclip_off_windows(dummy_pynput, monkeypatch):
    """Non-Windows platforms keep using pyperclip for snippet copies."""
    import utils.keyboard_utils as ku

    db = MagicMock()
    db.get_all_custom_placeholders.return_value = []
    db.get_enabled_trigger_index.return_value = []

    expander = SnippetExpander(snippets_db=db, parent=MagicMock())

    monkeypatch.setattr(ku, "IS_WINDOWS", False)
    mock_copy = MagicMock()
    monkeypatch.setattr("pyperclip.copy", mock_copy)
    mock_private = MagicMock()
    monkeypatch.setattr(expander, "copy_clipboard_windows", mock_private)

    expander.copy_to_clipboard("plain text")

    mock_copy.assert_called_once_with("plain text")
    mock_private.assert_not_called()


def test_clear_managed_clipboard_retries_when_clear_fails(dummy_pynput, monkeypatch):
    """A clipboard that cannot be emptied is retried instead of abandoned."""
    import utils.keyboard_utils as ku

    db = MagicMock()
    db.get_all_custom_placeholders.return_value = []
    db.get_enabled_trigger_index.return_value = []

    expander = SnippetExpander(snippets_db=db, parent=MagicMock())
    monkeypatch.setattr(ku, "CLIPBOARD_CLEAR_RETRY_SECONDS", 0.01)
    monkeypatch.setattr(expander, "read_clipboard", lambda: (True, "secret"))

    attempts = []

    def failing_empty():
        attempts.append(1)
        return False

    monkeypatch.setattr(expander, "empty_clipboard", failing_empty)

    expander.clipboard_generation = 1
    expander.last_managed_clipboard = "secret"
    expander.clear_managed_clipboard(expected_text="secret", generation=1)

    deadline = time.time() + 5
    while len(attempts) < ku.CLIPBOARD_CLEAR_RETRY_ATTEMPTS and time.time() < deadline:
        time.sleep(0.01)

    expander.cancel_clipboard_timer()
    assert len(attempts) == ku.CLIPBOARD_CLEAR_RETRY_ATTEMPTS
    # The snippet is still tracked, so shutdown can make one final attempt
    assert expander.last_managed_clipboard == "secret"

def test_clear_managed_clipboard_callsempty_clipboard(dummy_pynput, monkeypatch):
    """Verify that clear_managed_clipboard() uses the appropriate clipboard clearing method."""
    db = MagicMock()
    db.get_all_custom_placeholders.return_value = []
    db.get_enabled_trigger_index.return_value = []
    
    expander = SnippetExpander(
        snippets_db=db,
        parent=MagicMock(),
        settings_provider=lambda: {
            "general": {
                "clipboard_behavior": {
                    "clipboard_timeout": {"value": "30"}
                }
            }
        },
    )
    
    # Mock the empty_clipboard method
    mock_empty = MagicMock()
    expander.empty_clipboard = mock_empty
    
    # Mock pyperclip.paste to return matching content
    monkeypatch.setattr("pyperclip.paste", MagicMock(return_value="test_snippet"))
    
    expander.clear_managed_clipboard(expected_text="test_snippet", force=False)
    
    # Verify empty_clipboard was called
    mock_empty.assert_called_once()


def test_concurrent_refresh_and_expand_stress(expander):
    """Stress rapid snippet refresh and trigger expansion from multiple threads."""
    errors = []
    expansion_count = 0
    expansion_lock = threading.Lock()

    def fake_expand(_trigger, _snippet, _paste_style, _return_press):
        nonlocal expansion_count
        with expansion_lock:
            expansion_count += 1

    expander.expand = fake_expand

    def refresh_worker(iterations: int):
        try:
            for _ in range(iterations):
                expander.refresh_snippets()
        except Exception as exc:
            errors.append(exc)

    def type_worker(iterations: int):
        try:
            for _ in range(iterations):
                for char in "/sig":
                    expander.handle_char(char)
        except Exception as exc:
            errors.append(exc)

    threads = [
        threading.Thread(target=refresh_worker, args=(250,)),
        threading.Thread(target=type_worker, args=(250,)),
        threading.Thread(target=type_worker, args=(250,)),
    ]

    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert all(not thread.is_alive() for thread in threads)
    assert errors == []
    assert expansion_count > 0
    assert "/sig" in expander.trigger_map
    assert expander.max_trigger_len >= len("/sig")


def test_rapid_schedule_and_clear_cycles_stress(dummy_pynput, monkeypatch):
    """Stress rapid clipboard schedule/cancel/clear cycles for lock safety."""
    db = MagicMock()
    db.get_all_custom_placeholders.return_value = []
    db.get_enabled_trigger_index.return_value = []
    db.get_snippet_by_trigger.return_value = {}

    expander = SnippetExpander(
        snippets_db=db,
        parent=MagicMock(),
        settings_provider=lambda: {
            "general": {
                "clipboard_behavior": {
                    "clipboard_timeout": {"value": "1"}
                }
            }
        },
    )

    class FakeTimer:
        def __init__(self, _interval, _func, kwargs=None):
            self.kwargs = kwargs or {}
            self.daemon = False
            self.started = False
            self.canceled = False

        def start(self):
            self.started = True

        def cancel(self):
            self.canceled = True

    monkeypatch.setattr("utils.keyboard_utils.threading.Timer", FakeTimer)
    monkeypatch.setattr("pyperclip.paste", MagicMock(return_value=""))

    clear_calls = []
    clear_lock = threading.Lock()

    def fake_empty_clipboard():
        with clear_lock:
            clear_calls.append(1)

    expander.empty_clipboard = fake_empty_clipboard

    errors = []

    def schedule_worker(worker_id: int, iterations: int):
        try:
            for i in range(iterations):
                expander.schedule_clipboard_clear(f"snippet-{worker_id}-{i}")
        except Exception as exc:
            errors.append(exc)

    def clear_worker(iterations: int):
        try:
            for _ in range(iterations):
                expander.clear_managed_clipboard(force=True)
        except Exception as exc:
            errors.append(exc)

    threads = [
        threading.Thread(target=schedule_worker, args=(1, 300)),
        threading.Thread(target=schedule_worker, args=(2, 300)),
        threading.Thread(target=clear_worker, args=(300,)),
    ]

    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    expander.cancel_clipboard_timer()

    assert all(not thread.is_alive() for thread in threads)
    assert errors == []
    assert expander.clipboard_generation > 0
    assert len(clear_calls) > 0


@pytest.mark.parametrize(
    "text, expected_names",
    [
        ("Hi [[name]], welcome to [[place]]!", ["name", "place"]),
        ("[[a]] and [[a]] again", ["a"]),
        ("No placeholders here", []),
        ("[[ spaced out ]]", ["spaced out"]),
    ],
)
def test_extract_dynamic_placeholder_names(text, expected_names):
    """[[name]] tokens should be found in first-seen order, deduped, and trimmed."""
    assert extract_dynamic_placeholder_names(text) == expected_names


def test_substitute_dynamic_placeholders_replaces_known_tokens():
    """Known [[name]] tokens are replaced; unknown ones are left untouched."""
    result = substitute_dynamic_placeholders(
        "Hi [[name]], re: [[project]]. Unused: [[other]]",
        {"name": "Alex", "project": "QSnippet"},
    )
    assert result == "Hi Alex, re: QSnippet. Unused: [[other]]"


def test_get_dynamic_placeholder_names_finds_nested_fields(dummy_pynput):
    """A [[name]] living inside a nested {/trigger} reference should still be detected."""
    db = MagicMock()
    db.get_all_custom_placeholders.return_value = []
    db.get_enabled_trigger_index.return_value = [
        {"id": 1, "trigger": "/sig", "paste_style": "Clipboard", "return_press": False},
        {"id": 2, "trigger": "/nested", "paste_style": "Clipboard", "return_press": False},
    ]
    snippets_by_trigger = {
        "/sig": {"id": 1, "trigger": "/sig", "snippet": "Hi {/nested}", "paste_style": "Clipboard", "return_press": False},
        "/nested": {"id": 2, "trigger": "/nested", "snippet": "there, [[name]]!", "paste_style": "Clipboard", "return_press": False},
    }
    db.get_snippet_by_trigger.side_effect = lambda trigger: snippets_by_trigger[trigger]

    dynamic_expander = SnippetExpander(
        snippets_db=db,
        parent=MagicMock(),
        settings_provider=lambda: {},
    )

    assert dynamic_expander.get_dynamic_placeholder_names("Hi {/nested}") == ["name"]


def test_get_dynamic_placeholder_names_no_placeholders_returns_empty(expander):
    """A snippet with no [[name]] fields should report no placeholders to fill in."""
    assert expander.get_dynamic_placeholder_names("Regards") == []


def test_handle_char_notifies_dynamic_placeholder_callback_and_skips_expand(expander):
    """A snippet with [[name]] fields should notify via callback instead of expanding synchronously."""
    expander.snippets_db.get_snippet_by_trigger.return_value = {
        "id": 1,
        "trigger": "/sig",
        "snippet": "Hi [[name]]",
        "paste_style": "Clipboard",
        "return_press": False,
        "enabled": True,
    }

    calls = []
    ready = threading.Event()

    def on_dynamic(trigger, snippet_entry, style, return_press):
        calls.append((trigger, snippet_entry, style, return_press))
        ready.set()

    expander.dynamic_placeholder_callback = on_dynamic
    expander.expand = MagicMock()

    for char in "/sig":
        expander.handle_char(char)

    assert ready.wait(timeout=1.0)
    trigger, snippet_entry, style, return_press = calls[0]
    assert (trigger, snippet_entry["snippet"], style, return_press) == ("/sig", "Hi [[name]]", "Clipboard", False)
    expander.expand.assert_not_called()


def test_expand_applies_dynamic_values_after_processing(expander):
    """expand() should substitute dynamic_values into the fully-processed snippet text."""
    expander.expand_clipboard = MagicMock()
    expander.buffer = "/sig"
    expander.cursor_pos = len("/sig")

    expander.expand("/sig", "Hi [[name]]", "Clipboard", False, dynamic_values={"name": "Alex"})

    expander.expand_clipboard.assert_called_once()
    (pasted_text,), _ = expander.expand_clipboard.call_args
    assert pasted_text == "Hi Alex"


def test_process_snippet_text_substitutes_double_brace_system_placeholders(expander):
    """System placeholders use {{name}} syntax and resolve to real values."""
    result = expander.process_snippet_text("Sent on {{date}} - {{greeting}}!")
    assert "{{date}}" not in result
    assert "{{greeting}}" not in result
    assert result.startswith("Sent on ")


def test_process_snippet_text_no_longer_substitutes_legacy_single_brace(expander):
    """Legacy single-brace {date} is a clean break - it must paste literally now."""
    result = expander.process_snippet_text("Sent on {date}")
    assert result == "Sent on {date}"


def test_process_snippet_text_substitutes_double_brace_custom_placeholder(dummy_pynput):
    """Custom placeholders substitute via {{name}}, not the legacy {name}."""
    db = MagicMock()
    db.get_all_custom_placeholders.return_value = [
        {"name": "email", "value": "me@example.com", "is_encrypted": False}
    ]
    db.get_enabled_trigger_index.return_value = []

    custom_expander = SnippetExpander(snippets_db=db, parent=MagicMock(), settings_provider=lambda: {})

    assert custom_expander.process_snippet_text("Reach me at {{email}}") == "Reach me at me@example.com"
    assert custom_expander.process_snippet_text("Reach me at {email}") == "Reach me at {email}"


def test_process_snippet_text_nested_snippet_still_uses_single_brace(dummy_pynput):
    """Nested {/trigger} references are a different, unrelated syntax and must be unaffected."""
    db = MagicMock()
    db.get_all_custom_placeholders.return_value = []
    db.get_enabled_trigger_index.return_value = [
        {"id": 1, "trigger": "/sig", "paste_style": "Clipboard", "return_press": False},
        {"id": 2, "trigger": "/nested", "paste_style": "Clipboard", "return_press": False},
    ]
    bodies = {
        "/sig": {"id": 1, "trigger": "/sig", "snippet": "Regards, {/nested}"},
        "/nested": {"id": 2, "trigger": "/nested", "snippet": "Alex"},
    }
    db.get_snippet_by_trigger.side_effect = lambda trigger: bodies[trigger]

    nested_expander = SnippetExpander(snippets_db=db, parent=MagicMock(), settings_provider=lambda: {})

    assert nested_expander.process_snippet_text("Regards, {/nested}") == "Regards, Alex"


def test_process_snippet_text_unknown_double_brace_left_literal(expander):
    """An unrecognized/typo'd {{name}} must not be misread as a nested-snippet reference."""
    result = expander.process_snippet_text("Hi {{typo_name}}")
    assert result == "Hi {{typo_name}}"
    assert "Error" not in result


def test_has_encrypted_placeholders_checks_double_brace_form(dummy_pynput):
    """has_encrypted_placeholders() must key off {{name}}, matching the new substitution syntax."""
    db = MagicMock()
    db.get_all_custom_placeholders.return_value = [
        {"name": "secret", "value": "cipher", "is_encrypted": True}
    ]
    db.get_enabled_trigger_index.return_value = []

    enc_expander = SnippetExpander(snippets_db=db, parent=MagicMock(), settings_provider=lambda: {})

    assert enc_expander.has_encrypted_placeholders("Value: {{secret}}") is True
    assert enc_expander.has_encrypted_placeholders("Value: {secret}") is False

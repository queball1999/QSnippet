import sys
import threading
import types
from contextlib import nullcontext
from unittest.mock import MagicMock

import pytest

from utils.keyboard_utils import SnippetExpander


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

    monkeypatch.setattr("utils.keyboard_utils.win32clipboard.OpenClipboard", mock_open)
    monkeypatch.setattr("utils.keyboard_utils.win32clipboard.CloseClipboard", mock_close)

    expander.empty_clipboard_windows()

    # Fallback to pyperclip occurred
    mock_copy.assert_called_once_with("")
    # OpenClipboard failed, so CloseClipboard should not be called
    mock_close.assert_not_called()

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

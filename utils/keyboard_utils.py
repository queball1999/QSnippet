import logging
import os
import platform
import pyperclip
import re
import datetime
import struct
import threading
import time
from functools import lru_cache

from utils.snippet_db import SnippetDB

IS_WINDOWS = platform.system() == "Windows"

# Windows clipboard API via pywin32
if IS_WINDOWS:
    import win32clipboard

logger = logging.getLogger(__name__)

DEFAULT_TRIGGER_TIMEOUT_SECONDS = 5.0

IS_MACOS = platform.system() == "Darwin"
IS_LINUX = platform.system() == "Linux"

# macOS. Clipboard managers following the NSPasteboard convention skip any
# pasteboard item that also carries this type. The value is irrelevant; the
# presence of the type is the signal.
MACOS_CONCEALED_PASTEBOARD_TYPE = "org.nspasteboard.ConcealedType"
MACOS_STRING_PASTEBOARD_TYPE = "public.utf8-plain-text"

# Linux. KDE Klipper, and the clipboard managers that follow it, skip a
# clipboard offer that also advertises this MIME type.
LINUX_PASSWORD_HINT_MIME = "x-kde-passwordManagerHint"
LINUX_PASSWORD_HINT_VALUE = b"secret"

# How long a worker thread waits for the Qt GUI thread to finish a clipboard
# write before giving up and falling back to pyperclip.
QT_CLIPBOARD_TIMEOUT_SECONDS = 2.0

# Cache for backend probes that cannot change during a run (an absent import
# stays absent). Probes that can change, such as whether a QApplication exists
# yet, are re-checked on every copy.
clipboard_backend_probe: dict[str, object] = {}


def load_macos_pasteboard_api():
    """
    Resolve the AppKit NSPasteboard API used for concealed pasteboard writes.

    pyobjc is optional. When it is missing the caller falls back to pyperclip,
    which still copies correctly but cannot mark the entry as concealed.

    Returns:
        tuple | None: (NSPasteboard class, string type) or None when unavailable.
    """
    if "macos" in clipboard_backend_probe:
        return clipboard_backend_probe["macos"]

    api = None
    if IS_MACOS:
        try:
            from AppKit import NSPasteboard

            try:
                from AppKit import NSPasteboardTypeString as string_type
            except Exception:
                string_type = MACOS_STRING_PASTEBOARD_TYPE
            api = (NSPasteboard, string_type)
        except Exception as e:
            logger.info(
                "AppKit/pyobjc unavailable (%s); macOS clipboard falls back to pyperclip", e
            )
    clipboard_backend_probe["macos"] = api
    return api


def get_linux_session_type() -> str:
    """
    Detect the graphical session type on Linux.

    Returns:
        str: "wayland", "x11", or "none" when no graphical session is present.
    """
    session = (os.environ.get("XDG_SESSION_TYPE") or "").strip().lower()
    if session in ("wayland", "x11"):
        return session
    if os.environ.get("WAYLAND_DISPLAY"):
        return "wayland"
    if os.environ.get("DISPLAY"):
        return "x11"
    return "none"


def load_qt_clipboard_api():
    """
    Resolve the Qt classes needed for a MIME-aware clipboard write.

    The QApplication instance is looked up fresh each call because it may not
    exist yet the first time a snippet is expanded.

    Returns:
        tuple | None: (app, QMimeData, QTimer) or None when Qt is unusable.
    """
    try:
        from PySide6.QtCore import QMimeData, QTimer
        from PySide6.QtWidgets import QApplication
    except Exception as e:
        logger.info("PySide6 clipboard API unavailable (%s)", e)
        return None

    app = QApplication.instance()
    if app is None:
        logger.info("No running QApplication; clipboard falls back to pyperclip")
        return None
    return app, QMimeData, QTimer


# Windows only. Another process can hold the clipboard open for short periods,
# which makes OpenClipboard fail with ERROR_ACCESS_DENIED. Retry briefly.
CLIPBOARD_OPEN_ATTEMPTS = 12
CLIPBOARD_OPEN_RETRY_SECONDS = 0.05

# When a scheduled clear cannot reach the clipboard, re-arm rather than giving
# up, otherwise the snippet stays on the clipboard indefinitely.
CLIPBOARD_CLEAR_RETRY_ATTEMPTS = 6
CLIPBOARD_CLEAR_RETRY_SECONDS = 1.0

# Windows shell clipboard formats that opt a clipboard entry out of clipboard
# history (Win+V) and Cloud Clipboard sync. They only take effect when set in
# the same OpenClipboard session that sets the text, so snippets have to be
# copied through win32clipboard rather than pyperclip on Windows.
WINDOWS_PRIVATE_CLIPBOARD_FORMATS = (
    "ExcludeClipboardContentFromMonitorProcessing",
    "CanIncludeInClipboardHistory",
    "CanUploadToCloudClipboard",
)

windows_clipboard_format_ids: dict[str, int | None] = {}


def get_windows_clipboard_format_id(name: str) -> int | None:
    """
    Resolve and cache a registered Windows clipboard format id.

    Args:
        name (str): The clipboard format name to register.

    Returns:
        int | None: The format id, or None when registration failed.
    """
    if name in windows_clipboard_format_ids:
        return windows_clipboard_format_ids[name]
    try:
        format_id = win32clipboard.RegisterClipboardFormat(name)
    except Exception:
        logger.exception("Failed to register clipboard format %s", name)
        format_id = None
    windows_clipboard_format_ids[name] = format_id
    return format_id


def open_clipboard_windows() -> bool:
    """
    Open the Windows clipboard, retrying while another process holds it.

    Returns:
        bool: True when the clipboard was opened and must be closed by the caller.
    """
    last_error = None
    for attempt in range(CLIPBOARD_OPEN_ATTEMPTS):
        try:
            win32clipboard.OpenClipboard()
            return True
        except Exception as e:
            last_error = e
            if attempt < CLIPBOARD_OPEN_ATTEMPTS - 1:
                time.sleep(CLIPBOARD_OPEN_RETRY_SECONDS)
    logger.warning(
        "Could not open the Windows clipboard after %s attempts: %s",
        CLIPBOARD_OPEN_ATTEMPTS,
        last_error,
    )
    return False


def close_clipboard_windows() -> None:
    """
    Close the Windows clipboard handle, logging but swallowing failures.

    Returns:
        None
    """
    try:
        win32clipboard.CloseClipboard()
    except Exception:
        logger.exception("Failed to close Windows clipboard handle")

_DURATION_PATTERN = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(ms|s)?\s*$")


def parse_duration_seconds(raw_value, default_seconds: float) -> float | None:
    """
    Parse a duration setting into seconds.

    Accepts a bare number (seconds), a number suffixed with "ms" or "s",
    or "off" to disable the timeout entirely.

    Args:
        raw_value (Any): The raw setting value (e.g. "500ms", "5s", "off").
        default_seconds (float): Value to fall back to when parsing fails.

    Returns:
        float | None: The duration in seconds, or None when disabled.
    """
    if raw_value is None:
        return default_seconds

    text = str(raw_value).strip().lower()
    if text in ("off", "disabled", "none"):
        return None

    match = _DURATION_PATTERN.match(text)
    if not match:
        logger.warning("Invalid duration %r. Falling back to %.3fs", raw_value, default_seconds)
        return default_seconds

    amount = float(match.group(1))
    unit = match.group(2) or "s"
    seconds = amount / 1000.0 if unit == "ms" else amount

    return seconds if seconds > 0 else None


def format_duration_seconds(seconds) -> str:
    """
    Format a duration in seconds for display (e.g. "500ms", "5s", "Off").

    Args:
        seconds (float | None): The duration in seconds, or None when disabled.

    Returns:
        str: The human-readable duration.
    """
    if seconds is None:
        return "Off"
    if seconds < 1:
        return f"{round(seconds * 1000)}ms"
    if float(seconds).is_integer():
        return f"{int(seconds)}s"
    return f"{seconds:g}s"


_DYNAMIC_PLACEHOLDER_PATTERN = re.compile(r"\[\[([^\[\]\r\n]+?)\]\]")


def extract_dynamic_placeholder_names(text: str) -> list[str]:
    """
    Find [[name]] dynamic placeholder tokens in text.

    Args:
        text (str): The text to scan.

    Returns:
        list[str]: Unique placeholder names, in first-seen order.
    """
    seen = set()
    names = []
    for match in _DYNAMIC_PLACEHOLDER_PATTERN.finditer(text):
        name = match.group(1).strip()
        if name and name not in seen:
            seen.add(name)
            names.append(name)
    return names


# Sentinel marking where an empty placeholder used to be, so the surrounding
# whitespace can be tidied without disturbing whitespace elsewhere in the text.
EMPTY_PLACEHOLDER_MARK = "\uE000"


def collapse_empty_placeholder_gaps(text: str) -> str:
    """
    Tidy the whitespace left behind by placeholders the user submitted empty.

    Each removed token is marked with EMPTY_PLACEHOLDER_MARK first, so only the
    gap it created is touched. Rules, applied in order:

      1. A line containing nothing but the token disappears entirely, rather
         than being left as a blank line.
      2. "a [[x]] b"     -> "a b"        (one separating space survives)
      3. "Hello [[x]], hi" -> "Hello, hi"  (no space stranded before punctuation)
      4. "[[x]] start"   -> "start"      (no leading space)

    Args:
        text (str): Text whose empty tokens have been replaced by the sentinel.

    Returns:
        str: The text with the sentinel removed and its gap collapsed.
    """
    mark = re.escape(EMPTY_PLACEHOLDER_MARK)

    # 1. Token was the entire line - drop the line, including its newline.
    text = re.sub(rf"^[ \t]*{mark}[ \t]*\r?\n", "", text, flags=re.MULTILINE)
    # ...and the same case on a final line with no trailing newline.
    text = re.sub(rf"\r?\n[ \t]*{mark}[ \t]*$", "", text)

    # 2. Whitespace on both sides - keep exactly one space.
    text = re.sub(rf"[ \t]+{mark}[ \t]+", " ", text)

    # 3. Whitespace only before the token (end of line, or punctuation after).
    text = re.sub(rf"[ \t]+{mark}", "", text)

    # 4. Whitespace only after the token (start of line).
    text = re.sub(rf"{mark}[ \t]+", "", text)

    # 5. Anything left (token flush against text on both sides).
    return text.replace(EMPTY_PLACEHOLDER_MARK, "")


def substitute_dynamic_placeholders(text: str, values: dict,
                                    collapse_empty: bool = True) -> str:
    """
    Replace [[name]] tokens in text with user-supplied values.

    Args:
        text (str): The text containing [[name]] tokens.
        values (dict): Mapping of placeholder name to its replacement value.
        collapse_empty (bool): When True, a token whose value is empty is
            removed along with the whitespace it would otherwise strand (a
            doubled space, a space before a comma, or a now-blank line).
            Pass False to substitute the empty string literally.

    Returns:
        str: The text with all known [[name]] tokens substituted.
    """
    had_empty = False
    for name, value in values.items():
        token = f"[[{name}]]"
        if not value and collapse_empty:
            if token in text:
                had_empty = True
                text = text.replace(token, EMPTY_PLACEHOLDER_MARK)
        else:
            text = text.replace(token, value)

    if had_empty:
        text = collapse_empty_placeholder_gaps(text)
    return text


class SnippetExpander:
    def __init__(self, snippets_db: SnippetDB, parent, settings_provider=None) -> None:
        """
        Initialize the SnippetExpander.

        Loads lightweight trigger metadata from the database, prepares
        trigger handling, initializes keyboard listener and controller,
        and configures internal state for buffer and clipboard tracking.

        Args:
            snippets_db (SnippetDB): The snippet database instance.
            parent (Any): The parent object.
            settings_provider (Callable | None): Optional callback that
            returns the latest settings dictionary.

        Returns:
            None
        """
        from pynput import keyboard
        self.keyboard = keyboard

        logger.info("Initializing SnippetExpander")

        self.snippets_db = snippets_db
        self.custom_placeholders = self.snippets_db.get_all_custom_placeholders()
        self.parent = parent
        self.settings_provider = settings_provider or getattr(parent, "settings_provider", None)

        self.disabled = False
        self.keys_to_ignore = [self.keyboard.Key.space, self.keyboard.Key.shift, self.keyboard.Key.enter, self.keyboard.Key.ctrl_l, self.keyboard.Key.ctrl_r]
        self.buffer = ""
        self.cursor_pos = 0
        self.max_trigger_len = 1
        self.trigger_flag = False
        self.last_keypress_at = 0.0
        self.last_event_processed_at = 0.0
        self.keyboard_debounce_ms = 20  # Minimum milliseconds between event processing
        self.buffer_lock = threading.RLock()
        self.clipboard_lock = threading.RLock()
        self.clipboard_timer = None
        self.clipboard_generation = 0
        self.last_managed_clipboard = None
        self.trigger_map = {}
        self.trigger_trie = {}
        self.trigger_prefixes: set = set()  # first character of every enabled trigger
        self.vault_unlock_callback = None  # Callable[[trigger, entry, style, return_press], None]
        self.trigger_detected_callback = None  # Callable[[prefix_char, timeout_seconds], None]
        self.clipboard_cleared_callback = None  # Callable[[], None]
        self.dynamic_placeholder_callback = None  # Callable[[trigger, entry, style, return_press], None]
        self.vault_folder_set: set = set()  # paths of vault-protected folders

        self.refresh_snippets()

        self.listener = self.keyboard.Listener(on_press=self.on_key_press)
        self.controller = self.keyboard.Controller()
        self.paste_mod = self.keyboard.Key.cmd if platform.system() == "Darwin" else self.keyboard.Key.ctrl

        logger.info("SnippetExpander initialized successfully")

    def build_trigger_map(self) -> None:
        """
        Build the trigger lookup map and reversed trie.

        Creates a lightweight dictionary of enabled snippet triggers mapped
        to their metadata and builds a reversed trie used for suffix matching.
        
        Returns:
            None
        """
        logger.info("Building trigger map")

        trigger_index = self.snippets_db.get_enabled_trigger_index() or []
        self.trigger_map = {
            row["trigger"]: row
            for row in trigger_index
            if row.get("trigger")
        }
        self.trigger_trie = {}

        for trigger in self.trigger_map:
            node = self.trigger_trie
            for char in reversed(trigger):
                node = node.setdefault(char, {})
            node["__trigger__"] = trigger

        self.max_trigger_len = max((len(trigger) for trigger in self.trigger_map), default=1)
        self.trigger_prefixes = {trigger[0] for trigger in self.trigger_map if trigger}

        logger.debug("Trigger map size: %d", len(self.trigger_map))
        logger.debug("Maximum trigger length: %d", self.max_trigger_len)

    def refresh_snippets(self) -> None:
        """
        Reload snippets and custom placeholders from the database.

        Refreshes trigger metadata, the suffix trie, and cached custom
        placeholders to reflect database updates.
        
        Returns:
            None
        """
        logger.info("Refreshing snippets from database")

        self.custom_placeholders = self.snippets_db.get_all_custom_placeholders()
        self.load_snippet_by_trigger.cache_clear()
        self.build_trigger_map()
        self.clear_buffer()
        logger.info("SnippetExpander reloaded snippets from DB")

    def has_encrypted_placeholders(self, text: str) -> bool:
        """Check if snippet text contains any vault-encrypted placeholders."""
        return any(
            ph.get("is_encrypted") and f"{{{{{ph['name']}}}}}" in text
            for ph in self.custom_placeholders
        )

    # Incremental trigger-map updates   update or remove a
    # single trigger in memory without a DB round-trip or
    # keyboard buffer clear.

    def rebuild_trie_from_map(self) -> None:
        """
        Rebuild the reversed suffix trie from the current trigger_map.

        Faster than a full build_trigger_map() because it skips the DB
        query and works entirely in memory.
        
        Returns:
            None
        """
        trie: dict = {}
        for trigger in self.trigger_map:
            node = trie
            for char in reversed(trigger):
                node = node.setdefault(char, {})
            node["__trigger__"] = trigger
        self.trigger_trie = trie
        self.max_trigger_len = max((len(t) for t in self.trigger_map), default=1)
        self.trigger_prefixes = {t[0] for t in self.trigger_map if t}

    def update_trigger_entry(self, snippet_meta: dict) -> None:
        """
        Add or update a single trigger in the in-memory index without a DB
        query or buffer clear.

        Intended for single-snippet save/update operations from the UI so
        that ongoing typing is not disrupted.

        Args:
            snippet_meta (dict): Must contain at minimum 'trigger' and 'id'.
                Optional keys: 'enabled' (default True), 'paste_style',
                'return_press'.
        
        Returns:
            None
        """
        trigger = snippet_meta.get("trigger")
        snippet_id = snippet_meta.get("id")
        if not trigger:
            logger.warning("update_trigger_entry called with no trigger; falling back to full refresh")
            self.refresh_snippets()
            return

        with self.buffer_lock:
            # Remove any existing entry for this snippet ID (handles renames)
            old_trigger = next(
                (t for t, m in self.trigger_map.items() if m.get("id") == snippet_id),
                None,
            )
            if old_trigger and old_trigger != trigger:
                self.trigger_map.pop(old_trigger, None)

            enabled = snippet_meta.get("enabled", True)
            if enabled:
                self.trigger_map[trigger] = {
                    "id": snippet_id,
                    "trigger": trigger,
                    "paste_style": snippet_meta.get("paste_style", "Keystroke"),
                    "return_press": bool(snippet_meta.get("return_press", False)),
                }
            else:
                # Disabled snippets must not appear in the trie
                self.trigger_map.pop(trigger, None)

            self.rebuild_trie_from_map()

        # Invalidate only the affected trigger in the LRU cache
        self.load_snippet_by_trigger.cache_clear()
        logger.debug("Incremental trigger update: %s (id=%s)", trigger, snippet_id)

    def remove_trigger_entry(self, snippet_id: int) -> None:
        """
        Remove a trigger from the in-memory index by snippet ID without a
        DB query or buffer clear.

        Args:
            snippet_id (int): The database ID of the deleted snippet.
        
        Returns:
            None
        """
        with self.buffer_lock:
            trigger = next(
                (t for t, m in self.trigger_map.items() if m.get("id") == snippet_id),
                None,
            )
            if trigger is None:
                logger.debug("remove_trigger_entry: snippet id=%s not in trigger map", snippet_id)
                return
            self.trigger_map.pop(trigger)
            self.rebuild_trie_from_map()

        self.load_snippet_by_trigger.cache_clear()
        logger.debug("Incremental trigger removal: %s (id=%s)", trigger, snippet_id)

    def set_vault_folders(self, vault_folder_paths: list) -> None:
        """Update the set of vault-protected folder paths used for trigger intercept."""
        self.vault_folder_set = set(vault_folder_paths)

    def retrieve_trigger_chars(self, snippets) -> list:
        """
        Retrieve unique first characters from enabled snippet triggers.

        Args:
            snippets (list[dict]): List of snippet dictionaries.
        
        Returns:
            list: A list of unique trigger prefix characters.
        """
        logger.debug("Retrieving trigger prefix characters")

        trigger_prefixs = []
        for snippet in snippets:
            prefix = snippet["trigger"][0]
            if snippet.get("enabled", True) and prefix not in trigger_prefixs:
                trigger_prefixs.append(prefix)

        logger.debug("Trigger prefixes: %s", trigger_prefixs)
        return trigger_prefixs

    def get_settings(self) -> dict:
        """
        Return the latest settings dictionary.
        
        Returns:
            dict: The current settings dictionary, or an empty dict.
        """
        if callable(self.settings_provider):
            try:
                return self.settings_provider() or {}
            except Exception:
                logger.exception("Failed to resolve settings for SnippetExpander")
                return {}

        settings = getattr(self.parent, "settings", None)
        return settings or {}

    def get_trigger_timeout_seconds(self) -> float | None:
        """
        Read the trigger buffer inactivity timeout from settings.

        Returns:
            float | None: The timeout in seconds, or None when disabled.
        """
        settings = self.get_settings()
        raw_value = (
            settings.get("general", {})
            .get("keyboard_behavior", {})
            .get("trigger_timeout", {})
            .get("value", DEFAULT_TRIGGER_TIMEOUT_SECONDS)
        )
        return parse_duration_seconds(raw_value, default_seconds=DEFAULT_TRIGGER_TIMEOUT_SECONDS)

    def get_clipboard_timeout_seconds(self) -> int | None:
        """
        Read the clipboard cleanup timeout from settings.
        
        Returns:
            int | None: The timeout in seconds, or None when disabled.
        """
        settings = self.get_settings()
        raw_value = (
            settings.get("general", {})
            .get("clipboard_behavior", {})
            .get("clipboard_timeout", {})
            .get("value", "30")
        )

        if isinstance(raw_value, str) and raw_value.strip().lower() == "off":
            return None

        try:
            timeout_seconds = int(raw_value)
        except (TypeError, ValueError):
            logger.warning("Invalid clipboard timeout %r. Falling back to 30 seconds.", raw_value)
            return 30

        return timeout_seconds if timeout_seconds > 0 else 30

    def get_dynamic_placeholder_dialog_mode(self) -> str:
        """
        Read how [[placeholder]] input prompts should be shown from settings.

        Returns:
            str: "single_form" or "sequential".
        """
        settings = self.get_settings()
        return (
            settings.get("general", {})
            .get("dynamic_placeholders", {})
            .get("dialog_mode", {})
            .get("value", "single_form")
        )

    def cancel_clipboard_timer(self) -> None:
        """
        Cancel any pending clipboard cleanup timer.
        
        Returns:
            None
        """
        with self.clipboard_lock:
            if self.clipboard_timer is not None:
                self.clipboard_timer.cancel()
                self.clipboard_timer = None

    def copy_clipboard_windows(self, text: str) -> bool:
        """
        Copy text on Windows while opting out of clipboard history and cloud sync.

        The exclusion markers only apply to the clipboard entry created in the
        same OpenClipboard session, so the text and the markers are written
        together here instead of going through pyperclip.

        Args:
            text (str): The text to place on the clipboard.

        Returns:
            bool: True when the private copy succeeded.
        """
        if not open_clipboard_windows():
            return False
        try:
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardData(win32clipboard.CF_UNICODETEXT, text)
            for name in WINDOWS_PRIVATE_CLIPBOARD_FORMATS:
                format_id = get_windows_clipboard_format_id(name)
                if format_id is None:
                    continue
                try:
                    win32clipboard.SetClipboardData(format_id, struct.pack("<I", 0))
                except Exception:
                    # A missing marker degrades privacy but must not break the paste.
                    logger.warning("Could not apply clipboard format %s", name)
            logger.debug("Snippet copied with clipboard history exclusion markers")
            return True
        except Exception:
            logger.exception("Private Windows clipboard copy failed")
            return False
        finally:
            close_clipboard_windows()

    def copy_clipboard_macos(self, text: str) -> bool:
        """
        Copy text on macOS while marking the pasteboard item as concealed.

        Clipboard managers that honor the NSPasteboard convention skip items
        carrying org.nspasteboard.ConcealedType. Requires pyobjc; without it
        the caller falls back to pyperclip.

        Args:
            text (str): The text to place on the clipboard.

        Returns:
            bool: True when the concealed copy succeeded and read back intact.
        """
        api = load_macos_pasteboard_api()
        if api is None:
            return False

        pasteboard_cls, string_type = api
        pasteboard = pasteboard_cls.generalPasteboard()
        if pasteboard is None:
            logger.warning("No general pasteboard available")
            return False

        pasteboard.declareTypes_owner_([string_type, MACOS_CONCEALED_PASTEBOARD_TYPE], None)
        if not pasteboard.setString_forType_(text, string_type):
            logger.warning("Pasteboard rejected the snippet text")
            return False
        if not pasteboard.setString_forType_("", MACOS_CONCEALED_PASTEBOARD_TYPE):
            # A missing marker degrades privacy but must not break the paste.
            logger.warning("Could not mark the pasteboard item as concealed")

        if pasteboard.stringForType_(string_type) != text:
            logger.warning("Pasteboard read-back mismatch; falling back")
            return False
        logger.debug("Snippet copied to the macOS pasteboard as a concealed item")
        return True

    def copy_clipboard_linux(self, text: str) -> bool:
        """
        Copy text on Linux while advertising the password-manager MIME hint.

        Qt is used rather than pyperclip because the hint has to be offered on
        the same clipboard offer as the text, which the xclip/xsel helpers
        pyperclip shells out to cannot do. The write is marshalled onto the GUI
        thread, since QClipboard may only be touched there.

        Args:
            text (str): The text to place on the clipboard.

        Returns:
            bool: True when the hinted copy succeeded.
        """
        session = get_linux_session_type()
        if session == "none":
            logger.info("No graphical session detected; clipboard falls back to pyperclip")
            return False

        api = load_qt_clipboard_api()
        if api is None:
            return False
        app, mime_cls, timer_cls = api

        done = threading.Event()
        outcome = {"ok": False}

        def write_clipboard() -> None:
            try:
                mime = mime_cls()
                mime.setText(text)
                mime.setData(LINUX_PASSWORD_HINT_MIME, LINUX_PASSWORD_HINT_VALUE)
                app.clipboard().setMimeData(mime)
                outcome["ok"] = True
            except Exception:
                logger.exception("Qt clipboard write failed")
            finally:
                done.set()

        if threading.current_thread() is threading.main_thread():
            write_clipboard()
        else:
            # Passing app as the context object runs the callable on the GUI thread.
            timer_cls.singleShot(0, app, write_clipboard)
            if not done.wait(QT_CLIPBOARD_TIMEOUT_SECONDS):
                logger.warning("Qt clipboard write timed out after %ss", QT_CLIPBOARD_TIMEOUT_SECONDS)
                return False

        if outcome["ok"]:
            logger.debug("Snippet copied with the %s hint (%s session)", LINUX_PASSWORD_HINT_MIME, session)
        return outcome["ok"]

    def get_private_copy_handler(self):
        """
        Pick the platform handler that copies without leaking to clipboard history.

        Returns:
            tuple | None: (description, callable) or None when the platform has no
            private copy path and pyperclip should be used directly.
        """
        if IS_WINDOWS:
            return "Windows clipboard history exclusion", self.copy_clipboard_windows
        if IS_MACOS:
            return "macOS concealed pasteboard", self.copy_clipboard_macos
        if IS_LINUX:
            return "Linux password-manager clipboard hint", self.copy_clipboard_linux
        logger.debug("Unrecognized platform %r; using pyperclip", platform.system())
        return None

    def copy_to_clipboard(self, text: str) -> None:
        """
        Copy snippet text to the clipboard using the best method for the platform.

        Each platform gets a copy path that asks the OS and any clipboard manager
        not to retain the entry: clipboard history and Cloud Clipboard exclusion on
        Windows, a concealed pasteboard item on macOS, and the password-manager MIME
        hint on Linux. If the platform is not recognized, its API is unavailable, or
        the write fails for any reason, the copy falls back to pyperclip so the
        snippet still pastes.

        Args:
            text (str): The text to place on the clipboard.

        Returns:
            None
        """
        handler = self.get_private_copy_handler()
        if handler is not None:
            label, copy_privately = handler
            try:
                if copy_privately(text):
                    return
            except Exception:
                logger.exception("%s failed", label)
            logger.warning("%s unavailable; falling back to pyperclip", label)
        pyperclip.copy(text)

    def empty_clipboard_windows(self) -> bool:
        """
        Empty clipboard on Windows using pywin32.

        Uses win32clipboard API and always closes the clipboard handle
        to avoid locking it for other applications.

        Returns:
            bool: True when the clipboard was emptied.
        """
        if open_clipboard_windows():
            try:
                win32clipboard.EmptyClipboard()
                logger.debug("Active clipboard cleared via win32clipboard.EmptyClipboard()")
                return True
            except Exception as e:
                logger.warning("win32clipboard clear failed: %s; falling back to pyperclip", e)
            finally:
                close_clipboard_windows()

        try:
            pyperclip.copy("")
            return True
        except Exception:
            logger.exception("pyperclip fallback also failed")
            return False

    def empty_clipboard_generic(self) -> bool:
        """
        Empty clipboard using cross-platform method.

        Returns:
            bool: True when the clipboard was emptied.
        """
        try:
            pyperclip.copy("")
            logger.debug("Clipboard cleared")
            return True
        except Exception:
            logger.exception("Failed to clear clipboard")
            return False

    def empty_clipboard_macos(self) -> bool:
        """
        Empty the macOS pasteboard via AppKit, dropping the concealed item.

        Returns:
            bool: True when the pasteboard was cleared.
        """
        api = load_macos_pasteboard_api()
        if api is None:
            return False
        pasteboard_cls, _string_type = api
        try:
            pasteboard = pasteboard_cls.generalPasteboard()
            if pasteboard is None:
                return False
            pasteboard.clearContents()
            logger.debug("Pasteboard cleared via NSPasteboard.clearContents()")
            return True
        except Exception:
            logger.exception("NSPasteboard clear failed")
            return False

    def empty_clipboard(self) -> bool:
        """
        Empty the clipboard using the most appropriate method for the platform.

        Every platform-specific path falls through to the pyperclip clear when it
        is unavailable or fails, so an unrecognized platform still gets cleaned up.

        Returns:
            bool: True when the clipboard was emptied.
        """
        if IS_WINDOWS:
            return self.empty_clipboard_windows()
        if IS_MACOS and self.empty_clipboard_macos():
            return True
        return self.empty_clipboard_generic()

    def read_clipboard(self) -> tuple[bool, str]:
        """
        Read the current clipboard text without raising.

        Returns:
            tuple[bool, str]: Whether the read succeeded, and the text read.
        """
        try:
            return True, pyperclip.paste()
        except Exception as e:
            logger.warning("Could not read the clipboard: %s", e)
            return False, ""

    def schedule_clipboard_clear(self, expected_text: str) -> None:
        """
        Schedule clipboard cleanup for a managed clipboard expansion.

        Args:
            expected_text (str): The clipboard content to clear if unchanged.

        Returns:
            None
        """
        timeout_seconds = self.get_clipboard_timeout_seconds()
        self.cancel_clipboard_timer()

        with self.clipboard_lock:
            self.clipboard_generation += 1
            self.last_managed_clipboard = expected_text
            generation = self.clipboard_generation

            if timeout_seconds is None:
                logger.info("Clipboard cleanup disabled by settings")
                return

            self.arm_clipboard_timer(
                delay_seconds=timeout_seconds,
                expected_text=expected_text,
                generation=generation,
                attempt=0,
            )
            logger.debug("Scheduled clipboard cleanup in %s seconds", timeout_seconds)

    def arm_clipboard_timer(
        self,
        delay_seconds: float,
        expected_text: str | None,
        generation: int,
        attempt: int,
    ) -> None:
        """
        Start the clipboard cleanup timer. Callers must hold clipboard_lock.

        Args:
            delay_seconds (float): Delay before the cleanup runs.
            expected_text (str | None): Expected clipboard content.
            generation (int): Clipboard generation token.
            attempt (int): Zero-based retry attempt for this generation.

        Returns:
            None
        """
        timer = threading.Timer(
            delay_seconds,
            self.clear_managed_clipboard,
            kwargs={
                "expected_text": expected_text,
                "generation": generation,
                "force": False,
                "attempt": attempt,
            },
        )
        timer.daemon = True
        self.clipboard_timer = timer
        timer.start()

    def clear_managed_clipboard(
        self,
        expected_text: str | None = None,
        generation: int | None = None,
        force: bool = False,
        attempt: int = 0,
    ) -> None:
        """
        Clear clipboard content managed by snippet expansion.

        When the clipboard cannot be reached, the cleanup is retried instead of
        being abandoned, so a clipboard briefly locked by another application
        does not leave snippet content behind.

        Args:
            expected_text (str | None): Expected clipboard content.
            generation (int | None): Clipboard generation token.
            force (bool): When True, clear regardless of current clipboard text.
            attempt (int): Zero-based retry attempt for this generation.

        Returns:
            None
        """
        try:
            with self.clipboard_lock:
                if generation is not None and generation != self.clipboard_generation:
                    return

            if not force:
                readable, current_text = self.read_clipboard()
                if not readable:
                    self.retry_clipboard_clear(expected_text, generation, attempt)
                    return
                if expected_text is not None and current_text != expected_text:
                    logger.debug("Clipboard changed since expansion. Skipping cleanup.")
                    self.reset_clipboard_state(generation)
                    return

            if not self.empty_clipboard():
                self.retry_clipboard_clear(expected_text, generation, attempt)
                return

            self.reset_clipboard_state(generation)
            logger.info("Managed clipboard content cleared")
            self.notify_clipboard_cleared()
        except Exception:
            logger.exception("Failed to clear managed clipboard content")

    def notify_clipboard_cleared(self) -> None:
        """
        Tell the UI that managed clipboard content was cleared.

        Runs on the cleanup timer thread, so the callback is responsible for
        hopping to the GUI thread.

        Returns:
            None
        """
        if not callable(self.clipboard_cleared_callback):
            return
        try:
            self.clipboard_cleared_callback()
        except Exception:
            logger.exception("clipboard_cleared_callback raised")

    def reset_clipboard_state(self, generation: int | None) -> None:
        """
        Drop the tracked clipboard content unless a newer expansion took over.

        Args:
            generation (int | None): Clipboard generation token being retired.

        Returns:
            None
        """
        with self.clipboard_lock:
            if generation is None or generation == self.clipboard_generation:
                self.last_managed_clipboard = None
                self.clipboard_timer = None

    def retry_clipboard_clear(
        self,
        expected_text: str | None,
        generation: int | None,
        attempt: int,
    ) -> None:
        """
        Re-arm clipboard cleanup after a failed attempt.

        Args:
            expected_text (str | None): Expected clipboard content.
            generation (int | None): Clipboard generation token.
            attempt (int): Zero-based attempt that just failed.

        Returns:
            None
        """
        if generation is None or attempt + 1 >= CLIPBOARD_CLEAR_RETRY_ATTEMPTS:
            logger.error(
                "Giving up on clipboard cleanup after %s attempts; "
                "snippet content may remain on the clipboard",
                attempt + 1,
            )
            return

        with self.clipboard_lock:
            if generation != self.clipboard_generation:
                return
            self.arm_clipboard_timer(
                delay_seconds=CLIPBOARD_CLEAR_RETRY_SECONDS,
                expected_text=expected_text,
                generation=generation,
                attempt=attempt + 1,
            )
        logger.warning(
            "Clipboard cleanup attempt %s failed; retrying in %s seconds",
            attempt + 1,
            CLIPBOARD_CLEAR_RETRY_SECONDS,
        )

    @lru_cache(maxsize=256)
    def load_snippet_by_trigger(self, trigger: str) -> dict:
        """
        Load full snippet data for a trigger on demand.

        Args:
            trigger (str): The trigger to load.
        
        Returns:
            dict: The matching snippet dictionary, or an empty dict.
        """
        return self.snippets_db.get_snippet_by_trigger(trigger) or {}

    def match_trigger_suffix(self) -> str | None:
        """
        Match the longest enabled trigger at the end of the buffer.
        
        Returns:
            str | None: The matched trigger, or None if no trigger matches.
        """
        if not self.buffer:
            return None

        node = self.trigger_trie
        matched_trigger = None

        for char in reversed(self.buffer[-self.max_trigger_len:]):
            node = node.get(char)
            if node is None:
                break
            if "__trigger__" in node:
                matched_trigger = node["__trigger__"]

        return matched_trigger

    def clear_buffer(self) -> None:
        """
        Reset the internal typing buffer and cursor state.

        Clears the buffer, resets the cursor position, and disables
        trigger mode.
        
        Returns:
            None
        """
        logger.debug("Clearing trigger buffer")

        with self.buffer_lock:
            self.buffer = ""
            self.cursor_pos = 0
            self.trigger_flag = False

    def on_key_press(self, key) -> None:
        """
        Handle key press events from the keyboard listener.

        Processes navigation, deletion, termination keys, and character
        input to detect and expand snippet triggers. Implements debouncing
        to prevent excessive event processing.

        Args:
            key (Any): The key event received from the listener.
        
        Returns:
            None
        """
        try:
            if self.disabled:
                return

            # Rate limiting: skip processing if events are coming too fast
            now = time.monotonic() # monotonic cannot go backwards, good for measuring elapsed time
            elapsed_ms = (now - self.last_event_processed_at) * 1000
            if elapsed_ms < self.keyboard_debounce_ms:
                return
            self.last_event_processed_at = now

            trigger_timeout = self.get_trigger_timeout_seconds()
            if (
                trigger_timeout is not None
                and self.last_keypress_at
                and (time.monotonic() - self.last_keypress_at) > trigger_timeout
            ):
                logger.debug("Clearing buffer due to inactivity timeout")
                self.clear_buffer()

            if self.handle_navigation_and_deletion(key):
                self.last_keypress_at = now
                return

            if self.should_clear_on(key):
                logger.debug("Clearing buffer due to sensitive or terminating key")
                self.clear_buffer()
                self.last_keypress_at = 0.0
                return

            if hasattr(key, "char") and key.char:
                self.last_keypress_at = time.monotonic()
                self.handle_char(char=key.char)
            else:
                self.clear_buffer()
                self.last_keypress_at = 0.0
        except Exception:
            logger.exception("Error in key handler, resetting buffer")
            self.clear_buffer()

    def handle_navigation_and_deletion(self, key) -> bool:
        """
        Handle cursor navigation and deletion keys.

        Updates the buffer and cursor position when left, right,
        backspace, or delete keys are pressed. Also refreshes the
        on-screen trigger countdown (see refresh_trigger_countdown), since
        editing/moving within an active trigger buffer is activity just
        like typing a character is.

        Args:
            key (Any): The key event.

        Returns:
            bool: True if the key was handled, otherwise False.
        """
        if key == self.keyboard.Key.left:
            if self.cursor_pos > 0:
                self.cursor_pos -= 1
        elif key == self.keyboard.Key.right:
            if self.cursor_pos < len(self.buffer):
                self.cursor_pos += 1
        elif key == self.keyboard.Key.backspace:
            if self.cursor_pos > 0:
                self.buffer = self.buffer[:self.cursor_pos - 1] + self.buffer[self.cursor_pos:]
                self.cursor_pos -= 1
        elif key == self.keyboard.Key.delete:
            if self.cursor_pos < len(self.buffer):
                self.buffer = self.buffer[:self.cursor_pos] + self.buffer[self.cursor_pos + 1:]
        else:
            return False

        active_prefix_char = self.buffer[0] if self.buffer and self.buffer[0] in self.trigger_prefixes else None
        self.refresh_trigger_countdown(active_prefix_char)
        return True

    def should_clear_on(self, key) -> bool:
        """
        Determine whether the buffer should be cleared for a given key.

        Args:
            key (Any): The key event.
        
        Returns:
            bool: True if the buffer should be cleared, otherwise False.
        """
        sensitive_keys = {
            getattr(self.keyboard.Key, "space", None),
            getattr(self.keyboard.Key, "enter", None),
            getattr(self.keyboard.Key, "tab", None),
            getattr(self.keyboard.Key, "esc", None),
            getattr(self.keyboard.Key, "shift", None),
            getattr(self.keyboard.Key, "shift_l", None),
            getattr(self.keyboard.Key, "shift_r", None),
            getattr(self.keyboard.Key, "ctrl_l", None),
            getattr(self.keyboard.Key, "ctrl_r", None),
            getattr(self.keyboard.Key, "alt_l", None),
            getattr(self.keyboard.Key, "alt_r", None),
            getattr(self.keyboard.Key, "alt_gr", None),
            getattr(self.keyboard.Key, "cmd", None),
            getattr(self.keyboard.Key, "cmd_l", None),
            getattr(self.keyboard.Key, "cmd_r", None),
            getattr(self.keyboard.Key, "caps_lock", None),
            getattr(self.keyboard.Key, "insert", None),
            getattr(self.keyboard.Key, "home", None),
            getattr(self.keyboard.Key, "end", None),
            getattr(self.keyboard.Key, "page_up", None),
            getattr(self.keyboard.Key, "page_down", None),
            getattr(self.keyboard.Key, "menu", None),
            getattr(self.keyboard.Key, "print_screen", None),
            getattr(self.keyboard.Key, "scroll_lock", None),
            getattr(self.keyboard.Key, "pause", None),
        }
        sensitive_keys.discard(None)
        if key in sensitive_keys:
            return True

        key_name = getattr(key, "name", "")
        return bool(key_name and key_name.startswith("f"))

    def refresh_trigger_countdown(self, prefix_char: str | None) -> None:
        """
        Re-notify trigger_detected_callback so the status bar countdown
        restarts from the full configured timeout.

        Called on every keystroke that touches an active trigger buffer
        (typing, backspace/delete, arrow movement) so the on-screen count
        stays in sync with last_keypress_at, which those same keys refresh
        (see on_key_press / handle_navigation_and_deletion).

        Args:
            prefix_char (str | None): The buffer's leading trigger-prefix
                character, or None when the buffer holds no active trigger.

        Returns:
            None
        """
        if not prefix_char or not callable(self.trigger_detected_callback):
            return
        try:
            self.trigger_detected_callback(prefix_char, self.get_trigger_timeout_seconds())
        except Exception:
            logger.exception("trigger_detected_callback raised")

    def handle_char(self, char: str) -> None:
        """
        Append a character to the buffer and attempt trigger matching.

        Updates the internal buffer, enforces maximum length, refreshes the
        on-screen trigger countdown while a potential trigger is being typed,
        and expands the snippet if a full trigger match is detected.

        Args:
            char (str): The character to append.

        Returns:
            None
        """
        logger.debug("Appending character to buffer: %r", char)

        with self.buffer_lock:
            self.trigger_flag = True
            self.buffer = self.buffer[:self.cursor_pos] + char + self.buffer[self.cursor_pos:]
            self.cursor_pos += 1

            if len(self.buffer) > self.max_trigger_len:
                overflow = len(self.buffer) - self.max_trigger_len
                self.buffer = self.buffer[overflow:]
                self.cursor_pos = max(0, self.cursor_pos - overflow)

            logger.debug("Buffer length: %d Cursor: %d", len(self.buffer), self.cursor_pos)

            # A buffer starting with a known trigger-prefix character (e.g.
            # "/") is a potential trigger still being typed, whether this is
            # the first character or a later one.
            active_prefix_char = self.buffer[0] if self.buffer and self.buffer[0] in self.trigger_prefixes else None
            trigger = self.match_trigger_suffix()

        self.refresh_trigger_countdown(active_prefix_char)

        if trigger:
            snippet_meta = self.trigger_map.get(trigger, {})
            snippet_entry = self.load_snippet_by_trigger(trigger)
            style = snippet_meta.get("paste_style", "Keystroke")
            return_press = snippet_meta.get("return_press", False)

            if not snippet_entry:
                logger.warning("Trigger matched but snippet data could not be loaded: %s", trigger)
                self.clear_buffer()
                return

            # Vault intercept: intercept if encrypted OR if snippet lives in a vault folder
            folder = snippet_entry.get("folder", "")
            is_vault_content = (
                snippet_entry.get("is_encrypted") or
                (folder and folder in self.vault_folder_set)
            )

            if is_vault_content:
                from utils.vault_manager import VaultManager
                vm = VaultManager.get_instance()
                if vm.is_unlocked():
                    if snippet_entry.get("is_encrypted"):
                        raw = snippet_entry.get("snippet", "")
                        try:
                            aad = (snippet_entry.get("vault_uuid") or "").encode()
                            snippet_text = vm.decrypt(raw, aad=aad)
                            vm.reset_activity_timer()
                        except Exception:
                            # Content may not be encrypted yet (DB inconsistency); use raw
                            logger.warning("Decrypt failed for trigger %s; using raw content", trigger)
                            snippet_text = raw
                    else:
                        # Folder is vault-protected but snippet not yet encrypted
                        snippet_text = snippet_entry.get("snippet", "")
                else:
                    # Vault is locked - show unlock prompt on main thread
                    if hasattr(self, "vault_unlock_callback") and self.vault_unlock_callback:
                        cb = self.vault_unlock_callback
                        trig = trigger
                        se = snippet_entry
                        st = style
                        rp = return_press
                        threading.Thread(
                            target=lambda: cb(trig, se, st, rp),
                            daemon=True,
                        ).start()
                    self.clear_buffer()
                    return
            else:
                snippet_text = snippet_entry.get("snippet", "")

            # Check for encrypted placeholders if vault is not already being unlocked
            if not is_vault_content and self.has_encrypted_placeholders(snippet_text):
                from utils.vault_manager import VaultManager
                vm = VaultManager.get_instance()
                if not vm.is_unlocked():
                    if hasattr(self, "vault_unlock_callback") and self.vault_unlock_callback:
                        cb = self.vault_unlock_callback
                        trig = trigger
                        se = snippet_entry
                        st = style
                        rp = return_press
                        threading.Thread(
                            target=lambda: cb(trig, se, st, rp),
                            daemon=True,
                        ).start()
                    self.clear_buffer()
                    return

            # By this point snippet_text is guaranteed plaintext (either it
            # was never encrypted, or the vault checks above already
            # resolved/deferred it). Check for [[name]] fields that need a
            # value from the user before pasting.
            names = self.get_dynamic_placeholder_names(snippet_text)
            if names:
                if hasattr(self, "dynamic_placeholder_callback") and self.dynamic_placeholder_callback:
                    cb = self.dynamic_placeholder_callback
                    trig = trigger
                    se = snippet_entry
                    st = style
                    rp = return_press
                    threading.Thread(
                        target=lambda: cb(trig, se, st, rp),
                        daemon=True,
                    ).start()
                self.clear_buffer()
                return

            logger.info("Trigger matched: %s", trigger)
            try:
                self.expand(trigger, snippet_text, style, return_press)
            except Exception:
                logger.exception("expand() raised in handle_char")
                self.disabled = False
            self.clear_buffer()

    def expand_clipboard(self, snippet: str, return_press: bool = False) -> None:
        """
        Expand a snippet using clipboard paste (non-blocking).

        Audit 3.5: Spawns a background thread to copy the snippet to the
        clipboard and simulate the paste shortcut, so the keyboard listener
        thread is not held while the copy completes. The background thread
        re-enables event processing (self.disabled) when done.

        The copy goes through copy_to_clipboard(), which on Windows keeps the
        snippet out of clipboard history (Win+V) and Cloud Clipboard.

        Args:
            snippet (str): The snippet text to insert.
            return_press (bool): Whether to simulate an Enter key press after paste.
        
        Returns:
            None
        """
        logger.debug("Expanding snippet via clipboard (async)")

        def copy_and_paste() -> None:
            try:
                self.copy_to_clipboard(snippet)
                self.schedule_clipboard_clear(snippet)
                # Brief pause to ensure the clipboard is populated before pasting
                time.sleep(0.05)
                with self.controller.pressed(self.paste_mod):
                    self.controller.press("v")
                    self.controller.release("v")
                if return_press:
                    time.sleep(0.02)
                    self.controller.press(self.keyboard.Key.enter)
                    self.controller.release(self.keyboard.Key.enter)
            except Exception:
                logger.exception("Clipboard expand failed")
            finally:
                logger.debug("Clipboard expand complete; re-enabling listener")
                self.disabled = False

        t = threading.Thread(target=copy_and_paste, daemon=True)
        t.start()

    def expand_keystrokes(self, snippet: str, return_press: bool = False) -> None:
        """
        Expand a snippet by simulating keystrokes (non-blocking).

        Spawns a background thread to type the snippet character by
        character so the pynput listener thread is not held during
        expansion. The background thread re-enables event processing
        (self.disabled) when done.

        Args:
            snippet (str): The snippet text to insert.
            return_press (bool): Whether to simulate an Enter key press after typing.

        Returns:
            None
        """
        logger.debug("Expanding snippet via keystrokes (async)")

        def type_snippet() -> None:
            try:
                for ch in snippet:
                    if ch == "\n":
                        self.controller.press(self.keyboard.Key.enter)
                        self.controller.release(self.keyboard.Key.enter)
                    else:
                        self.controller.press(ch)
                        self.controller.release(ch)
                if return_press:
                    self.controller.press(self.keyboard.Key.enter)
                    self.controller.release(self.keyboard.Key.enter)
            except Exception:
                logger.exception("Error occurred while expanding keystrokes")
            finally:
                logger.debug("Keystroke expand complete; re-enabling listener")
                self.disabled = False

        t = threading.Thread(target=type_snippet, daemon=True)
        t.start()

    def expand(self, trigger: str, snippet: str, paste_style: str, return_press: bool,
               dynamic_values: dict | None = None) -> None:
        """
        Remove the trigger text and insert the expanded snippet.

        Deletes the matched trigger from the input field, processes
        placeholders and nested snippets, and inserts the expanded
        content using the configured paste style.

        Args:
            trigger (str): The matched trigger text.
            snippet (str): The snippet content to insert.
            paste_style (str): The expansion method ("Clipboard" or other).
            return_press (bool): Whether to simulate an additional
                return key press after expansion.
            dynamic_values (dict | None): User-supplied values for any
                [[name]] placeholders, collected via an input dialog before
                this call. Substituted after all other placeholder/nested
                resolution so it also reaches [[name]] tokens pulled in
                from nested snippets.

        Returns:
            None
        """
        logger.info("Expanding snippet for trigger: %s", trigger)

        # Preprocess for placeholders and nested snippets
        snippet = self.process_snippet_text(snippet)
        if dynamic_values:
            snippet = substitute_dynamic_placeholders(snippet, dynamic_values)

        trigger_len = len(trigger)
        trigger_start = self.buffer.rfind(trigger)
        
        if trigger_start == -1:
            logger.warning("Trigger not found in buffer. Aborting expansion.")
            return

        trigger_end = trigger_start + trigger_len
        chars_before_cursor = self.cursor_pos - trigger_start
        chars_after_cursor = trigger_end - self.cursor_pos

        # Delete the trigger from the input
        for _ in range(chars_before_cursor):
            self.controller.press(self.keyboard.Key.backspace)
            self.controller.release(self.keyboard.Key.backspace)

        # Delete any characters after the cursor that are part of the trigger
        for _ in range(chars_after_cursor):
            self.controller.press(self.keyboard.Key.delete)
            self.controller.release(self.keyboard.Key.delete)
        
        logger.debug("Stopping listener to prevent feedback")
        # Temporarily disable event processing, but do NOT stop listener
        self.disabled = True

        if str(paste_style).lower() == "clipboard":
            # expand_clipboard runs on a background thread and owns the
            # self.disabled lifecycle   it re-enables when the paste is done.
            self.expand_clipboard(snippet, return_press=return_press)
        else:
            # expand_keystrokes runs on a background thread and owns the
            # self.disabled lifecycle   it re-enables when typing is done.
            self.expand_keystrokes(snippet, return_press=return_press)

    def get_dynamic_placeholder_names(self, snippet_text: str) -> list[str]:
        """
        Determine which [[name]] fields a snippet needs filled in before pasting.

        Runs the snippet through the same placeholder/nested-snippet
        resolution used at expansion time, then scans the fully-flattened
        result for [[name]] tokens - so placeholders pulled in from a
        nested {/trigger} reference are found too, not just top-level ones.

        Args:
            snippet_text (str): The raw (already-decrypted) snippet body.

        Returns:
            list[str]: Unique placeholder names, in first-seen order.
        """
        flattened = self.process_snippet_text(snippet_text)
        return extract_dynamic_placeholder_names(flattened)

    def process_snippet_text(self, text: str, depth: int = 0, seen=None) -> str:
        """
        Process snippet text by replacing placeholders and nested references.

        Replaces dynamic placeholders such as date, time, and greeting,
        and resolves nested snippet references with recursion depth
        protection.

        Args:
            text (str): The snippet text to process.
            depth (int): Current recursion depth.
            seen (set | None): Set of triggers already processed to prevent loops.
        
        Returns:
            str: The processed snippet text.
        """
        if seen is None:
            seen = set()

        if depth > 5:  # configurable max depth
            logger.warning("Max snippet recursion depth reached.")
            return text

        # --    Dynamic placeholders ---
        now = datetime.datetime.now()

        # Greeting detection
        hour = now.hour
        if 5 <= hour < 11:
            greeting = "Good Morning"
        elif 11 <= hour < 17:
            greeting = "Good Afternoon"
        elif 17 <= hour < 22:
            greeting = "Good Evening"
        else:
            greeting = "Hello"  # fallback

        replacements = {
            # Dates
            "{{date}}": now.strftime("%Y-%m-%d"),           # 2025-09-04
            "{{date_long}}": now.strftime("%B %d, %Y"),     # September 04, 2025
            "{{weekday}}": now.strftime("%A"),              # Thursday
            "{{month}}": now.strftime("%B"),                # September
            "{{year}}": now.strftime("%Y"),                 # 2025

            # Times
            "{{time}}": now.strftime("%H:%M"),              # 14:35
            "{{time_ampm}}": now.strftime("%I:%M %p"),      # 02:35 PM
            "{{hour}}": now.strftime("%H"),                 # 14
            "{{minute}}": now.strftime("%M"),               # 35
            "{{second}}": now.strftime("%S"),               # 07
            "{{datetime}}": now.strftime("%Y-%m-%d %H:%M"), # 2025-09-04 14:35

            # Contextual
            "{{greeting}}": greeting,                       # Good afternoon
        }
        for key, val in replacements.items():
            text = text.replace(key, val)

        # --    User-defined custom placeholders ---
        for ph in self.custom_placeholders:
            if ph.get("is_encrypted"):
                from utils.vault_manager import VaultManager
                vm = VaultManager.get_instance()
                try:
                    aad = (ph.get("vault_uuid") or "").encode()
                    val = vm.decrypt(ph["value"], aad=aad) if vm.is_unlocked() else ""
                except Exception:
                    logger.warning("Failed to decrypt placeholder '%s'", ph.get("name"))
                    val = ""
            else:
                val = ph["value"]
            text = text.replace(f"{{{{{ph['name']}}}}}", val)

        # --    Nested snippets --- ([^\w{] excludes "{" so a stray/typo'd
        # {{name}} that didn't match a known placeholder above is left
        # literal instead of being misread as a nested-snippet reference.
        nested_pattern = re.compile(r"\{[^\w{](.+?)\}")
        matches = list(nested_pattern.finditer(text))

        if not matches:
            return text

        result = []
        last_idx = 0

        for match in matches:
            result.append(text[last_idx:match.start()])
            trigger = match.group(0)[1:-1]

            if trigger in seen:     # detect circular call
                logger.error("Detected circular reference for trigger '%s'", trigger)
                replacement = f"{{/{trigger}}}"

            elif trigger in self.trigger_map:
                seen.add(trigger)
                nested_entry = self.load_snippet_by_trigger(trigger)
                nested_snip = nested_entry.get("snippet", "")
                replacement = self.process_snippet_text(
                    nested_snip, depth + 1, seen
                )
                seen.remove(trigger)

            else:   # do nothing
                # replacement = f"{{/{trigger}}}"

                # Catch missing embed snippet. Fixing Issue #23
                replacement = f"[Error  Could not locate snippet: {trigger}]"

            result.append(replacement)
            last_idx = match.end()

        result.append(text[last_idx:])
        return "".join(result)

    # ---   Start/Stop Functions -----

    def start(self) -> None:
        """
        Start the keyboard listener.
        
        Returns:
            None
        """
        logger.info("Starting SnippetExpander listener")
        self.listener.start()

    def stop(self) -> None:
        """
        Stop the keyboard listener.
        
        Returns:
            None
        """
        logger.info("Stopping SnippetExpander listener")
        self.cancel_clipboard_timer()
        if self.last_managed_clipboard:
            # Clear on the way out, but only when the clipboard still holds the
            # snippet we put there; the user's own clipboard is left intact.
            self.clear_managed_clipboard(
                expected_text=self.last_managed_clipboard,
                generation=self.clipboard_generation,
            )
        self.clear_buffer()
        self.listener.stop()

    def pause(self) -> None:
        """
        Temporarily disable snippet expansion.

        Clears the buffer and prevents trigger handling until resumed.
        
        Returns:
            None
        """
        logger.info("Pausing SnippetExpander")
        self.disabled = True
        self.clear_buffer()

    def resume(self) -> None:
        """
        Resume snippet expansion after being paused.
        
        Returns:
            None
        """
        logger.info("Resuming SnippetExpander")
        self.disabled = False

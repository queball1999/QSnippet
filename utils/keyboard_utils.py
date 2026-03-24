import logging
import platform
import pyperclip
import re
import datetime
import threading
import time
from functools import lru_cache

from utils.snippet_db import SnippetDB

# Windows clipboard API via pywin32
if platform.system() == "Windows":
    import win32clipboard

logger = logging.getLogger(__name__)

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
        self.buffer_inactivity_timeout = 5.0
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

    # Incremental trigger-map updates - update or remove a
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

    def empty_clipboard_windows(self) -> None:
        """
        Empty clipboard on Windows using pywin32.

        Uses win32clipboard API and always closes the clipboard handle
        to avoid locking it for other applications.
        
        Returns:
            None
        """
        opened = False
        try:
            win32clipboard.OpenClipboard()
            opened = True
            win32clipboard.EmptyClipboard()
            logger.debug("Active clipboard cleared via win32clipboard.EmptyClipboard()")
        except Exception as e:
            logger.warning("win32clipboard clear failed: %s; falling back to pyperclip", e)
            try:
                pyperclip.copy("")
            except Exception:
                logger.exception("pyperclip fallback also failed")
        finally:
            if opened:
                try:
                    win32clipboard.CloseClipboard()
                except Exception:
                    logger.exception("Failed to close Windows clipboard handle")

    def empty_clipboard_generic(self) -> None:
        """
        Empty clipboard using cross-platform method.
        
        Returns:
            None
        """
        try:
            pyperclip.copy("")
            logger.debug("Clipboard cleared")
        except Exception:
            logger.exception("Failed to clear clipboard")

    def empty_clipboard(self) -> None:
        """
        Empty the clipboard using the most appropriate method for the platform.
        
        Returns:
            None
        """
        if platform.system() == "Windows":
            self.empty_clipboard_windows()
        else:
            self.empty_clipboard_generic()

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

            timer = threading.Timer(
                timeout_seconds,
                self.clear_managed_clipboard,
                kwargs={
                    "expected_text": expected_text,
                    "generation": generation,
                    "force": False,
                },
            )
            timer.daemon = True
            self.clipboard_timer = timer
            timer.start()
            logger.debug("Scheduled clipboard cleanup in %s seconds", timeout_seconds)

    def clear_managed_clipboard(
        self,
        expected_text: str | None = None,
        generation: int | None = None,
        force: bool = False,
    ) -> None:
        """
        Clear clipboard content managed by snippet expansion.

        Args:
            expected_text (str | None): Expected clipboard content.
            generation (int | None): Clipboard generation token.
            force (bool): When True, clear regardless of current clipboard text.
        
        Returns:
            None
        """
        try:
            with self.clipboard_lock:
                if generation is not None and generation != self.clipboard_generation:
                    return

            current_text = ""
            if not force:
                current_text = pyperclip.paste()
                if expected_text is not None and current_text != expected_text:
                    logger.debug("Clipboard changed since expansion. Skipping cleanup.")
                    return

            self.empty_clipboard()
            with self.clipboard_lock:
                self.last_managed_clipboard = None
                self.clipboard_timer = None
            logger.info("Managed clipboard content cleared")
        except Exception:
            logger.exception("Failed to clear managed clipboard content")

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

            if self.last_keypress_at and (time.monotonic() - self.last_keypress_at) > self.buffer_inactivity_timeout:
                logger.debug("Clearing buffer due to inactivity timeout")
                self.clear_buffer()

            if self.handle_navigation_and_deletion(key):
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
        backspace, or delete keys are pressed.

        Args:
            key (Any): The key event.
        
        Returns:
            bool: True if the key was handled, otherwise False.
        """
        if key == self.keyboard.Key.left:
            if self.cursor_pos > 0:
                self.cursor_pos -= 1
            return True
        elif key == self.keyboard.Key.right:
            if self.cursor_pos < len(self.buffer):
                self.cursor_pos += 1
            return True
        elif key == self.keyboard.Key.backspace:
            if self.cursor_pos > 0:
                self.buffer = self.buffer[:self.cursor_pos - 1] + self.buffer[self.cursor_pos:]
                self.cursor_pos -= 1
            return True
        elif key == self.keyboard.Key.delete:
            if self.cursor_pos < len(self.buffer):
                self.buffer = self.buffer[:self.cursor_pos] + self.buffer[self.cursor_pos + 1:]
            return True
        return False

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

    def handle_char(self, char: str) -> None:
        """
        Append a character to the buffer and attempt trigger matching.

        Updates the internal buffer, enforces maximum length, and
        expands the snippet if a trigger match is detected.

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
            trigger = self.match_trigger_suffix()

        if trigger:
            snippet_meta = self.trigger_map.get(trigger, {})
            snippet_entry = self.load_snippet_by_trigger(trigger)
            style = snippet_meta.get("paste_style", "Keystroke")
            return_press = snippet_meta.get("return_press", False)

            if not snippet_entry:
                logger.warning("Trigger matched but snippet data could not be loaded: %s", trigger)
                self.clear_buffer()
                return

            logger.info("Trigger matched: %s", trigger)
            self.expand(trigger, snippet_entry.get("snippet", ""), style, return_press)
            self.clear_buffer()

    def expand_clipboard(self, snippet: str, return_press: bool = False) -> None:
        """
        Expand a snippet using clipboard paste (non-blocking).

        Audit 3.5: Spawns a background thread to copy the snippet to the
        clipboard and simulate the paste shortcut, so the keyboard listener
        thread is not held while pyperclip.copy() completes. The background
        thread re-enables event processing (self.disabled) when done.

        Args:
            snippet (str): The snippet text to insert.
            return_press (bool): Whether to simulate an Enter key press after paste.
        
        Returns:
            None
        """
        logger.debug("Expanding snippet via clipboard (async)")

        def copy_and_paste() -> None:
            try:
                pyperclip.copy(snippet)
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

    def expand_keystrokes(self, snippet) -> None:
        """
        Expand a snippet by simulating keystrokes.

        Types the snippet text character by character, handling
        newline characters appropriately.

        Args:
            snippet (str): The snippet text to insert.
        
        Returns:
            None
        """
        logger.debug("Expanding snippet via keystrokes")

        self.disabled = True    # Disable service temporarily
        try:
            # Simulate keystrokes for each character in the snippet
            for ch in snippet:
                if ch == "\n":
                    self.controller.press(self.keyboard.Key.enter)
                    self.controller.release(self.keyboard.Key.enter)
                else:
                    self.controller.press(ch)
                    self.controller.release(ch)
        except Exception:
            logger.exception("Error occurred while expanding keystrokes")
        finally:
            # Re-enable listener
            # Always re-enable to avoid errors
            self.disabled = False

    def expand(self, trigger: str, snippet: str, paste_style: str, return_press: bool) -> None:
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
        
        Returns:
            None
        """
        logger.info("Expanding snippet for trigger: %s", trigger)

        # Preprocess for placeholders and nested snippets
        snippet = self.process_snippet_text(snippet)

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
            # self.disabled lifecycle - it re-enables when the paste is done.
            self.expand_clipboard(snippet, return_press=return_press)
        else:
            try:
                self.expand_keystrokes(snippet)

                if return_press:
                    self.controller.press(self.keyboard.Key.enter)
                    self.controller.release(self.keyboard.Key.enter)
            finally:
                logger.debug("Restarting listener")
                self.disabled = False

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

        # --- Dynamic placeholders ---
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
            "{date}": now.strftime("%Y-%m-%d"),           # 2025-09-04
            "{date_long}": now.strftime("%B %d, %Y"),     # September 04, 2025
            "{weekday}": now.strftime("%A"),              # Thursday
            "{month}": now.strftime("%B"),                # September
            "{year}": now.strftime("%Y"),                 # 2025

            # Times
            "{time}": now.strftime("%H:%M"),              # 14:35
            "{time_ampm}": now.strftime("%I:%M %p"),      # 02:35 PM
            "{hour}": now.strftime("%H"),                 # 14
            "{minute}": now.strftime("%M"),               # 35
            "{second}": now.strftime("%S"),               # 07
            "{datetime}": now.strftime("%Y-%m-%d %H:%M"), # 2025-09-04 14:35

            # Contextual
            "{greeting}": greeting,                       # Good afternoon
        }
        for key, val in replacements.items():
            text = text.replace(key, val)

        # --- User-defined custom placeholders ---
        for ph in self.custom_placeholders:
            text = text.replace(f"{{{ph['name']}}}", ph["value"])

        # --- Nested snippets ---
        nested_pattern = re.compile(r"\{\W(.+?)\}")
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
                replacement = f"[Error - Could not locate snippet: {trigger}]"

            result.append(replacement)
            last_idx = match.end()

        result.append(text[last_idx:])
        return "".join(result)

    # ---- Start/Stop Functions -----

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
        self.clear_managed_clipboard(
            expected_text=self.last_managed_clipboard,
            generation=self.clipboard_generation,
            force=True,
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

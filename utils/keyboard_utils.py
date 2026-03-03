import logging
import platform
import pyperclip
import re
import datetime
from pynput import keyboard
from utils.snippet_db import SnippetDB

logger = logging.getLogger(__name__)



class SnippetExpander():
    def __init__(self, snippets_db: SnippetDB, parent) -> None:
        """
        Initialize the SnippetExpander.

        Loads snippets from the database, prepares trigger handling,
        initializes keyboard listener and controller, and configures
        internal state for buffer and trigger tracking.

        Args:
            snippets_db (SnippetDB): The snippet database instance.
            parent (Any): The parent object.

        Returns:
            None
        """
        logger.info("Initializing SnippetExpander")

        self.snippets_db = snippets_db
        self.snippets = self.snippets_db.get_all_snippets()
        self.parent = parent

        self.disabled = False
        self.trigger_prefixs = self.retrieve_trigger_chars(self.snippets)
        self.keys_to_ignore = [keyboard.Key.space, keyboard.Key.shift, keyboard.Key.enter, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r]
        self.buffer = ""
        self.cursor_pos = 0  # Cursor position in the buffer
        self.max_trigger_len = 255
        self.trigger_flag = False   # Used to track if we are within a snippet trigger sequence

        self.build_trigger_map()

        self.listener = keyboard.Listener(on_press=self._on_key_press)
        self.controller = keyboard.Controller()
        self._paste_mod = keyboard.Key.cmd if platform.system() == "Darwin" else keyboard.Key.ctrl

        logger.info("SnippetExpander initialized successfully")

    def build_trigger_map(self) -> None:
        """
        Build the trigger lookup map and compiled regex.

        Creates a dictionary of enabled snippet triggers mapped to their
        data and compiles a regex pattern to detect trigger matches
        at the end of the buffer.

        Returns:
            None
        """
        logger.info("Building trigger map")
    
        self.trigger_map = {
            s["trigger"]: s
            for s in self.snippets
            if s.get("enabled", True)
        }
        escapes = sorted(
            (re.escape(t) for t in self.trigger_map),
            key=len, reverse=True
        )
        pattern = r'(?:' + '|'.join(escapes) + r')\Z'
        self.trigger_regex = re.compile(pattern)

        logger.debug(f"Trigger map size: {len(self.trigger_map)}")
        logger.debug(f"Trigger regex: {self.trigger_regex}")

    def refresh_snippets(self) -> None:
        """
        Reload snippets from the database and rebuild trigger handling.

        Refreshes the internal snippet list, trigger map, and trigger
        prefix characters to reflect database updates.

        Returns:
            None
        """
        logger.info("Refreshing snippets from database")

        self.snippets = self.snippets_db.get_all_snippets()
        self.build_trigger_map()    # Rebuild trigger map
        # This single line fixes the issue where new snippets don't get recognized until restart
        # smh...
        self.trigger_prefixs = self.retrieve_trigger_chars(self.snippets)   # Reload prefixes
        logging.info("SnippetExpander reloaded snippets from DB.")

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

        logger.debug(f"Trigger prefixes: {trigger_prefixs}")
        return trigger_prefixs

    def clear_buffer(self) -> None:
        """
        Reset the internal typing buffer and cursor state.

        Clears the buffer, resets the cursor position, and disables
        trigger mode.

        Returns:
            None
        """
        logger.debug("Clearing trigger buffer")

        self.buffer = ""
        self.cursor_pos = 0
        self.trigger_flag = False

    def _on_key_press(self, key) -> None:
        """
        Handle key press events from the keyboard listener.

        Processes navigation, deletion, termination keys, and character
        input to detect and expand snippet triggers.

        Args:
            key (Any): The key event received from the listener.

        Returns:
            None
        """
        try:
            # Detect if paused and skip if true
            if self.disabled:
                return
            
            # Handle navigation and deletion keys
            if self.handle_navigation_and_deletion(key):
                return
            
            # Clear buffer on certain keys
            if self.should_clear_on(key):
                logger.debug("Clearing buffer due to terminating key")
                self.clear_buffer()
                return   

            # Handle character keys
            if hasattr(key, "char") and key.char:
                # Exit if not in trigger mode and char not a trigger prefix
                if not self.trigger_flag and key.char not in self.trigger_prefixs:  # Exit if true
                    self.clear_buffer()
                    return
                
                # Handle character input
                self.handle_char(char=key.char)
            else:
                # any other special key resets buffer
                self.clear_buffer()
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
        if key == keyboard.Key.left:
            if self.cursor_pos > 0:
                self.cursor_pos -= 1
            return True
        elif key == keyboard.Key.right:
            if self.cursor_pos < len(self.buffer):
                self.cursor_pos += 1
            return True
        elif key == keyboard.Key.backspace:
            if self.cursor_pos > 0:
                self.buffer = self.buffer[:self.cursor_pos - 1] + self.buffer[self.cursor_pos:]
                self.cursor_pos -= 1
            return True
        elif key == keyboard.Key.delete:
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
        if key in (keyboard.Key.space,
                   keyboard.Key.enter,
                   keyboard.Key.tab,
                   keyboard.Key.shift,
                   keyboard.Key.ctrl_l,
                   keyboard.Key.ctrl_r):
            return True
        return False

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
        # Trigger mode detection
        self.trigger_flag = True

        logger.debug(f"Appending character to buffer: {char}")
            
        # Still in trigger mode; update buffer
        logger.debug(f"Appending buffer with {char}")
        self.buffer = self.buffer[:self.cursor_pos] + char + self.buffer[self.cursor_pos:]
        self.cursor_pos += 1

        # Trim buffer if over max trigger length
        if len(self.buffer) > self.max_trigger_len:
            overflow = len(self.buffer) - self.max_trigger_len
            self.buffer = self.buffer[overflow:]
            self.cursor_pos = max(0, self.cursor_pos - overflow)

        logger.debug(f"Buffer state: '{self.buffer}' Cursor: {self.cursor_pos}")

        response = self.trigger_regex.search(self.buffer)
        logger.debug(f"Regex match: {response}")

        if response:
            trigger = response.group(0)
            snippet = self.trigger_map[trigger]
            style = snippet.get("paste_style", "Keystroke")
            return_press = snippet.get("return_press", False)

            logger.info(f"Trigger matched: {trigger}")
            self.expand(trigger, snippet["snippet"], style, return_press)
            self.clear_buffer()

    def expand_clipboard(self, snippet) -> None:
        """
        Expand a snippet using clipboard paste.

        Copies the snippet text to the clipboard and simulates a
        paste keyboard shortcut.

        Args:
            snippet (str): The snippet text to insert.

        Returns:
            None
        """
        logger.debug("Expanding snippet via clipboard")
        # NOTE: xclip or xsel must be installed on Linux for clipboard support

        pyperclip.copy(snippet)
        with self.controller.pressed(self._paste_mod):
            self.controller.press("v")
            self.controller.release("v")

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
                    self.controller.press(keyboard.Key.enter)
                    self.controller.release(keyboard.Key.enter)
                else:
                    self.controller.press(ch)
                    self.controller.release(ch)
        except Exception as e:
            logger.error(f"Error occured while expanding keystrokes: {e}")
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
        logger.info(f"Expanding snippet for trigger: {trigger}")

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
            self.controller.press(keyboard.Key.backspace)
            self.controller.release(keyboard.Key.backspace)

        # Delete any characters after the cursor that are part of the trigger
        for _ in range(chars_after_cursor):
            self.controller.press(keyboard.Key.delete)
            self.controller.release(keyboard.Key.delete)
        
        logger.debug("Stopping listener to prevent feedback")
        # Temporarily disable event processing, but do NOT stop listener
        self.disabled = True

        # Expand the snippet
        try:
            if paste_style == "Clipboard":
                self.expand_clipboard(snippet)
            else:
                self.expand_keystrokes(snippet)

            if return_press:
                self.controller.press(keyboard.Key.enter)
                self.controller.release(keyboard.Key.enter) 
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
            "{location}": "Unknown Location",             # still placeholder
        }
        for key, val in replacements.items():
            text = text.replace(key, val)

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
                logger.error(f"Detected circular reference for trigger '{trigger}'")
                replacement = f"{{/{trigger}}}"

            elif trigger in self.trigger_map:   # check for trigger in map
                seen.add(trigger)
                nested_snip = self.trigger_map[trigger]["snippet"]
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

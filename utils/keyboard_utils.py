import logging
import platform
import pyperclip
import re
import datetime
from pynput import keyboard
from utils.snippet_db import SnippetDB

logger = logging.getLogger(__name__)

class SnippetExpander():
    def __init__(self, snippets_db: SnippetDB, parent):
        # Updated to SnippetDB method 06/28/25
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

    def build_trigger_map(self):
        # Build an enabled trigger→snippet map for quick lookup
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
        logger.debug(self.trigger_regex)

    def refresh_snippets(self):
        print("refresh snippets")
        self.snippets = self.snippets_db.get_all_snippets()
        self.build_trigger_map()
        logging.info("SnippetExpander reloaded snippets from DB.")

    def retrieve_trigger_chars(self, snippets):
        """
        This function loops through the triggers and grabs the first characters.
        """
        trigger_prefixs = []
        for snippet in snippets:
            prefix = snippet["trigger"][0]
            if snippet.get("enabled", True) and prefix not in trigger_prefixs:
                trigger_prefixs.append(prefix)
        return trigger_prefixs

    def clear_buffer(self):
        logger.debug("Clearing Buffer!")
        self.buffer = ""
        self.cursor_pos = 0
        self.trigger_flag = False

    def _on_key_press(self, key):
        """ This function is called on every key press. """
        try:
            # Detect if paused and skip if true
            if self.disabled:
                return
            
            if self._handle_navigation_and_deletion(key):
                return
            
            if self._should_clear_on(key):
                self.clear_buffer()
                return
                
            
            if hasattr(key, "char") and key.char:
                if not self.trigger_flag and key.char not in self.trigger_prefixs:  # Exit if true
                    self.clear_buffer()
                    return
                
                self._handle_char(char=key.char)
            else:
                # any other special key resets us
                self.clear_buffer()
        except Exception:
            logger.exception("Error in key handler, resetting buffer")
            self.clear_buffer()

    def _handle_navigation_and_deletion(self, key) -> bool:
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

    def _should_clear_on(self, key) -> bool:
        # any punctuation, whitespace, or modifiers break a snippet
        if key in (keyboard.Key.space,
                   keyboard.Key.enter,
                   keyboard.Key.tab,
                   keyboard.Key.shift,
                   keyboard.Key.ctrl_l,
                   keyboard.Key.ctrl_r):
            return True
        return False

    def _handle_char(self, char: str):
        # Trigger mode detection
        self.trigger_flag = True
            
        # Still in trigger mode; update buffer
        logger.debug(f"Appending buffer with {char}")
        self.buffer = self.buffer[:self.cursor_pos] + char + self.buffer[self.cursor_pos:]
        self.cursor_pos += 1

        # Trim buffer if over max trigger length
        if len(self.buffer) > self.max_trigger_len:
            overflow = len(self.buffer) - self.max_trigger_len
            self.buffer = self.buffer[overflow:]
            self.cursor_pos = max(0, self.cursor_pos - overflow)

        logger.debug(f"Buffer: {self.buffer}, Cursor: {self.cursor_pos}")

        response = self.trigger_regex.search(self.buffer)
        logger.debug(f"Regex Response: {response}")
        if response:
            trigger = response.group(0)
            snippet = self.trigger_map[trigger]
            style = snippet.get("paste_style", "Keystroke")
            return_press = snippet.get("return_press", False)
            self._expand(trigger, snippet["snippet"], style, return_press)
            self.clear_buffer()

    def _expand_clipboard(self, snippet):
        pyperclip.copy(snippet)
        with self.controller.pressed(self._paste_mod):
            self.controller.press("v")
            self.controller.release("v")

    def _expand_keystrokes(self, snippet):
        for ch in snippet:
            if ch == "\n":
                self.controller.press(keyboard.Key.enter)
                self.controller.release(keyboard.Key.enter)
            else:
                self.controller.press(ch)
                self.controller.release(ch)

    def _expand(self, trigger: str, snippet: str, paste_style: str, return_press: bool):
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

        for _ in range(chars_before_cursor):
            self.controller.press(keyboard.Key.backspace)
            self.controller.release(keyboard.Key.backspace)

        for _ in range(chars_after_cursor):
            self.controller.press(keyboard.Key.delete)
            self.controller.release(keyboard.Key.delete)

        if paste_style == "Clipboard":
            self._expand_clipboard(snippet)
        else:
            self._expand_keystrokes(snippet)

        if return_press:
            self.controller.press(keyboard.Key.enter)
            self.controller.release(keyboard.Key.enter) 

    def process_snippet_text(self, text: str, depth: int = 0, seen=None) -> str:
        """Replace placeholders and nested snippet references with loop protection."""
        if seen is None:
            seen = set()

        if depth > 5:  # configurable max depth
            logger.warning("Max snippet recursion depth reached.")
            return text

        # --- Dynamic placeholders ---
        now = datetime.datetime.now()
        replacements = {
            "{date}": now.strftime("%Y-%m-%d"),
            "{time}": now.strftime("%H:%M"),
            "{datetime}": now.strftime("%Y-%m-%d %H:%M"),
            "{location}": "Unknown Location",
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
                replacement = f"{{/{trigger}}}"

            result.append(replacement)
            last_idx = match.end()

        result.append(text[last_idx:])
        return "".join(result)

    # ---- Start/Stop Functions -----
    def start(self):
        self.listener.start()

    def stop(self):
        self.listener.stop()

    def pause(self):
        self.disabled = True
        self.clear_buffer()

    def resume(self):
        self.disabled = False

import logging
import platform
import pyperclip
from pynput import keyboard
from .config_utils import ConfigLoader

logger = logging.getLogger(__name__)

class SnippetExpander():
    def __init__(self, config_loader: ConfigLoader, parent):
        self.config = config_loader
        self.parent = parent

        self.trigger_prefixs = self.retrieve_trigger_chars(self.config.snippets)
        print(self.trigger_prefixs)
        self.buffer = ""
        self.cursor_pos = 0  # Cursor position in the buffer
        self.max_trigger_len = 255
        self.trigger_flag = False   # Used to track if we are within a snippet trigger sequence

        self.listener = keyboard.Listener(on_press=self._on_key_press)
        self.controller = keyboard.Controller()
        self._paste_mod = keyboard.Key.cmd if platform.system() == "Darwin" else keyboard.Key.ctrl

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
        if key == keyboard.Key.left:
            if self.cursor_pos > 0:
                self.cursor_pos -= 1
            return
        elif key == keyboard.Key.right:
            if self.cursor_pos < len(self.buffer):
                self.cursor_pos += 1
            return
        elif key == keyboard.Key.backspace:
            if self.cursor_pos > 0:
                self.buffer = self.buffer[:self.cursor_pos - 1] + self.buffer[self.cursor_pos:]
                self.cursor_pos -= 1
            return
        elif key == keyboard.Key.delete:
            if self.cursor_pos < len(self.buffer):
                self.buffer = self.buffer[:self.cursor_pos] + self.buffer[self.cursor_pos + 1:]
            return
        elif hasattr(key, 'char') and key.char:
            char = key.char
            # If space or newline, clear buffer
            if char in ["", " ", "\n"]:
                logger.debug("Null character or space detected.")
                self.clear_buffer()
                return
            
            # Trigger mode detection
            if not self.trigger_flag:
                if char in self.trigger_prefixs:
                    logger.debug(f"Trigger prefix '{char}' detected. Starting buffer.")
                    self.trigger_flag = True
                else:
                    logger.debug(f"Non-trigger character '{char}' while outside trigger. Ignoring.")
                    self.clear_buffer()
                    return
                
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

            for snippet in self.config.snippets:
                trigger = snippet["trigger"]
                enabled = snippet["enabled"]

                if not enabled:
                    continue

                if self.buffer.endswith(trigger):
                    logger.info(f"Trigger detected: {trigger}")
                    snippet_text = snippet["snippet"]
                    style = snippet.get("paste_style", "Keystroke")
                    self._expand(trigger, snippet_text, style)
                    self.clear_buffer()
                    break
        else:
            logger.debug(f"Unhandled special key: {key}")

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

    def _expand(self, trigger: str, snippet: str, paste_style: str):
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

    def start(self):
        logging.info("Starting keyboard listener...")
        self.listener.start()

    def stop(self):
        self.listener.stop()

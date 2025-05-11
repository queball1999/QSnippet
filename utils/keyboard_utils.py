import logging
import platform
import pyperclip
import time
from pynput import keyboard
from .config_utils import ConfigLoader

logger = logging.getLogger(__name__)

class SnippetExpander():
    """
    Listens for triggers and expands via keystroke or clipboard+paste.
    """
    def __init__(self, config_loader: ConfigLoader, parent):
        self.config = config_loader
        self.parent = parent

        self.idle_clear_secs = 10
        self.buffer = ""
        self.last_key_time = time.time()
        
        # This sets the max trigger length. Also determines how long buffer is.
        # Using 255 for 1 byte
        self.max_trigger_len = 255

        self.listener = keyboard.Listener(on_press=self._on_key_press)
        self.controller = keyboard.Controller()
        # detect which modifier to use for paste
        self._paste_mod = keyboard.Key.cmd if platform.system() == "Darwin" else keyboard.Key.ctrl

    def _on_key_press(self, key):
        try:
            char = key.char
        except AttributeError:
            logger.debug("Could not determine key. Clearing buffer!")
            self.buffer = ""
            return

        if char in ["", " ", "\n", None]: # Clear buffer and skip characters
            logger.debug("Null character or space detected. Clearing buffer!")
            self.buffer = ""
            return
        
        # Commenting out 05.11.25
        """now = time.time()
        if now - self.last_key_time > self.idle_clear_secs:  # If we’ve been idle too long, clear buffer
            logging.debug("Idle timeout, clearing buffer.")
            self.buffer = ""
        

        self.last_key_time = now
        """

        # Shifting buffer to keep within max length
        self.buffer += char
        if len(self.buffer) > self.max_trigger_len:
            self.buffer = self.buffer[-self.max_trigger_len:]

        # Check for snippet
        for snippet in self.config.snippets:
            trigger = snippet["trigger"]
            enabled = snippet["enabled"]

            if not enabled:
                break
                  
            if self.buffer.endswith(trigger):
                logging.info(f"Trigger detected: {trigger}")
                snippet_text = snippet["snippet"]
                style = snippet.get("paste_style", "Keystroke")
                self._expand(trigger, snippet_text, style)
                self.buffer = ""
                logger.debug("Trigger detected. Clearing buffer!")
                break
        return

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
        # Erase the trigger
        for _ in trigger:
            self.controller.press(keyboard.Key.backspace)
            self.controller.release(keyboard.Key.backspace)

        # Expand accordingly
        if paste_style == "Clipboard":
            self._expand_clipboard(snippet)
        else:
            self._expand_keystrokes(snippet)
            
    def start(self):
        logging.info("Starting keyboard listener...")
        self.listener.start()

    def stop(self):
        self.listener.stop()
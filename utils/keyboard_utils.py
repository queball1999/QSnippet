import logging
import time
from pynput import keyboard
from .config_utils import ConfigLoader

class SnippetExpander:
    """
    Listens to keyboard, detects triggers, and expands snippets.
    """
    def __init__(self, config_loader: ConfigLoader):
        self.config = config_loader
        self.buffer = ''
        self.max_trigger_len = max((len(k) for k in self.config.snippets), default=0)
        self.listener = keyboard.Listener(on_press=self._on_key_press)

    def _on_key_press(self, key):
        try:
            char = key.char
        except AttributeError:
            char = None

        if char:
            self.buffer += char
            if len(self.buffer) > self.max_trigger_len:
                self.buffer = self.buffer[-self.max_trigger_len:]

            for trigger, snippet in self.config.snippets.items():
                if self.buffer.endswith(trigger):
                    logging.info(f"Trigger detected: {trigger}")
                    self._expand(trigger, snippet)
                    self.buffer = ''
                    break
        else:
            self.buffer = ''

    def _expand(self, trigger: str, snippet: str):
        """Erase trigger text and type the snippet."""
        controller = keyboard.Controller()
        for _ in trigger:
            controller.press(keyboard.Key.backspace)
            controller.release(keyboard.Key.backspace)

        for index, ch in enumerate(snippet):
            if ch == '\n' and index != len(snippet):
                controller.press(keyboard.Key.enter)
                controller.release(keyboard.Key.enter)
            else:
                controller.press(ch)
                controller.release(ch)

    def start(self):
        logging.info("Starting keyboard listener...")
        self.listener.start()

    def stop(self):
        self.listener.stop()
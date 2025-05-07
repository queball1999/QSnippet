import os
import yaml
import logging
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

class ConfigLoader:
    """
    Loads and watches the YAML config file for snippet definitions.
    """
    def __init__(self, config_path: str):
        self.config_path = config_path
        self.snippets = {}
        self._load_config()
        self._start_watcher()

    def _load_config(self):
        """Load snippets from YAML file."""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
            self.snippets = data.get('snippets', {}) or {}
            logging.info(f"Loaded {len(self.snippets)} snippets.")
        except Exception as e:
            logging.error(f"Failed to load config: {e}")

    def _start_watcher(self):
        """Watch the config file for changes."""
        class Handler(FileSystemEventHandler):
            def __init__(self, outer):
                self.outer = outer

            def on_modified(self, event):
                if os.path.abspath(event.src_path) == os.path.abspath(self.outer.config_path):
                    logging.info("Config file changed. Reloading...")
                    self.outer._load_config()

        self._observer = Observer()
        directory = os.path.dirname(os.path.abspath(self.config_path)) or '.'
        event_handler = Handler(self)
        self._observer.schedule(event_handler, directory, recursive=False)
        self._observer.daemon = True
        self._observer.start()

    def stop(self):
        """Stop the file watcher."""
        self._observer.stop()
        self._observer.join()
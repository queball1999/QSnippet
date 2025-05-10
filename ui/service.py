import logging
import time
from threading import Thread, Event

from PySide6.QtWidgets import QApplication, QMessageBox

from utils.config_utils import ConfigLoader
from utils.keyboard_utils import SnippetExpander
from utils.file_utils import FileUtils


class SnippetService:
    """Background service that loads snippets and listens for triggers."""

    def __init__(self, config_path: str):
        # Set up logging
        paths = FileUtils.get_default_paths()
        log_file = paths['log_dir'] / 'qsnippet_service.log'
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s %(levelname)s: %(message)s',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler()
            ]
        )
        logging.info(f"Initializing SnippetService with config: {config_path}")

        # Core components
        self.loader   = ConfigLoader(config_path)
        self.expander = SnippetExpander(config_loader=self.loader, parent=self)

        # Thread control
        self._thread   = None
        self._stop_evt = Event()

    def _run_loop(self):
        """Monitor thread: sleep until stop requested, then clean up."""
        logging.info("SnippetService monitor thread running...")
        while not self._stop_evt.is_set():
            time.sleep(1)

        logging.info("SnippetService monitor shutting down…")
        self.expander.stop()
        self.loader.stop()

    def start(self):
        """Start the expander (once) and launch the monitor thread."""
        if self._thread and self._thread.is_alive():
            logging.info("SnippetService already running.")
            return

        # Kick off the expander's listener thread exactly once
        try:
            self.expander.start()
            logging.info("SnippetExpander started.")
        except RuntimeError:
            logging.warning("SnippetExpander was already started; skipping.")

        # Now spawn our own thread just to wait for stop requests
        self._stop_evt.clear()
        self._thread = Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        logging.info("SnippetService monitor thread started.")

    def stop(self):
        """Signal the service to stop and wait for thread to join."""
        if not self._thread:
            return

        logging.info("Stopping SnippetService…")
        self._stop_evt.set()
        self._thread.join(timeout=5)
        logging.info("SnippetService stopped.")

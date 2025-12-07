import logging
import time
from threading import Thread, Event
# from utils.config_utils import SnippetsLoader
from utils.keyboard_utils import SnippetExpander
from utils.file_utils import FileUtils
from utils.snippet_db import SnippetDB

class SnippetService():
    """Background service that loads snippets and listens for triggers."""

    def __init__(self, config_path: str):
        # Set up logging
        paths = FileUtils.get_default_paths()
        log_file = paths['log_dir'] / 'QSnippet_service.log'
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
        self.snippet_db = SnippetDB(config_path)
        self.expander = SnippetExpander(snippets_db=self.snippet_db, parent=self)

        # Thread control
        self._thread   = None
        self._stop_evt = Event()

    def refresh(self):
        """Force a reload of snippets from the database."""
        self.expander.refresh_snippets()

    def _on_snippets_updated(self, new_snippets: list):
        logging.info("Snippet definitions reloaded.")

    def _run_loop(self):
        """Monitor thread: sleep until stop requested, then clean up."""
        logging.info("SnippetService monitor thread running...")
        while not self._stop_evt.is_set():
            time.sleep(1)

        logging.info("SnippetService monitor shutting down...")
        self.expander.stop()
        # self.loader.stop()

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

        logging.info("Stopping SnippetService...")
        self._stop_evt.set()
        self._thread.join(timeout=5)
        logging.info("SnippetService stopped.")

    def pause(self):
        """ Pause the snippet service momentarily """
        logging.info("Pausing SnippetService...")
        self.expander.pause()

    def resume(self):
        """ Resume the snippet service """
        logging.info("Resuming SnippetService...")
        self.expander.resume()

    def active(self) -> bool:
        """Return True if the service monitor thread is running and not stopped."""
        return bool(self._thread and self._thread.is_alive() and not self._stop_evt.is_set())

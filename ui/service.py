import logging
import time
from threading import Thread, Event
from utils.keyboard_utils import SnippetExpander
from utils.snippet_db import SnippetDB

logger = logging.getLogger(__name__)

class SnippetService():
    """Background service that loads snippets and listens for triggers."""

    def __init__(self, config_path: str):
        logger.info("Initializing SnippetService")
        logger.debug(f"Config path: {config_path}")

        # Core components
        self.snippet_db = SnippetDB(config_path)
        self.expander = SnippetExpander(snippets_db=self.snippet_db, parent=self)

        # Thread control
        self._thread   = None
        self._stop_evt = Event()

        logger.info("SnippetService initialized successfully")

    def refresh(self):
        """Force a reload of snippets from the database."""
        logger.info("Refreshing snippets via SnippetService")
        self.expander.refresh_snippets()

    def _on_snippets_updated(self, new_snippets: list):
        logger.info("Snippet definitions reloaded")
        logger.debug(f"Updated snippet count: {len(new_snippets)}")

    def _run_loop(self):
        """Monitor thread: sleep until stop requested, then clean up."""
        logger.info("SnippetService monitor thread running...")

        while not self._stop_evt.is_set():
            time.sleep(1)

        logger.info("SnippetService monitor shutting down...")
        self.expander.stop()

    def start(self):
        """Start the expander (once) and launch the monitor thread."""
        if self._thread and self._thread.is_alive():
            logger.info("SnippetService already running.")
            return

        # Kick off the expander's listener thread exactly once
        try:
            self.expander.start()
            logger.info("SnippetExpander started.")
        except RuntimeError:
            logger.warning("SnippetExpander was already started; skipping.")

        # Now spawn our own thread just to wait for stop requests
        self._stop_evt.clear()
        self._thread = Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        logger.info("SnippetService monitor thread started.")

    def stop(self):
        """Signal the service to stop and wait for thread to join."""
        if not self._thread:
            logger.info("SnippetService stop requested, but service was not running")
            return

        logger.info("Stopping SnippetService...")
        self._stop_evt.set()
        self._thread.join(timeout=5)

        if self._thread.is_alive():
            logger.warning(
                "SnippetService monitor thread did not stop within timeout"
            )
        else:
            logger.info("SnippetService stopped successfully")

    def pause(self):
        """ Pause the snippet service momentarily """
        logger.info("Pausing SnippetService...")
        self.expander.pause()

    def resume(self):
        """ Resume the snippet service """
        logger.info("Resuming SnippetService...")
        self.expander.resume()

    def active(self) -> bool:
        """Return True if the service monitor thread is running and not stopped."""
        active = bool(
            self._thread
            and self._thread.is_alive()
            and not self._stop_evt.is_set()
        )
        logger.debug(f"SnippetService active state: {active}")
        return active

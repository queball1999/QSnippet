import logging
import time
from threading import Thread, Event
from utils.keyboard_utils import SnippetExpander
from utils.snippet_db import SnippetDB

logger = logging.getLogger(__name__)

class SnippetService():
    def __init__(self, config_path: str) -> None:
        """
        Initialize the SnippetService.

        Creates the snippet database and expander instances, and prepares
        threading primitives for background monitoring.

        Args:
            config_path (str): Path to the snippets database file.

        Returns:
            None
        """
        logger.info("Initializing SnippetService")
        logger.debug(f"Config path: {config_path}")

        # Core components
        self.snippet_db = SnippetDB(config_path)
        self.expander = SnippetExpander(snippets_db=self.snippet_db, parent=self)

        # Thread control
        self._thread   = None
        self._stop_evt = Event()

        logger.info("SnippetService initialized successfully")

    def refresh(self) -> None:
        """
        Force a reload of snippets from the database.

        Returns:
            None
        """
        logger.info("Refreshing snippets via SnippetService")
        self.expander.refresh_snippets()

    def on_snippets_updated(self, new_snippets: list):
        """
        Handle snippet update notifications.

        Args:
            new_snippets (list): The updated list of snippet definitions.

        Returns:
            None
        """
        logger.info("Snippet definitions reloaded")
        logger.debug(f"Updated snippet count: {len(new_snippets)}")

    def run_loop(self) -> None:
        """
        Run the background monitor loop.

        Sleeps until a stop request is received, then stops the snippet
        expander and exits.

        Returns:
            None
        """
        logger.info("SnippetService monitor thread running...")

        while not self._stop_evt.is_set():
            time.sleep(1)

        logger.info("SnippetService monitor shutting down...")
        self.expander.stop()

    def start(self) -> None:
        """
        Start the snippet expander and monitoring thread.

        Initializes the expander listener if not already running and
        spawns a daemon thread to monitor stop requests.

        Returns:
            None
        """
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
        self._thread = Thread(target=self.run_loop, daemon=True)
        self._thread.start()
        logger.info("SnippetService monitor thread started.")

    def stop(self) -> None:
        """
        Stop the snippet service and wait for shutdown.

        Signals the monitor thread to stop and waits for it to join.

        Returns:
            None
        """
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

    def pause(self) -> None:
        """
        Pause the snippet service temporarily.

        Returns:
            None
        """
        logger.info("Pausing SnippetService...")
        self.expander.pause()

    def resume(self) -> None:
        """
        Resume the snippet service after being paused.

        Returns:
            None
        """
        logger.info("Resuming SnippetService...")
        self.expander.resume()

    def active(self) -> bool:
        """
        Check whether the snippet service is currently active.

        Returns:
            bool: True if the monitor thread is running and not signaled
                to stop, otherwise False.
        """
        active = bool(
            self._thread
            and self._thread.is_alive()
            and not self._stop_evt.is_set()
        )
        logger.debug(f"SnippetService active state: {active}")
        return active

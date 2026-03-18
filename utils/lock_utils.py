"""
Cross-platform single instance detection using kernel-enforced locking.

- Windows: Named mutex via CreateMutex (kernel-enforced, atomic)
- Linux/macOS: fcntl.flock() (kernel-enforced, atomic, auto-released on crash)

Both approaches provide atomic mutual exclusion with automatic cleanup
on process termination, eliminating stale lock issues.

Inspired by: https://www.codegenes.net/blog/how-can-i-tell-if-another-instance-of-my-program-is-already-running/
"""
import os
import sys
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class LockFile:
    """
    Cross-platform single instance detection using kernel-enforced locking.

    - **Windows**: Uses CreateMutex for atomic, kernel-managed exclusion
    - **Linux/macOS**: Uses fcntl.flock() for atomic, kernel-enforced file locking

    Both mechanisms automatically release when the process dies or crashes,
    eliminating stale lock cleanup.
    """

    def __init__(self, lock_identifier: str):
        """
        Initialize lock manager.

        Args:
            lock_identifier (str): Platform-specific lock identifier.
                - Windows: Mutex name (e.g., "Local\\MyApp.Lock")
                - Unix: Lock file path (e.g., "/path/to/app.lock")
        """
        self.lock_identifier = lock_identifier
        self.acquired = False
        self._handle = None  # For Windows mutex
        self._lock_fd = None  # For Unix file lock

    def try_acquire(self) -> bool:
        """
        Attempt to acquire the lock using kernel-enforced mechanism.

        Returns:
            bool: True if lock acquired, False if another instance holds it
        """
        try:
            if sys.platform == "win32":
                return self.acquire_windows()
            else:
                return self.acquire_unix()
        except Exception as e:
            logger.exception(f"Error acquiring lock: {e}")
            return False

    def acquire_windows(self) -> bool:
        """
        Acquire lock on Windows using CreateMutex.

        Returns:
            bool: True if acquired, False if already held by another instance
        """
        import ctypes
        from ctypes import wintypes

        # Magic number: ERROR_ALREADY_EXISTS
        ERROR_ALREADY_EXISTS = 183

        try:
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.CreateMutexW.argtypes = (
                wintypes.LPVOID,
                wintypes.BOOL,
                wintypes.LPCWSTR,
            )
            kernel32.CreateMutexW.restype = wintypes.HANDLE

            mutex_handle = kernel32.CreateMutexW(None, False, self.lock_identifier)
            if not mutex_handle:
                raise ctypes.WinError(ctypes.get_last_error())

            error_code = ctypes.get_last_error()
            if error_code == ERROR_ALREADY_EXISTS:
                logger.debug(f"Mutex already exists: {self.lock_identifier}")
                kernel32.CloseHandle(mutex_handle)
                return False

            self._handle = mutex_handle
            self.acquired = True
            logger.debug(f"Windows mutex acquired: {self.lock_identifier}")
            return True

        except Exception as e:
            logger.exception(f"Failed to acquire Windows mutex: {e}")
            return False

    def acquire_unix(self) -> bool:
        """
        Acquire lock on Unix using fcntl.flock().

        Returns:
            bool: True if acquired, False if already held by another instance
        """
        import fcntl

        lock_path = Path(self.lock_identifier)

        try:
            # Ensure parent directory exists
            lock_path.parent.mkdir(parents=True, exist_ok=True)

            # Open lock file with restricted permissions (user only)
            lock_fd = os.open(
                str(lock_path), os.O_CREAT | os.O_WRONLY | os.O_CLOEXEC, 0o600
            )

            try:
                # Try to acquire exclusive non-blocking lock
                fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                self._lock_fd = lock_fd
                self.acquired = True
                logger.debug(f"Unix lock acquired: {lock_path}")
                return True

            except BlockingIOError:
                # Lock is held by another instance
                os.close(lock_fd)
                logger.debug(f"Lock held by another instance: {lock_path}")
                return False

        except Exception as e:
            logger.exception(f"Failed to acquire Unix lock: {e}")
            return False

    def release(self) -> None:
        """
        Release the lock.

        On Windows: Closes the mutex handle.
        On Unix: Releases fcntl lock and closes file descriptor.

        Safe to call multiple times even if lock was never acquired.
        """
        if not self.acquired:
            return

        try:
            if sys.platform == "win32":
                self.release_windows()
            else:
                self.release_unix()
            self.acquired = False
        except Exception as e:
            logger.warning(f"Error releasing lock: {e}")

    def release_windows(self) -> None:
        """Release Windows mutex."""
        if not self._handle:
            return

        try:
            import ctypes
            from ctypes import wintypes

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
            kernel32.CloseHandle.restype = wintypes.BOOL

            kernel32.CloseHandle(self._handle)
            logger.debug("Windows mutex released")
        finally:
            self._handle = None

    def release_unix(self) -> None:
        """Release Unix file lock."""
        if self._lock_fd is None:
            return

        try:
            import fcntl

            # fcntl.flock() automatically releases when fd is closed
            # but we can explicitly release it
            fcntl.flock(self._lock_fd, fcntl.LOCK_UN)
            os.close(self._lock_fd)
            logger.debug("Unix lock released")
        finally:
            self._lock_fd = None

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - always release lock."""
        self.release()

    def __del__(self):
        """Cleanup on garbage collection."""
        self.release()

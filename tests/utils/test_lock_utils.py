"""
Unit tests for kernel-enforced cross-platform single instance locking.

Tests Windows mutex and Unix fcntl.flock() implementations.
"""
import pytest
import sys
import os
from pathlib import Path
from unittest.mock import patch, MagicMock
from utils.lock_utils import LockFile


@pytest.fixture
def unix_lock_path(tmp_path):
    """Fixture: returns a path for a Unix lock file."""
    return tmp_path / "test.lock"


@pytest.fixture
def windows_mutex_name():
    """Fixture: returns a Windows mutex name."""
    return "Local\\QSnippet.Test.Lock"


class TestWindowsMutex:
    """Test Windows named mutex locking."""

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
    def testacquire_windows_mutex_success(self, windows_mutex_name):
        """Successfully acquire Windows mutex."""
        lock = LockFile(windows_mutex_name)
        assert lock.try_acquire() is True
        assert lock.acquired is True
        lock.release()

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
    def test_cannot_acquire_held_mutex(self, windows_mutex_name):
        """Cannot acquire mutex already held by another instance."""
        lock1 = LockFile(windows_mutex_name)
        lock2 = LockFile(windows_mutex_name)

        assert lock1.try_acquire() is True
        assert lock2.try_acquire() is False

        lock1.release()

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
    def test_release_windows_mutex(self, windows_mutex_name):
        """Release Windows mutex allows reacquisition."""
        lock1 = LockFile(windows_mutex_name)
        lock1.try_acquire()
        lock1.release()

        lock2 = LockFile(windows_mutex_name)
        assert lock2.try_acquire() is True
        lock2.release()

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
    def test_mutex_name_is_case_insensitive(self, windows_mutex_name):
        """Windows mutex names are case-insensitive."""
        lock1 = LockFile(windows_mutex_name)
        lock2 = LockFile(windows_mutex_name.lower())

        assert lock1.try_acquire() is True
        assert lock2.try_acquire() is False

        lock1.release()


class TestUnixFlock:
    """Test Unix fcntl.flock() locking."""

    @pytest.mark.skipif(sys.platform == "win32", reason="Unix only")
    def testacquire_unix_lock_success(self, unix_lock_path):
        """Successfully acquire Unix file lock."""
        lock = LockFile(str(unix_lock_path))
        assert lock.try_acquire() is True
        assert lock.acquired is True
        lock.release()

    @pytest.mark.skipif(sys.platform == "win32", reason="Unix only")
    def test_cannot_acquire_held_lock(self, unix_lock_path):
        """Cannot acquire lock already held by another instance."""
        lock1 = LockFile(str(unix_lock_path))
        lock2 = LockFile(str(unix_lock_path))

        assert lock1.try_acquire() is True
        assert lock2.try_acquire() is False

        lock1.release()

    @pytest.mark.skipif(sys.platform == "win32", reason="Unix only")
    def test_release_unix_lock(self, unix_lock_path):
        """Release Unix lock allows reacquisition."""
        lock1 = LockFile(str(unix_lock_path))
        lock1.try_acquire()
        lock1.release()

        lock2 = LockFile(str(unix_lock_path))
        assert lock2.try_acquire() is True
        lock2.release()

    @pytest.mark.skipif(sys.platform == "win32", reason="Unix only")
    def test_lock_file_has_restricted_permissions(self, unix_lock_path):
        """Lock file is created with user-only permissions (0o600)."""
        lock = LockFile(str(unix_lock_path))
        lock.try_acquire()

        # Check file permissions
        file_stat = os.stat(unix_lock_path)
        file_mode = file_stat.st_mode & 0o777
        assert file_mode == 0o600, f"Expected 0o600, got {oct(file_mode)}"

        lock.release()

    @pytest.mark.skipif(sys.platform == "win32", reason="Unix only")
    def test_lock_file_created_in_parent_directory(self, unix_lock_path):
        """Lock file path can be in non-existent nested directory."""
        nested_path = unix_lock_path.parent / "subdir" / "another" / "test.lock"
        lock = LockFile(str(nested_path))

        assert not nested_path.parent.exists()
        assert lock.try_acquire() is True
        assert nested_path.parent.exists()
        assert nested_path.exists()

        lock.release()


class TestLockFileCommon:
    """Test common functionality across platforms."""

    def _get_platform_lock_identifier(self, tmp_path, suffix=""):
        """Get appropriate lock identifier for current platform."""
        if sys.platform == "win32":
            return f"Local\\QSnippet.Test.Lock{suffix}"
        else:
            return str(tmp_path / f"test{suffix}.lock")

    def test_release_is_idempotent(self, tmp_path):
        """Release can be called multiple times safely."""
        lock_id = self._get_platform_lock_identifier(tmp_path)
        lock = LockFile(lock_id)
        lock.try_acquire()

        lock.release()
        lock.release()  # Should not raise
        lock.release()  # Should not raise

    def test_release_without_acquire_is_safe(self, tmp_path):
        """Release is safe to call if lock was never acquired."""
        lock_id = self._get_platform_lock_identifier(tmp_path)
        lock = LockFile(lock_id)
        lock.release()  # Should not raise
        assert lock.acquired is False

    def test_context_manager_releases_on_exit(self, tmp_path):
        """Context manager releases lock on normal exit."""
        lock_id = self._get_platform_lock_identifier(tmp_path)

        with LockFile(lock_id) as lock:
            lock.try_acquire()
            assert lock.acquired is True

        # Lock should be released after context exit
        lock2 = LockFile(lock_id)
        assert lock2.try_acquire() is True
        lock2.release()

    def test_context_manager_releases_on_exception(self, tmp_path):
        """Context manager releases lock even if exception occurs."""
        lock_id = self._get_platform_lock_identifier(tmp_path)

        try:
            with LockFile(lock_id) as lock:
                lock.try_acquire()
                assert lock.acquired is True
                raise ValueError("Test exception")
        except ValueError:
            pass

        # Lock should be released even after exception
        lock2 = LockFile(lock_id)
        assert lock2.try_acquire() is True
        lock2.release()

    def test_lock_identifier_string(self, tmp_path):
        """Lock identifier can be provided as string."""
        lock_id = self._get_platform_lock_identifier(tmp_path)
        lock = LockFile(lock_id)
        assert lock.try_acquire() is True
        lock.release()

    def test_multiple_unique_locks(self, tmp_path):
        """Multiple different locks can be acquired simultaneously."""
        lock1_id = self._get_platform_lock_identifier(tmp_path, suffix="1")
        lock2_id = self._get_platform_lock_identifier(tmp_path, suffix="2")

        lock1 = LockFile(lock1_id)
        lock2 = LockFile(lock2_id)

        assert lock1.try_acquire() is True
        assert lock2.try_acquire() is True

        lock1.release()
        lock2.release()


class TestLockFileErrorHandling:
    """Test error handling and edge cases."""

    def test_invalid_lock_identifier_windows(self):
        """Windows handles invalid mutex names gracefully."""
        if sys.platform != "win32":
            pytest.skip("Windows only")

        # Very long mutex name (>256 chars) should fail gracefully
        long_name = "Local\\" + "A" * 300
        lock = LockFile(long_name)

        # Should not crash, just return False
        result = lock.try_acquire()
        assert isinstance(result, bool)

    def test_permission_error_unix(self, tmp_path):
        """Unix handles permission errors when creating lock file."""
        if sys.platform == "win32":
            pytest.skip("Unix only")

        # Create a read-only directory
        readonly_dir = tmp_path / "readonly"
        readonly_dir.mkdir()
        lock_path = readonly_dir / "test.lock"

        # Make directory read-only (no write permission)
        os.chmod(readonly_dir, 0o444)

        try:
            lock = LockFile(str(lock_path))
            # Should handle permission error gracefully
            result = lock.try_acquire()
            assert result is False
        finally:
            # Restore permissions for cleanup
            os.chmod(readonly_dir, 0o755)


class TestLockFileDocstring:
    """Test that lock file meets documented requirements."""

    def test_kernel_enforced_windows(self):
        """Windows implementation uses CreateMutex (kernel-enforced)."""
        import inspect

        source = inspect.getsource(LockFile.acquire_windows)
        assert "CreateMutexW" in source
        assert "kernel32" in source

    def test_kernel_enforced_unix(self):
        """Unix implementation uses fcntl.flock (kernel-enforced)."""
        import inspect

        source = inspect.getsource(LockFile.acquire_unix)
        assert "fcntl.flock" in source
        assert "LOCK_EX" in source

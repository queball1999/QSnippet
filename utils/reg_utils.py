import logging
import sys
import os

logger = logging.getLogger(__name__)

if sys.platform == "win32":
    import winreg
else:
    winreg = None  # dummy placeholder

logger = logging.getLogger(__name__)



class RegUtils:
    @staticmethod
    def add_to_run_key(app_exe_path: str, entry_name: str = "QSnippet") -> None:
        """
        Add the application to the current user's Windows Run registry key.

        Creates or updates an entry under
        HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run
        so the application starts automatically when the user logs in.

        Args:
            app_exe_path (str): Full path to the application executable.
            entry_name (str): Registry entry name.

        Returns:
            None
        """
        if winreg is None or sys.platform != "win32":
            logger.warning("Registry functions are only available on Windows.")
            return
        
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as run_key:
                value = f"\"{app_exe_path}\""
                winreg.SetValueEx(run_key, entry_name, 0, winreg.REG_SZ, value)
                logger.info(f"Added registry key: {entry_name}")
        except Exception as e:
            logger.error(f"Failed to add registry key {entry_name}: {e}")

    @staticmethod
    def remove_from_run_key(entry_name: str = "QSnippet") -> None:
        """
        Remove the application from the current user's Windows Run registry key.

        Deletes the specified entry from
        HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run
        to disable automatic startup at login.

        Args:
            entry_name (str): Registry entry name.

        Returns:
            None
        """
        if winreg is None or sys.platform != "win32":
            logger.warning("Registry functions are only available on Windows.")
            return
        
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as run_key:
                winreg.DeleteValue(run_key, entry_name)
                logger.info(f"Removed registry key: {entry_name}")
        except FileNotFoundError:
            logger.info(f"Registry key {entry_name} not found (nothing to remove).")
        except Exception as e:
            logger.error(f"Failed to remove registry key {entry_name}: {e}")

    @staticmethod
    def is_in_run_key(entry_name: str = "QSnippet") -> bool:
        """
        Check whether the application is registered in the Windows Run key.

        Args:
            entry_name (str): Registry entry name.

        Returns:
            bool: True if the entry exists in the Run key, otherwise False.
        """
        if winreg is None or sys.platform != "win32":
            logger.warning("Registry functions are only available on Windows.")
            return False
        
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_READ) as run_key:
                winreg.QueryValueEx(run_key, entry_name)
                return True
        except FileNotFoundError:
            return False
        except Exception as e:
            logger.warning(f"Error checking registry key {entry_name}: {e}")
            return False

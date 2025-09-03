import logging
import platform

logger = logging.getLogger(__name__)

if platform.system() == "Windows":
    import winreg
else:
    winreg = None  # dummy placeholder

logger = logging.getLogger(__name__)


class RegUtils:
    @staticmethod
    def add_to_run_key(app_exe_path: str, entry_name: str = "QSnippet"):
        if winreg is None:
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
    def remove_from_run_key(entry_name: str = "QSnippet"):
        if winreg is None:
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
        if winreg is None:
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

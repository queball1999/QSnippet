import os
import platform
import logging
import yaml
from pathlib import Path

class FileUtils:
    """
    Utility class for common file and directory operations.
    """
    @staticmethod
    def ensure_dir(path: Path):
        """Create directory if it doesn"t exist."""
        try:
            path.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logging.critical(f"Could not create directory {path}: {e}")
            raise

    @staticmethod
    def read_yaml(path: Path) -> dict:
        """Read a YAML file and return its contents as a dict."""
        try:
            with path.open("r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            logging.error(f"Failed to read YAML file {path}: {e}")
            return {}

    @staticmethod
    def write_yaml(path: Path, data: dict):
        """Write a dict to a YAML file atomically."""
        temp_path = path.with_suffix(path.suffix + ".tmp")
        try:
            with temp_path.open("w", encoding="utf-8") as f:
                yaml.safe_dump(data, f)
            temp_path.replace(path)
        except Exception as e:
            logging.error(f"Failed to write YAML file {path}: {e}")
            raise

    @staticmethod
    def file_exists(path: Path) -> bool:
        """Check whether a file exists."""
        return path.is_file()
    
    @staticmethod
    def get_default_paths():
        """
        Retrieve default directories based on the operating system.
        """
        system = platform.system()
        user_home = Path.home()

        if system == "Windows":
            documents = Path(os.environ.get("USERPROFILE", user_home)) / "Documents" / "QSnippet"
            log_dir = Path(os.getenv("ProgramData", "C:/ProgramData")) / "QSnippet" / "logs"
        elif system == "Darwin":
            documents = user_home / "Documents" / "QSnippet"
            log_dir = user_home / "Library" / "Logs" / "QSnippet"
        else:
            documents = user_home / "Documents" / "QSnippet"
            log_dir = Path("/var/log/QSnippet")

        # Ensure directories exist
        FileUtils.ensure_dir(documents)
        FileUtils.ensure_dir(log_dir)

        # Get current working directory
        cwd = Path.cwd()

        return {
            "documents_dir": documents,
            "log_dir": log_dir,
            "working_dir": cwd
        }
import os
import platform
import logging
import yaml
import sys
from datetime import datetime
from pathlib import Path
from PySide6.QtWidgets import QFileDialog, QMessageBox

logger = logging.getLogger(__name__)


class FileUtils:
    """
    Utility class for common file and directory operations.
    """
    @staticmethod
    def ensure_dir(path: Path):
        """Create directory if it doesn"t exist."""
        logger.debug("Ensuring directory exists: %s", path)

        try:
            path.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logging.critical(f"Could not create directory {path}: {e}")
            raise

    @staticmethod
    def read_yaml(path: Path) -> dict:
        """Read a YAML file and return its contents as a dict."""
        logger.debug("Reading YAML file: %s", path)

        try:
            with path.open("r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            logger.debug("YAML file loaded successfully: %s", path)
            return data
        except Exception as e:
            logging.error(f"Failed to read YAML file {path}: {e}")
            return {}

    @staticmethod
    def write_yaml(path: Path, data: dict):
        """Write a dict to a YAML file atomically."""
        logger.debug("Writing YAML file: %s", path)
        temp_path = path.with_suffix(path.suffix + ".tmp")
        try:
            with temp_path.open("w", encoding="utf-8") as f:
                yaml.safe_dump(data, f)
            temp_path.replace(path)
            logger.info("YAML file written successfully: %s", path)
        except Exception as e:
            logging.error(f"Failed to write YAML file {path}: {e}")
            raise

    @staticmethod
    def export_snippets_yaml(path: Path, snippets: list[dict]):
        """Export snippets to a YAML file."""
        logger.debug("Exporting %d snippets to %s", len(snippets), path)
        try:
            data = {"snippets": snippets}
            FileUtils.write_yaml(path, data)
            logger.info("Exported %d snippets to %s", len(snippets), path)
        except Exception as e:
            logging.error(f"Failed to export snippets to YAML: {e}")
            raise

    @staticmethod
    def import_snippets_yaml(path: Path) -> list[dict]:
        """Import snippets from a YAML file and return as a list of dicts."""
        logger.debug("Importing snippets from YAML: %s", path)

        try:
            data = FileUtils.read_yaml(path)
            snippets = data.get("snippets", [])
            if not isinstance(snippets, list):
                raise ValueError("Invalid YAML format: 'snippets' must be a list.")
            
            logger.info("Imported %d snippets from %s", len(snippets), path)
            return snippets
        except Exception as e:
            logging.error(f"Failed to import snippets from YAML: {e}")
            raise

    @staticmethod
    def import_snippets_with_dialog(parent, db):
        """Prompt user to import snippets from YAML."""
        logger.debug("Opening import snippets dialog")

        path, _ = QFileDialog.getOpenFileName(
            parent,
            "Import Snippets from YAML",
            str(Path.home()),
            "YAML Files (*.yaml *.yml)"
        )
        if not path:
            logger.debug("Import cancelled by user")
            return 0

        snippets = FileUtils.import_snippets_yaml(Path(path))
        new_count = 0
        updated_count = 0

        for entry in snippets:
            is_new = db.insert_snippet(entry)
            if is_new:
                new_count += 1
            else:
                updated_count += 1

        logger.info(
            "Snippet import complete: %d new, %d updated",
            new_count,
            updated_count,
        )

        QMessageBox.information(
            parent,
            "Import Complete",
            f"Imported {new_count} new snippets.\nUpdated {updated_count} existing snippets."
        )
        return new_count + updated_count


    @staticmethod
    def export_snippets_with_dialog(parent, db):
        """Prompt user to export snippets to YAML."""
        date = datetime.now().date()
        default_name = f"qsnippets-export-{date}.yaml"

        logger.debug("Opening export snippets dialog")
    
        path, _ = QFileDialog.getSaveFileName(
            parent,
            "Export Snippets to YAML",
            str(Path.home() / default_name),
            "YAML Files (*.yaml *.yml)",
        )

        if not path:
            logger.debug("Export cancelled by user")
            return 0

        snippets = db.get_all_snippets()
        FileUtils.export_snippets_yaml(Path(path), snippets)

        QMessageBox.information(
            parent,
            "Export Complete",
            f"Exported {len(snippets)} snippets.",
        )

        logger.info("Snippet export completed: %s", path)
        return len(snippets)

    @staticmethod
    def file_exists(path: Path) -> bool:
        """Check whether a file exists."""
        return path.is_file()
    
    @staticmethod
    def get_default_paths():
        """
        Retrieve default directories based on the operating system.
        """
        logger.debug("Resolving default OS paths")

        try:
            system = platform.system()
            user_home = Path.home()

            if system == "Windows":
                app_data = Path(os.path.join(os.environ["LOCALAPPDATA"], "QSnippet"))
                documents = Path(os.path.join(os.environ["USERPROFILE"], "Documents", "QSnippet"))
                log_dir = Path(os.getenv("ProgramData", "C:/ProgramData")) / "QSnippet" / "logs"
            elif system == "Darwin":
                app_data = user_home / "Library" / "Application Support" / "QSnippet"
                documents = user_home / "Documents" / "QSnippet"
                log_dir = user_home / "Library" / "Logs" / "QSnippet"
            else:
                app_data = Path(os.getenv("XDG_DATA_HOME", user_home / ".local" / "share")) / "QSnippet"
                documents = user_home / "Documents" / "QSnippet"
                log_dir = Path("/var/log/QSnippet")

            # Ensure directories exist
            FileUtils.ensure_dir(documents)
            FileUtils.ensure_dir(log_dir)

            # Detect runtime working directory
            if hasattr(sys, "_MEIPASS"):
                # Running inside a PyInstaller bundle
                resource_dir = Path(sys._MEIPASS)
                logger.debug("Detected PyInstaller runtime")
            else:
                # Running from source / dev
                resource_dir = Path.cwd()

            return {
                "app_data": app_data,
                "documents": documents,
                "log_dir": log_dir,
                "working_dir": Path.cwd(),
                "resource_dir": resource_dir
            }
        except Exception as e:
            logging.critical("Could not retrieve OS specific directories!")
            raise ValueError("Could not retrieve OS specific directories! Please contact application vendor.")

    @staticmethod
    def merge_dict(default: dict, user: dict) -> dict:
        """
        Recursively merge default values into user values.
        User values treated as source of truth. 
        Only Missing keys are added.
        """
        if not isinstance(default, dict):
            return user

        merged = dict(user)

        for key, default_val in default.items():
            if key not in merged:
                merged[key] = default_val
            else:
                user_val = merged[key]
                if isinstance(default_val, dict) and isinstance(user_val, dict):
                    merged[key] = FileUtils.merge_dict(default_val, user_val)

        return merged

    @staticmethod
    def create_config_file(default_dir: Path, user_path: Path, parent=None):
        """
        Create the user config.yaml by copying from the default config directory.
        Does NOT overwrite existing user config.
        """
        if user_path.exists():
            logger.debug("Config file already exists, skipping: %s", user_path)
            return

        source = default_dir / "config.yaml"

        if not source.exists():
            logger.critical("Default config file missing: %s", source)

            """ QMessageBox.critical(
                parent,
                "Configuration Error",
                "The default configuration file could not be found.\n\n"
                "Please reinstall the application or report an issue."
            ) """
            raise FileNotFoundError(f"Missing default config file: {source}")

        try:
            FileUtils.ensure_dir(user_path.parent)
            user_path.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
            logger.info("Copied default config to user location: %s", user_path)
        except Exception as e:
            logger.critical("Failed to copy config file: %s", e)
            """ QMessageBox.critical(
                parent,
                "Configuration Error",
                f"Failed to create configuration file.\n\n{e}"
            ) """
            raise RuntimeError(f"Failed to create config file: {e}")

    @staticmethod
    def create_settings_file(default_dir: Path, user_path: Path, parent=None):
        """
        Create the user settings.yaml by copying from the default config directory.
        Does NOT overwrite existing user settings.
        """
        if user_path.exists():
            logger.debug("Settings file already exists, skipping: %s", user_path)
            return

        source = default_dir / "settings.yaml"

        if not source.exists():
            logger.critical("Default settings file missing: %s", source)

            """ QMessageBox.critical(
                parent,
                "Configuration Error",
                "The default settings file could not be found.\n\n"
                "Please reinstall the application or report an issue."
            ) """
            raise FileNotFoundError(f"Missing default settings file: {source}")

        try:
            FileUtils.ensure_dir(user_path.parent)
            user_path.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
            logger.info("Copied default settings to user location: %s", user_path)
        except Exception as e:
            logger.critical("Failed to copy settings file: %s", e)
            """ QMessageBox.critical(
                parent,
                "Configuration Error",
                f"Failed to create settings file.\n\n{e}"
            ) """
            raise RuntimeError(f"Failed to create settings file: {e}")
    
    @staticmethod
    def create_snippets_db_file(path):
        if path.exists():
            logging.debug(f"DB already exists: {path}, skipping creation.")
            return
        
        # This import statement is required here
        # This prevents circular import and allows access when necessary.
        # Do NOT remove.
        from .snippet_db import SnippetDB
        logger.info("Creating snippets database: %s", path)
        db = SnippetDB(path)
        db._create_table()

    @staticmethod
    def load_and_merge_yaml(default_path: Path, user_path: Path) -> dict:
        """
        Load default YAML and merge it into the user YAML.
        Writes merged result back to user_path.
        User values are treated as the source of truth.
        """
        logger.debug("Loading default YAML: %s", default_path)
        default_data = FileUtils.read_yaml(default_path)

        if user_path.exists():
            logger.debug("Loading user YAML: %s", user_path)
            user_data = FileUtils.read_yaml(user_path)
        else:
            logger.info("User YAML missing, creating new: %s", user_path)
            user_data = {}

        merged = FileUtils.merge_dict(default_data, user_data)

        # Only write if file missing or structure changed
        if not user_path.exists() or merged != user_data:
            logger.info("Writing merged YAML to: %s", user_path)
            FileUtils.ensure_dir(user_path.parent)
            FileUtils.write_yaml(user_path, merged)
        else:
            logger.debug("User YAML already up to date: %s", user_path)

        return merged
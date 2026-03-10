import os
import platform
import logging
import yaml
import sys
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class FileUtils:
    def resolve_images_path(self) -> Path:
        """
        Resolve and return the valid images directory path.

        Searches for an images directory in the resource directory and
        working directory, in that order. Validates that all required
        image files are present before returning the path.

        Returns:
            Path: The resolved images directory path.

        Raises:
            FileNotFoundError: If no valid images directory containing all
                required image files is found.
        """
        candidates = [
            Path(self.resource_dir) / "images",
            Path(self.working_dir) / "images",
        ]

        for path in candidates:
            if not path.exists() or not path.is_dir():
                continue

            missing = [
                img for img in self.REQUIRED_IMAGE_FILES
                if not (path / img).exists()
            ]

            if not missing:
                logger.info(f"Using images directory: {path}")
                return path

            logger.warning(
                "Images directory found but missing files in %s: %s",
                path,
                ", ".join(missing),
            )

        raise FileNotFoundError(
            "No valid images directory found. "
            "Checked resource_dir and working_dir."
            "\n\n"
            f"Location: {path}"
            ""
        )

    # Utility class for common file and directory operations.
    @staticmethod
    def ensure_dir(path: Path) -> None:
        """
        Ensure that a directory exists.

        Creates the specified directory and any necessary parent directories
        if they do not already exist.

        Args:
            path (Path): The directory path to create.

        Returns:
            None

        Raises:
            Exception: If the directory cannot be created.
        """
        logger.debug("Ensuring directory exists: %s", path)

        try:
            path.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logging.critical(f"Could not create directory {path}: {e}")
            raise

    @staticmethod
    def read_yaml(path: Path) -> dict:
        """
        Read a YAML file and return its contents.

        Args:
            path (Path): The path to the YAML file.

        Returns:
            dict: The parsed YAML contents as a dictionary. Returns an empty
                dictionary if loading fails.
        """
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
    def write_yaml(path: Path, data: dict) -> None:
        """
        Write a dictionary to a YAML file atomically.

        Writes data to a temporary file and replaces the target file upon
        successful write to prevent corruption.

        Args:
            path (Path): The destination YAML file path.
            data (dict): The dictionary to serialize and write.

        Returns:
            None

        Raises:
            Exception: If writing to the file fails.
        """
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
    def export_snippets_yaml(path: Path, snippets: list[dict]) -> None:
        """
        Export snippets to a YAML file.

        Args:
            path (Path): The destination file path.
            snippets (list[dict]): A list of snippet dictionaries to export.

        Returns:
            None

        Raises:
            Exception: If exporting fails.
        """
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
        """
        Import snippets from a YAML file.

        Args:
            path (Path): The source YAML file path.

        Returns:
            list[dict]: A list of snippet dictionaries loaded from the file.

        Raises:
            ValueError: If the YAML format is invalid.
            Exception: If reading or parsing fails.
        """
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
    def import_snippets_with_dialog(parent, db) -> int:
        """
        Prompt the user to import snippets from a YAML file.

        Opens a file dialog to select a YAML file, imports snippets into the
        database, and displays a summary of imported and updated entries.

        Args:
            parent (Any): The parent widget for dialog windows.
            db (Any): The database instance used to insert snippets.

        Returns:
            int: The total number of snippets imported or updated.

        Raises:
            Exception: If importing snippets fails.
        """
        from PySide6.QtWidgets import QFileDialog, QMessageBox

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
    def export_snippets_with_dialog(parent, db) -> int:
        """
        Prompt the user to export snippets to a YAML file.

        Opens a save file dialog, retrieves all snippets from the database,
        writes them to a YAML file, and displays a completion message.

        Args:
            parent (Any): The parent widget for dialog windows.
            db (Any): The database instance used to retrieve snippets.

        Returns:
            int: The number of snippets exported.

        Raises:
            Exception: If exporting snippets fails.
        """
        from PySide6.QtWidgets import QFileDialog, QMessageBox

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
        """
        Check whether a file exists.

        Args:
            path (Path): The file path to check.

        Returns:
            bool: True if the file exists and is a file, otherwise False.
        """
        return path.is_file()
    
    @staticmethod
    def get_default_paths() -> dict:
        """
        Retrieve default application directories based on the operating system.

        Determines appropriate paths for application data, documents, logs,
        working directory, and resource directory depending on the runtime
        environment.

        Returns:
            dict: A dictionary containing resolved Path objects for default
                directories.

        Raises:
            ValueError: If OS-specific directories cannot be determined.
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
                "working_dir": FileUtils.get_executable_dir(),
                "resource_dir": resource_dir
            }
        except Exception as e:
            logging.critical("Could not retrieve OS specific directories!")
            raise ValueError("Could not retrieve OS specific directories! Please contact application vendor.")
    
    @staticmethod
    def get_executable_dir() -> Path:
        """
        Return the application root directory.

        Determines the directory of the executable when running as a bundled
        application, or the main entry point directory when running from source.

        Returns:
            Path: The resolved application root directory.
        """
        if getattr(sys, "frozen", False):
            # PyInstaller executable
            return Path(sys.executable).resolve().parent

        # Running from source: anchor to the main entrypoint
        main_file = sys.modules.get("__main__").__file__
        return Path(main_file).resolve().parent

    @staticmethod
    def merge_dict(default: dict, user: dict) -> dict:
        """
        Recursively merge default values into user-provided values.

        User values are treated as the source of truth. Only missing keys
        from the default dictionary are added to the user dictionary.

        Args:
            default (dict): The default configuration dictionary.
            user (dict): The user configuration dictionary.

        Returns:
            dict: The merged dictionary.
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
    def create_config_file(default_dir: Path, user_path: Path, parent=None) -> None:
        """
        Create a user configuration file from the default template.

        Copies the default config.yaml file to the user location if it does
        not already exist.

        Args:
            default_dir (Path): Directory containing the default config.yaml.
            user_path (Path): Destination path for the user config file.
            parent (Any): Optional parent widget for error dialogs.

        Returns:
            None

        Raises:
            FileNotFoundError: If the default config file is missing.
            RuntimeError: If the config file cannot be created.
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
    def create_settings_file(default_dir: Path, user_path: Path, parent=None) -> None:
        """
        Create a user settings file from the default template.

        Copies the default settings.yaml file to the user location if it does
        not already exist.

        Args:
            default_dir (Path): Directory containing the default settings.yaml.
            user_path (Path): Destination path for the user settings file.
            parent (Any): Optional parent widget for error dialogs.

        Returns:
            None

        Raises:
            FileNotFoundError: If the default settings file is missing.
            RuntimeError: If the settings file cannot be created.
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
    def create_snippets_db_file(path) -> None:
        """
        Create the snippets database file if it does not exist.

        Initializes the database and creates the required table structure.

        Args:
            path (Path): The path to the database file.

        Returns:
            None
        """
        if path.exists():
            logging.debug(f"DB already exists: {path}, skipping creation.")
            return
        
        # This import statement is required here
        # This prevents circular import and allows access when necessary.
        # Do NOT remove.
        from .snippet_db import SnippetDB
        logger.info("Creating snippets database: %s", path)
        db = SnippetDB(path)
        db.create_table()

    @staticmethod
    def load_and_merge_yaml(default_path: Path, user_path: Path) -> dict:
        """
        Load default and user YAML files and merge them.

        User values are treated as authoritative. Missing default keys are
        added to the user configuration. The merged result is written back
        to the user file if changes are detected.

        Args:
            default_path (Path): Path to the default YAML file.
            user_path (Path): Path to the user YAML file.

        Returns:
            dict: The merged configuration dictionary.
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
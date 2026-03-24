import os
import re
import platform
import logging
import yaml
import sys
import signal
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# Security constraints for import/export
MAX_IMPORT_FILE_SIZE = 50 * 1024 * 1024  # 50MB
MAX_SNIPPETS_PER_FILE = 10000  # Prevent DoS via thousands of items
MAX_FIELD_LENGTH = 10000  # Max characters per field (prevent memory bombs)
YAML_PARSE_TIMEOUT = 10  # Seconds - timeout for YAML parsing
ALLOWED_SNIPPET_FIELDS = {
    "enabled", "label", "trigger", "snippet",
    "paste_style", "return_press", "folder", "tags"
}
REQUIRED_SNIPPET_FIELDS = {"label", "trigger", "snippet"}


def validate_snippet_fields(snippet: dict) -> None:
    """
    Validate a snippet dictionary for security and type safety.

    Checks:
    - Required fields present
    - Field types correct
    - Field lengths within limits
    - No invalid boolean/string values
    
    Raises:
        ValueError: If validation fails
        TypeError: If field type is wrong
    """
    if not isinstance(snippet, dict):
        raise TypeError("Snippet must be a dictionary")

    # Check required fields
    missing = REQUIRED_SNIPPET_FIELDS - set(snippet.keys())
    if missing:
        raise ValueError(f"Snippet missing required fields: {missing}")

    # Validate string fields
    string_fields = ["trigger", "label", "snippet", "folder", "tags", "paste_style"]
    for field in string_fields:
        if field in snippet:
            if not isinstance(snippet[field], str):
                raise TypeError(f"Field '{field}' must be string, got {type(snippet[field]).__name__}")
            # Check field length
            if len(snippet[field]) > MAX_FIELD_LENGTH:
                raise ValueError(f"Field '{field}' exceeds max length ({MAX_FIELD_LENGTH})")

    # Validate boolean fields
    bool_fields = ["enabled", "return_press"]
    for field in bool_fields:
        if field in snippet and not isinstance(snippet[field], bool):
            raise TypeError(f"Field '{field}' must be boolean, got {type(snippet[field]).__name__}")

    # Validate trigger is not empty
    if not snippet["trigger"].strip():
        raise ValueError("Trigger cannot be empty or whitespace only")

    # Reject control characters in all text fields (import path)
    control_char_re = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
    for field in string_fields:
        if field in snippet and control_char_re.search(snippet[field]):
            raise ValueError(f"Field '{field}' contains invalid control characters.")


def sanitize_snippet(snippet: dict) -> dict:
    """
    Remove unknown fields from snippet (whitelist approach).

    Args:
        snippet (dict): Snippet dictionary from YAML
    
    Returns:
        dict: Sanitized snippet with only allowed fields
    """
    return {k: v for k, v in snippet.items() if k in ALLOWED_SNIPPET_FIELDS}


def validate_snippets_list(data: dict) -> list:
    """
    Validate and extract snippets list from parsed YAML.

    Checks:
    - Data is a dictionary
    - 'snippets' key exists
    - 'snippets' value is a list
    - List size is reasonable

    Args:
        data (dict): Parsed YAML data
    
    Returns:
        list: Validated snippets list
    
    Raises:
        ValueError: If validation fails
    """
    if not isinstance(data, dict):
        raise ValueError("YAML content must be a dictionary")

    if "snippets" not in data:
        raise ValueError("YAML missing required 'snippets' key")

    snippets = data["snippets"]
    if not isinstance(snippets, list):
        raise ValueError("'snippets' value must be a list, got " + type(snippets).__name__)

    if len(snippets) > MAX_SNIPPETS_PER_FILE:
        raise ValueError(f"Too many snippets ({len(snippets)}). Max allowed: {MAX_SNIPPETS_PER_FILE}")

    return snippets


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

        Security checks:
        - File size limit (50MB)
        - Parsing timeout (10 seconds)
        - Safe deserialization (yaml.safe_load)

        Args:
            path (Path): The path to the YAML file.
        
        Returns:
            dict: The parsed YAML contents as a dictionary. Returns an empty
                dictionary if loading fails.
        
        Raises:
            ValueError: If file is too large
            TimeoutError: If parsing takes too long
        """
        logger.debug("Reading YAML file: %s", path)

        try:
            # Check file exists first
            if not path.exists():
                logger.warning("YAML file does not exist: %s", path)
                return {}

            # Check file size
            file_size = path.stat().st_size
            if file_size > MAX_IMPORT_FILE_SIZE:
                raise ValueError(
                    f"File too large ({file_size} bytes). "
                    f"Maximum allowed: {MAX_IMPORT_FILE_SIZE} bytes"
                )
            logger.debug("File size check passed: %d bytes", file_size)

            # Read with timeout protection
            with path.open("r", encoding="utf-8") as f:
                # Platform-specific timeout (signal only works on Unix)
                if sys.platform != "win32":
                    def _timeout_handler(signum, frame):
                        raise TimeoutError(f"YAML parsing exceeded {YAML_PARSE_TIMEOUT} second timeout")
                    signal.signal(signal.SIGALRM, _timeout_handler)
                    signal.alarm(YAML_PARSE_TIMEOUT)

                try:
                    data = yaml.safe_load(f) or {}
                finally:
                    if sys.platform != "win32":
                        signal.alarm(0)  # Cancel alarm

            logger.debug("YAML file loaded successfully: %s", path)
            return data
        except Exception as e:
            logging.error(f"Failed to read YAML file {path}: {e}")
            raise

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
            # Remove internal database IDs from exported snippets
            # IDs are auto-generated on import and should not be preserved
            clean_snippets = [
                {k: v for k, v in snippet.items() if k != "id"}
                for snippet in snippets
            ]
            data = {"snippets": clean_snippets}
            FileUtils.write_yaml(path, data)
            logger.info("Exported %d snippets to %s", len(snippets), path)
        except Exception as e:
            logging.error(f"Failed to export snippets to YAML: {e}")
            raise

    @staticmethod
    def import_snippets_yaml(path: Path) -> list[dict]:
        """
        Import snippets from a YAML file with full validation.

        Security validations:
        - File size check (50MB max)
        - Parsing timeout (10s max)
        - YAML structure validation
        - Individual snippet field validation
        - Field type/length validation
        - Unknown field stripping

        Args:
            path (Path): The source YAML file path.
        
        Returns:
            list[dict]: A list of sanitized snippet dictionaries.
        
        Raises:
            ValueError: If validation fails (size, format, field values)
            TypeError: If field types are invalid
            Exception: If reading or parsing fails
        """
        logger.debug("Importing snippets from YAML: %s", path)

        try:
            # Load with security checks (file size, timeout)
            data = FileUtils.read_yaml(path)

            # Validate structure
            snippets = validate_snippets_list(data)
            logger.debug("YAML structure validated: %d snippets", len(snippets))

            # Validate and sanitize each snippet
            validated_snippets = []
            for idx, snippet in enumerate(snippets):
                try:
                    # Validate fields
                    validate_snippet_fields(snippet)
                    # Remove unknown fields
                    sanitized = sanitize_snippet(snippet)
                    validated_snippets.append(sanitized)
                except (ValueError, TypeError) as e:
                    raise type(e)(f"Snippet #{idx + 1} validation failed: {e}") from None

            logger.info("Imported and validated %d snippets from %s", len(validated_snippets), path)
            return validated_snippets
        except Exception as e:
            logging.error(f"Failed to import snippets from YAML: {e}")
            raise

    @staticmethod
    def import_snippets_with_dialog(parent, db) -> int:
        """
        Prompt the user to import snippets from a YAML file.

        Opens a file dialog to select a YAML file, imports snippets into the
        database with full validation, and displays a summary.

        Args:
            parent (Any): The parent widget for dialog windows.
            db (Any): The database instance used to insert snippets.
        
        Returns:
            int: The total number of snippets imported or updated.
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

        try:
            # Import with full validation (file size, parsing timeout, field validation)
            snippets = FileUtils.import_snippets_yaml(Path(path))
            new_count = 0
            updated_count = 0
            error_count = 0

            for entry in snippets:
                # Strip internal database IDs to prevent ID-based conflicts
                clean_entry = {k: v for k, v in entry.items() if k != "id"}
                is_new = db.insert_snippet(clean_entry)
                if is_new is True:
                    new_count += 1
                elif is_new is False:
                    updated_count += 1
                else:
                    error_count += 1
                    logger.warning(f"Insert error for trigger: {entry.get('trigger')}")

            logger.info(
                "Snippet import complete: %d new, %d updated, %d errors",
                new_count,
                updated_count,
                error_count,
            )

            QMessageBox.information(
                parent,
                "Import Complete",
                f"Imported {new_count} new snippets.\nUpdated {updated_count} existing snippets."
            )
            return new_count + updated_count
        except (ValueError, TypeError) as e:
            logger.error(f"Import validation failed: {e}")
            QMessageBox.critical(
                parent,
                "Import Error",
                f"Invalid YAML file:\n\n{str(e)}"
            )
            return 0
        except TimeoutError as e:
            logger.error(f"Import timeout: {e}")
            QMessageBox.critical(
                parent,
                "Import Error",
                "YAML file took too long to parse. File may be corrupted or too large."
            )
            return 0
        except Exception as e:
            logger.error(f"Import failed: {e}")
            QMessageBox.critical(
                parent,
                "Import Error",
                f"Failed to import snippets:\n\n{str(e)}"
            )
            return 0


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
                log_dir = app_data / "logs"
            elif system == "Darwin":
                app_data = user_home / "Library" / "Application Support" / "QSnippet"
                documents = user_home / "Documents" / "QSnippet"
                log_dir = app_data / "logs"
            else:
                app_data = Path(os.getenv("XDG_DATA_HOME", user_home / ".local" / "share")) / "QSnippet"
                documents = user_home / "Documents" / "QSnippet"
                log_dir = app_data / "logs"

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
    def is_setting_leaf(d: dict) -> bool:
        """True for settings leaf nodes that carry both 'value' and 'default' keys."""
        return "value" in d and "default" in d

    # Settings schema validation - type-check setting values
    # after merge and reset invalid ones to their defaults.

    SETTING_TYPE_CHECKS = {
        "string":  lambda v: isinstance(v, str),
        "integer": lambda v: isinstance(v, (int, str)) and str(v).lstrip("-").isdigit(),
        "boolean": lambda v: isinstance(v, bool),
        "float":   lambda v: isinstance(v, (int, float)),
    }

    @staticmethod
    def validate_setting_leaf(path: str, leaf: dict) -> bool:
        """
        Check that a settings leaf node's value matches its declared type.

        Logs a warning and resets to the default value when a mismatch is
        detected. Does NOT raise, preserving graceful-degradation behavior.

        Args:
            path (str): Dot-separated key path used for log messages.
            leaf (dict): A settings leaf node with 'value', 'default', and
                optionally 'type' keys.
        
        Returns:
            bool: True if the value was valid (or no type declared), False if
                it was reset to the default.
        """
        declared_type = leaf.get("type")
        if not declared_type:
            return True

        checker = FileUtils.SETTING_TYPE_CHECKS.get(declared_type)
        if checker is None:
            return True  # Unknown type - skip

        value = leaf.get("value")
        if not checker(value):
            logger.warning(
                "Settings value at '%s' has type '%s' but value %r is invalid; "
                "resetting to default %r.",
                path,
                declared_type,
                value,
                leaf.get("default"),
            )
            leaf["value"] = leaf["default"]
            return False
        return True

    @staticmethod
    def validate_merged_settings(merged: dict, path: str = "") -> None:
        """
        Recursively walk a merged settings dict and validate every leaf node.

        Args:
            merged (dict): The merged settings dictionary to validate.
            path (str): Current dot-separated key path (used for log messages).
        
        Returns:
            None
        """
        for key, val in merged.items():
            current_path = f"{path}.{key}" if path else key
            if not isinstance(val, dict):
                continue
            if FileUtils.is_setting_leaf(val):
                FileUtils.validate_setting_leaf(current_path, val)
            else:
                FileUtils.validate_merged_settings(val, current_path)

    @staticmethod
    def merge_dict(default: dict, user: dict) -> dict:
        """
        Recursively merge default and user dicts with default structure as authoritative.

        Default structure wins completely - keys present in user but absent from
        default are pruned. Keys that moved to a different path in the default are
        removed from their old location and replaced at the new location using the
        default value. For settings leaf nodes (dicts containing both 'value' and
        'default' keys), only the 'value' field is carried from the user; all other
        metadata ('type', 'default', 'description', 'hidden') always comes from the
        default. For plain scalar values, the user value is preserved at exact path
        matches.

        Args:
            default (dict): The default configuration dictionary.
            user (dict): The user configuration dictionary.
        
        Returns:
            dict: Merged dictionary following default structure exactly.
        """
        if not isinstance(default, dict):
            return user

        merged = {}

        for key, default_val in default.items():
            if key not in user:
                merged[key] = default_val
            elif isinstance(default_val, dict) and isinstance(user[key], dict):
                user_val = user[key]
                if FileUtils.is_setting_leaf(default_val):
                    # Settings leaf: refresh all metadata from default, preserve only value
                    merged[key] = dict(default_val)
                    merged[key]["value"] = user_val.get("value", default_val["value"])
                else:
                    merged[key] = FileUtils.merge_dict(default_val, user_val)
            elif not isinstance(default_val, dict):
                merged[key] = user[key]  # both scalars - user wins
            else:
                merged[key] = default_val  # type mismatch - default wins

        # Keys in user not present in default are intentionally omitted (pruned)
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
        FileUtils.validate_merged_settings(merged)  # Type-check values after merge

        # Only write if file missing or structure changed
        if not user_path.exists() or merged != user_data:
            logger.info("Writing merged YAML to: %s", user_path)
            FileUtils.ensure_dir(user_path.parent)
            FileUtils.write_yaml(user_path, merged)
        else:
            logger.debug("User YAML already up to date: %s", user_path)

        return merged
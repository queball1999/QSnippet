import os
import yaml
import logging
from PySide6.QtCore import QObject, QFileSystemWatcher, Signal

logger = logging.getLogger(__name__)

class ConfigLoader(QObject):
    """
    Loads and watches the YAML application config file.
    Emits `configChanged` when the top-level settings change.
    """
    configChanged = Signal(dict)

    def __init__(self, config_path: str, parent=None):
        """
        Initialize the ConfigLoader instance.

        Sets up a file system watcher for the specified configuration file,
        loads the initial configuration, and connects change signals.

        Args:
            config_path (str): Path to the configuration YAML file.
            parent (Any): Optional parent QObject.

        Returns:
            None
        """
        logger.info("Initializing ConfigLoader")
        super().__init__()
        self.config_path = os.path.abspath(config_path)
        logger.debug("Config Path: %s", self.config_path)

        self._watcher = QFileSystemWatcher(self)
        self._watcher.addPath(self.config_path)
        self._watcher.fileChanged.connect(self.on_file_changed)

        # initial load
        self.config = {}
        self.load_config()
        logger.info("ConfigLoader successfully initialized")

    def load_config(self):
        """
        Load the configuration file from disk and emit a change signal.

        Reads the YAML configuration file, updates the internal config
        attribute, and emits the configChanged signal with the loaded data.

        Returns:
            None
        """
        logger.debug("Loading config file: %s", self.config_path)

        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f) or {}
            self.config = data
            
            logger.info("Config loaded successfully")
            logger.debug(f"Loaded config: {self.config_path}")
            self.configChanged.emit(self.config)
        except Exception as e:
            logger.error(f"Failed to load config {self.config_path}: {e}")

    def on_file_changed(self, path):
        """
        Handle file change events for the configuration file.

        Re-adds the file path to the watcher if necessary and reloads
        the configuration from disk.

        Args:
            path (str): The path of the changed file.

        Returns:
            None
        """
        logger.debug("Config file change detected: %s", path)

        if not self._watcher.files():
            logger.debug("Re-adding config path to watcher")
            self._watcher.addPath(self.config_path)

        self.load_config()

    def stop(self):
        """
        Stop watching the configuration file for changes.

        Removes the configuration file path from the file system watcher.

        Returns:
            None
        """
        logger.debug("Stopping ConfigLoader watcher")
        self._watcher.removePath(self.config_path)

class SettingsLoader(QObject):
    """
    Loads and watches the YAML application settings file.
    Emits `settingsChanged` when the top-level settings change.
    """
    settingsChanged = Signal(dict)

    def __init__(self, settings_path: str, parent=None):
        """
        Initialize the SettingsLoader instance.

        Sets up a file system watcher for the specified settings file,
        loads and normalizes the initial settings, and connects change signals.

        Args:
            settings_path (str): Path to the settings YAML file.
            parent (Any): Optional parent QObject.

        Returns:
            None
        """
        logger.debug("Initializing SettingsLoader")
        super().__init__()
        self.settings_path = os.path.abspath(settings_path)
        logger.debug("Settings Path: %s", self.settings_path)
        
        self._watcher = QFileSystemWatcher(self)
        self._watcher.addPath(self.settings_path)
        self._watcher.fileChanged.connect(self.on_file_changed)

        # initial load
        self.settings = {}
        self.load_settings()
        logger.info("SettingsLoader successfully initialized")

    def load_settings(self):
        """
        Load the settings file from disk and emit a change signal.

        Reads the YAML settings file, normalizes its structure, updates
        the internal settings attribute, and emits the settingsChanged signal.

        Returns:
            None
        """
        logger.debug("Loading settings file: %s", self.settings_path)

        try:
            with open(self.settings_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f) or {}

            self.settings = self.normalize_settings(data)
            logger.info(f"Loaded Settings: {self.settings_path}")
            self.settingsChanged.emit(self.settings)
        except Exception as e:
            logger.error(f"Failed to load Settings {self.settings_path}: {e}")

    
    def infer_type(self, value):
        """
        Infer the string representation of a value's type.

        Args:
            value (Any): The value to evaluate.

        Returns:
            str: A string representing the inferred type.
        """
        if isinstance(value, bool):
            return "bool"
        if isinstance(value, int):
            return "int"
        if isinstance(value, list):
            return "list"
        if isinstance(value, str):
            return "string"
        return "unknown"

    def normalize_settings(self, data: dict) -> dict:
        """
        Normalize the structure of the settings dictionary.

        Ensures that structural groupings remain dictionaries while leaf
        values are converted into dictionaries containing type and value keys.

        Args:
            data (dict): The raw settings dictionary.

        Returns:
            dict: The normalized settings dictionary.
        """

        def normalize_node(node):
            # Already a normalized setting
            if isinstance(node, dict) and "value" in node:
                return node

            # Structural grouping
            if isinstance(node, dict):
                return {
                    key: normalize_node(value)
                    for key, value in node.items()
                }

            # Scalar leaf value (fallback support)
            return {
                "type": self.infer_type(node),
                "value": node,
            }

        return normalize_node(data or {})

    def on_file_changed(self, path):
        """
        Handle file change events for the settings file.

        Re-adds the file path to the watcher if necessary and reloads
        the settings from disk.

        Args:
            path (str): The path of the changed file.

        Returns:
            None
        """
        logger.debug("Settings file change detected: %s", path)

        if not self._watcher.files():
            logger.debug("Re-adding settings path to watcher")
            self._watcher.addPath(self.settings_path)

        self.load_settings()

    def stop(self):
        """
        Stop watching the settings file for changes.

        Removes the settings file path from the file system watcher.

        Returns:
            None
        """
        logger.debug("Stopping SettingsLoader watcher")
        self._watcher.removePath(self.settings_path)

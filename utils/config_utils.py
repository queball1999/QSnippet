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
        logger.info("Initializing ConfigLoader")
        super().__init__()
        self.config_path = os.path.abspath(config_path)
        logger.debug("Config Path: %s", self.config_path)

        self._watcher = QFileSystemWatcher(self)
        self._watcher.addPath(self.config_path)
        self._watcher.fileChanged.connect(self._on_file_changed)

        # initial load
        self.config = {}
        self._load_config()
        logger.info("ConfigLoader successfully initialized")

    def _load_config(self):
        """Load config.yaml from disk and emit configChanged."""
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

    def _on_file_changed(self, path):
        # QFileSystemWatcher may emit twice, so re-add path if needed
        logger.debug("Config file change detected: %s", path)

        if not self._watcher.files():
            logger.debug("Re-adding config path to watcher")
            self._watcher.addPath(self.config_path)

        self._load_config()

    def stop(self):
        """Stop watching the config file."""
        logger.debug("Stopping ConfigLoader watcher")
        self._watcher.removePath(self.config_path)

class SettingsLoader(QObject):
    """
    Loads and watches the YAML application settings file.
    Emits `settingsChanged` when the top-level settings change.
    """
    settingsChanged = Signal(dict)

    def __init__(self, settings_path: str, parent=None):
        logger.debug("Initializing SettingsLoader")
        super().__init__()
        self.settings_path = os.path.abspath(settings_path)
        logger.debug("Settings Path: %s", self.settings_path)
        
        self._watcher = QFileSystemWatcher(self)
        self._watcher.addPath(self.settings_path)
        self._watcher.fileChanged.connect(self._on_file_changed)

        # initial load
        self.settings = {}
        self._load_settings()
        logger.info("SettingsLoader successfully initialized")

    def _load_settings(self):
        """Load settings.yaml from disk and emit settingsChanged."""
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
        Normalize settings structure:
        - Categories and subcategories remain dicts
        - Only leaf nodes with values become {type, value, ...}
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

    def _on_file_changed(self, path):
        # QFileSystemWatcher may emit twice, so re-add path if needed
        logger.debug("Settings file change detected: %s", path)

        if not self._watcher.files():
            logger.debug("Re-adding settings path to watcher")
            self._watcher.addPath(self.settings_path)

        self._load_settings()

    def stop(self):
        """Stop watching the settings file."""
        logger.debug("Stopping SettingsLoader watcher")
        self._watcher.removePath(self.settings_path)

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
        super().__init__()
        self.config_path = os.path.abspath(config_path)
        self._watcher = QFileSystemWatcher(self)
        self._watcher.addPath(self.config_path)
        self._watcher.fileChanged.connect(self._on_file_changed)

        # initial load
        self.config = {}
        self._load_config()

    def _load_config(self):
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f) or {}
            self.config = data
            logger.info(f"Loaded config: {self.config_path}")
            self.configChanged.emit(self.config)
        except Exception as e:
            logger.error(f"Failed to load config {self.config_path}: {e}")

    def _on_file_changed(self, path):
        # QFileSystemWatcher may emit twice, so re-add path if needed
        if not self._watcher.files():
            self._watcher.addPath(self.config_path)
        logger.info(f"Config file changed on disk: {path}")
        self._load_config()

    def stop(self):
        """Stop watching the config file."""
        self._watcher.removePath(self.config_path)


class SnippetsLoader(QObject):
    """
    Loads and watches the YAML snippets file.
    Emits `snippetsChanged` when the snippet definitions update.
    """
    snippetsChanged = Signal(list)

    def __init__(self, snippets_path: str, parent=None):
        super().__init__()
        self.snippets_path = os.path.abspath(snippets_path)
        self._watcher = QFileSystemWatcher(self)
        self._watcher.addPath(self.snippets_path)
        self._watcher.fileChanged.connect(self._on_file_changed)

        # initial load
        self.snippets = []
        self._load_snippets()

    def _load_snippets(self):
        try:
            with open(self.snippets_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f) or {}
            self.snippets = data.get('snippets', [])
            logger.info(f"Loaded {len(self.snippets)} snippets from {self.snippets_path}")
            self.snippetsChanged.emit(self.snippets)
        except Exception as e:
            logger.error(f"Failed to load snippets {self.snippets_path}: {e}")

    def _on_file_changed(self, path):
        # re-add path if watcher lost it
        if not self._watcher.files():
            self._watcher.addPath(self.snippets_path)
        logger.info(f"Snippets file changed on disk: {path}")
        self._load_snippets()

    def stop(self):
        """Stop watching the snippets file."""
        self._watcher.removePath(self.snippets_path)

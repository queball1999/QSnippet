import os
import sys
import pytest
import tempfile
from pathlib import Path
from unittest.mock import MagicMock
from PySide6.QtCore import QCoreApplication

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture(scope="session")
def project_root():
    """Return the project root path."""
    return PROJECT_ROOT


@pytest.fixture
def temp_dir(tmp_path):
    """
    Generic temporary directory fixture.
    """
    return tmp_path


@pytest.fixture
def temp_app_dirs(tmp_path):
    """
    Create a fake application directory structure.
    Mimics FileUtils.get_default_paths output.
    """
    base = tmp_path / "app"
    paths = {
        "working_dir": base,
        "resource_dir": base / "resources",
        "log_dir": base / "logs",
        "documents": base / "documents",
        "app_data": base / "app_data",
    }

    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)

    return paths


@pytest.fixture
def temp_snippet_db_path(tmp_path):
    """
    Provide a temporary SQLite database path.
    """
    return tmp_path / "snippets.db"


@pytest.fixture
def temp_config_file(tmp_path):
    """
    Provide a temporary config.yaml path.
    """
    return tmp_path / "config.yaml"


@pytest.fixture
def temp_settings_file(tmp_path):
    """
    Provide a temporary settings.yaml path.
    """
    return tmp_path / "settings.yaml"


""" @pytest.fixture
def mock_qt_app(monkeypatch):
    
    # Mock QApplication and related Qt objects.
    # Prevents real Qt initialization during tests.
    
    mock_app = MagicMock()
    mock_clipboard = MagicMock()
    mock_screen = MagicMock()
    mock_geometry = MagicMock()

    mock_geometry.width.return_value = 1920
    mock_geometry.height.return_value = 1080

    mock_screen.geometry.return_value = mock_geometry
    mock_app.clipboard.return_value = mock_clipboard
    mock_app.primaryScreen.return_value = mock_screen

    monkeypatch.setattr(
        "PySide6.QtWidgets.QApplication.instance",
        lambda: mock_app
    )

    return mock_app """

@pytest.fixture(scope="session", autouse=True)
def mock_qt_app():
    """
    Provide a single Qt application instance for the entire test session.
    Uses QCoreApplication to avoid GUI initialization.
    """
    app = QCoreApplication.instance()
    if app is None:
        app = QCoreApplication(sys.argv)
    yield app


@pytest.fixture
def mock_reg_utils(monkeypatch):
    """
    Mock RegUtils to avoid touching the Windows registry.
    """
    mock = MagicMock()
    mock.is_in_run_key.return_value = False

    monkeypatch.setattr(
        "utils.reg_utils.RegUtils",
        mock,
        raising=False
    )

    return mock


@pytest.fixture
def disable_sys_exit(monkeypatch):
    """
    Prevent sys.exit from killing pytest.
    """
    monkeypatch.setattr(sys, "exit", lambda *args, **kwargs: None)

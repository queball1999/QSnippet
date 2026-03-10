import os
import sys
import pytest
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def pytest_addoption(parser):
    """Add custom command-line options."""
    parser.addoption(
        "--benchmark",
        action="store_true",
        default=False,
        help="run benchmark tests"
    )


def pytest_configure(config):
    """Skip benchmark tests by default unless --benchmark flag is passed."""
    if not config.getoption("--benchmark"):
        config.option.markexpr = "not benchmark"


@pytest.fixture(scope="session")
def project_root():
    """Return the project root path.

    Returns:
        Path: The absolute path to the project root directory.
    """
    return PROJECT_ROOT


@pytest.fixture
def temp_dir(tmp_path):
    """Provide a generic temporary directory for testing.

    Returns:
        Path: A fresh temporary directory.
    """
    return tmp_path


@pytest.fixture
def temp_app_dirs(tmp_path):
    """Create a fake application directory structure.

    Mimics FileUtils.get_default_paths output.

    Returns:
        dict: Mapping of path keys to temporary Path objects.
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
    """Provide a temporary SQLite database path.

    Returns:
        Path: A path to a non-existent database file in a temp directory.
    """
    return tmp_path / "snippets.db"


@pytest.fixture
def temp_config_file(tmp_path):
    """Provide a temporary config.yaml path.

    Returns:
        Path: A path to a non-existent config file in a temp directory.
    """
    return tmp_path / "config.yaml"


@pytest.fixture
def temp_settings_file(tmp_path):
    """Provide a temporary settings.yaml path.

    Returns:
        Path: A path to a non-existent settings file in a temp directory.
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
    """Provide a single Qt application instance for the entire test session.

    Uses QCoreApplication to avoid GUI initialization.

    Yields:
        QCoreApplication: The shared application instance.
    """
    from PySide6.QtCore import QCoreApplication

    app = QCoreApplication.instance()
    if app is None:
        app = QCoreApplication(sys.argv)
    yield app


@pytest.fixture
def mock_reg_utils(monkeypatch):
    """Mock RegUtils to avoid touching the Windows registry.

    Returns:
        MagicMock: A mock RegUtils with is_in_run_key returning False.
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
    """Prevent sys.exit from killing pytest."""
    monkeypatch.setattr(sys, "exit", lambda *args, **kwargs: None)


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    from tests.db.benchmark_test import _results

    if not _results:
        return

    _results.sort(key=lambda r: (r["qty"], r["type"]))

    header = f"{'Qty':>12}  {'Type':<12}  {'Per Item':>15}  {'Total':>12}"
    divider = "-" * len(header)

    terminalreporter.write_sep("=", "Benchmark Results")
    terminalreporter.write_line(header)
    terminalreporter.write_line(divider)

    prev_qty = None
    for r in _results:
        if prev_qty is not None and r["qty"] != prev_qty:
            terminalreporter.write_line("")
        prev_qty = r["qty"]
        terminalreporter.write_line(
            f"{r['qty']:>12,}  "
            f"{r['type']:<12}  "
            f"{r['per_item_ms']:>12.4f} ms  "
            f"{r['total_ms']:>9.2f} ms"
        )

    terminalreporter.write_line(divider)
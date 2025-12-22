import time
from unittest.mock import MagicMock, patch

import pytest

from ui import SnippetService


# Fixtures

@pytest.fixture
def mock_expander(monkeypatch):
    """
    Mock SnippetExpander to avoid real keyboard hooks.
    """
    mock = MagicMock()
    monkeypatch.setattr(
        "ui.service.SnippetExpander",
        lambda *args, **kwargs: mock
    )
    return mock


@pytest.fixture
def mock_db(monkeypatch):
    """
    Mock SnippetDB to avoid real database work.
    """
    mock = MagicMock()
    monkeypatch.setattr(
        "ui.service.SnippetDB",
        lambda *args, **kwargs: mock
    )
    return mock


@pytest.fixture
def service(mock_expander, mock_db, tmp_path):
    """
    Create SnippetService with mocked dependencies.
    """
    db_path = tmp_path / "snippets.db"
    return SnippetService(str(db_path))


# Tests

def test_service_initializes(service, mock_expander, mock_db):
    """
    Service should initialize with expander and db.
    """
    assert service.snippet_db is mock_db
    assert service.expander is mock_expander
    assert service._thread is None
    assert service.active() is False


def test_start_starts_expander_and_thread(service, mock_expander):
    """
    start() should start expander and background thread.
    """
    service.start()

    mock_expander.start.assert_called_once()

    # Allow thread to spin up
    time.sleep(0.05)

    assert service._thread is not None
    assert service._thread.is_alive()
    assert service.active() is True


def test_start_is_idempotent(service, mock_expander):
    """
    Calling start() twice should not restart expander.
    """
    service.start()
    service.start()

    mock_expander.start.assert_called_once()


def test_stop_stops_service(service, mock_expander):
    """
    stop() should signal shutdown and stop expander.
    """
    service.start()
    time.sleep(0.05)

    service.stop()

    mock_expander.stop.assert_called_once()
    assert service.active() is False


def test_stop_without_start_is_safe(service):
    """
    stop() without start should not crash.
    """
    service.stop()
    assert service.active() is False


def test_refresh_calls_expander(service, mock_expander):
    """
    refresh() should reload snippets via expander.
    """
    service.refresh()
    mock_expander.refresh_snippets.assert_called_once()


def test_pause_and_resume_delegate(service, mock_expander):
    """
    pause() and resume() should delegate to expander.
    """
    service.pause()
    service.resume()

    mock_expander.pause.assert_called_once()
    mock_expander.resume.assert_called_once()


def test_active_reflects_state(service):
    """
    active() should reflect running thread state.
    """
    assert service.active() is False

    service.start()
    time.sleep(0.05)

    assert service.active() is True

    service.stop()
    assert service.active() is False

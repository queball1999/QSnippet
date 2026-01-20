import logging
import zipfile
from pathlib import Path

import pytest

from utils.logging_utils import (
    CompressedRotatingFileHandler,
    AppLogger,
)


# -------------------------
# CompressedRotatingFileHandler
# -------------------------

def test_compressed_handler_creates_zip_on_rollover(tmp_path):
    """
    Rollover should compress the existing log file into a .zip.
    """
    log_path = tmp_path / "test.log"

    handler = CompressedRotatingFileHandler(
        log_path,
        maxBytes=1,
        backupCount=3,
    )

    logger = logging.getLogger("test_logger_1")
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)

    logger.info("A")  # create log
    handler.doRollover()

    zip_path = tmp_path / "test.log.1.zip"
    assert zip_path.exists()

    with zipfile.ZipFile(zip_path, "r") as zf:
        assert "test.log" in zf.namelist()


def test_compressed_handler_rotates_backups(tmp_path):
    """
    Old compressed logs should rotate and respect backupCount.
    """
    log_path = tmp_path / "rotate.log"

    handler = CompressedRotatingFileHandler(
        log_path,
        maxBytes=1,
        backupCount=2,
    )

    logger = logging.getLogger("test_logger_2")
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)

    logger.info("one")
    handler.doRollover()
    assert (tmp_path / "rotate.log.1.zip").exists()

    logger.info("two")
    handler.doRollover()
    assert (tmp_path / "rotate.log.1.zip").exists()
    assert (tmp_path / "rotate.log.2.zip").exists()

    logger.info("three")
    handler.doRollover()

    assert (tmp_path / "rotate.log.1.zip").exists()
    assert (tmp_path / "rotate.log.2.zip").exists()
    assert not (tmp_path / "rotate.log.3.zip").exists()


def test_compress_log_file_removes_original(tmp_path):
    """
    compress_log_file should zip the file and delete the source
    once the stream is closed (Windows-safe).
    """
    source = tmp_path / "raw.log"
    dest = tmp_path / "raw.log.zip"

    source.write_text("log data")

    handler = CompressedRotatingFileHandler(
        source,
        maxBytes=1,
        backupCount=1,
    )

    # IMPORTANT: close the stream before deleting (Windows requirement)
    if handler.stream:
        handler.stream.close()
        handler.stream = None

    handler.compress_log_file(source, dest)

    assert dest.exists()
    assert not source.exists()


# -------------------------
# AppLogger
# -------------------------

def test_app_logger_configures_root_logger(tmp_path):
    """
    AppLogger should configure root logger with correct handler and level.
    """
    log_path = tmp_path / "app.log"

    AppLogger(
        log_filepath=log_path,
        log_level=logging.DEBUG,
        max_bytes=1024,
        backup_count=1,
    )

    root = logging.getLogger()

    assert root.level == logging.DEBUG
    assert len(root.handlers) == 1
    assert isinstance(root.handlers[0], CompressedRotatingFileHandler)
    assert Path(root.handlers[0].baseFilename) == log_path


def test_app_logger_replaces_existing_handlers(tmp_path):
    """
    Reconfiguring AppLogger should remove previous handlers
    and install CompressedRotatingFileHandler.
    """
    root = logging.getLogger()
    root.handlers.clear()

    root.addHandler(logging.StreamHandler())
    assert len(root.handlers) == 1

    AppLogger(
        log_filepath=tmp_path / "new.log",
        log_level=logging.INFO,
    )

    assert len(root.handlers) == 1
    assert isinstance(root.handlers[0], CompressedRotatingFileHandler)

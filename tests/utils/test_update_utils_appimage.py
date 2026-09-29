"""
Unit tests for AppImage handling in the updater launch path.

From an AppImage, QSnippet must relaunch the .AppImage file (not the binary
inside its temporary mount) and must copy the updater out of the mount before
an install, since the mount disappears when QSnippet exits.
"""
import hashlib
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from utils import update_utils


@pytest.fixture
def appimage_install(tmp_path, monkeypatch):
    """Fake a frozen QSnippet running from inside an AppImage mount."""
    image = tmp_path / "QSnippet-0.0.8-x86_64.AppImage"
    image.write_bytes(b"appimage")

    mount = tmp_path / "mount" / "usr" / "lib" / "qsnippet"
    (mount / "config").mkdir(parents=True)
    updater = mount / update_utils.updater_filename()
    updater.write_bytes(b"updater-binary")
    config = mount / "config" / "updater.yaml"
    config.write_text("app:\n  name: QSnippet\n", encoding="utf-8")

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(mount / "QSnippet"))
    monkeypatch.setenv("APPIMAGE", str(image))
    # A local build leaves a real hash in config/build_info.py; the fake
    # updater here would never match it.
    monkeypatch.setattr(update_utils, "expected_updater_hash", lambda: "")

    main = SimpleNamespace(working_dir=str(mount), config_dir=str(mount / "config"))
    return SimpleNamespace(image=image, mount=mount, updater=updater, config=config, main=main)


def option_value(command: list, flag: str) -> str:
    """Return the value following `flag` in a command line."""
    return command[command.index(flag) + 1]


class TestRunningAppimage:
    """Detecting the AppImage file QSnippet was launched from."""

    def test_returns_image_path(self, appimage_install):
        assert update_utils.running_appimage() == appimage_install.image

    def test_none_from_source(self, appimage_install, monkeypatch):
        monkeypatch.setattr(sys, "frozen", False, raising=False)
        assert update_utils.running_appimage() is None

    def test_none_without_env(self, appimage_install, monkeypatch):
        monkeypatch.delenv("APPIMAGE")
        assert update_utils.running_appimage() is None

    def test_none_when_image_missing(self, appimage_install):
        appimage_install.image.unlink()
        assert update_utils.running_appimage() is None


class TestApplicationExecutable:
    """The path the updater relaunches after installing."""

    def test_relaunches_the_appimage_not_the_mount(self, appimage_install):
        assert update_utils.application_executable(appimage_install.main) == appimage_install.image

    def test_plain_frozen_build_uses_sys_executable(self, appimage_install, monkeypatch):
        monkeypatch.delenv("APPIMAGE")
        assert update_utils.application_executable(appimage_install.main) == Path(sys.executable)


class TestBuildCommand:
    """Staging the updater outside the mount for installs only."""

    def test_install_runs_a_staged_copy(self, appimage_install):
        command = update_utils.build_command(appimage_install.main, [], install=True)

        staged = Path(command[0])
        assert staged != appimage_install.updater
        assert appimage_install.mount not in staged.parents
        assert staged.read_bytes() == appimage_install.updater.read_bytes()

        staged_config = Path(option_value(command, "--config"))
        assert staged_config.parent.parent == staged.parent
        assert staged_config.read_text(encoding="utf-8") == appimage_install.config.read_text(encoding="utf-8")

        assert option_value(command, "--executable") == str(appimage_install.image)

    def test_check_runs_in_place(self, appimage_install):
        command = update_utils.build_command(appimage_install.main, [])
        assert Path(command[0]) == appimage_install.updater.resolve()

    def test_install_outside_appimage_runs_in_place(self, appimage_install, monkeypatch):
        monkeypatch.delenv("APPIMAGE")
        command = update_utils.build_command(appimage_install.main, [], install=True)
        assert Path(command[0]) == appimage_install.updater.resolve()

    def test_staged_copy_is_hash_verified(self, appimage_install):
        good = hashlib.sha256(b"updater-binary").hexdigest()
        with patch.object(update_utils, "expected_updater_hash", return_value=good):
            assert update_utils.build_command(appimage_install.main, [], install=True) is not None

        with patch.object(update_utils, "expected_updater_hash", return_value="0" * 64):
            assert update_utils.build_command(appimage_install.main, [], install=True) is None

    def test_staging_failure_refuses_to_launch(self, appimage_install):
        with patch.object(update_utils, "stage_outside_appimage", side_effect=OSError("disk full")):
            assert update_utils.build_command(appimage_install.main, [], install=True) is None

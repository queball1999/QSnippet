"""
Tests that backups capture config.yaml alongside the database.

The vault's salt and verifier live in config.yaml, not in the database. A
backup of the database alone restores nothing but unreadable ciphertext,
which is exactly how encrypted snippets end up permanently orphaned.
"""

import zipfile

import pytest
import yaml

from utils.snippet_db import SnippetDB


VAULT_CONFIG = {
    "vault": {
        "salt": "c2FsdC12YWx1ZQ==",
        "verifier": "dmVyaWZpZXItdmFsdWU=",
        "auto_lock_minutes": 15,
    }
}


@pytest.fixture
def app_data(tmp_path, monkeypatch):
    """Point the app-data lookup at a temp dir holding a real config.yaml."""
    data_dir = tmp_path / "appdata"
    data_dir.mkdir()
    (data_dir / "config.yaml").write_text(
        yaml.safe_dump(VAULT_CONFIG), encoding="utf-8"
    )

    from utils.file_utils import FileUtils

    original = FileUtils.get_default_paths
    monkeypatch.setattr(
        FileUtils,
        "get_default_paths",
        staticmethod(lambda: {**original(), "app_data": data_dir}),
    )
    return data_dir


@pytest.fixture
def db(tmp_path):
    database = SnippetDB(tmp_path / "snippets.db")
    database.insert_snippet({
        "label": "Example", "trigger": "/ex", "snippet": "hello",
        "folder": "Default", "enabled": 1, "paste_style": "clipboard",
        "return_press": 0, "tags": "",
    })
    return database


def archive_members(path):
    with zipfile.ZipFile(path) as zf:
        return zf.namelist()


def test_backup_includes_config(app_data, db, tmp_path):
    out = tmp_path / "out"
    _, _, archive = db.backup_before_migration(export_dir=out)

    assert archive is not None, "no archive was produced"
    members = archive_members(archive)
    assert any("config-backup" in m for m in members), \
        f"config.yaml missing from the backup: {members}"


def test_backed_up_config_still_holds_the_vault_keys(app_data, db, tmp_path):
    """A backup that drops the salt is not a backup of the vault."""
    out = tmp_path / "out"
    _, _, archive = db.backup_before_migration(export_dir=out)

    with zipfile.ZipFile(archive) as zf:
        name = next(m for m in zf.namelist() if "config-backup" in m)
        restored = yaml.safe_load(zf.read(name).decode("utf-8"))

    assert restored["vault"]["salt"] == VAULT_CONFIG["vault"]["salt"]
    assert restored["vault"]["verifier"] == VAULT_CONFIG["vault"]["verifier"]


def test_backup_still_includes_the_database_and_export(app_data, db, tmp_path):
    out = tmp_path / "out"
    _, _, archive = db.backup_before_migration(export_dir=out)

    members = archive_members(archive)
    assert any(m.endswith(".db") for m in members), members
    assert any(m.endswith(".yaml") and "config" not in m for m in members), members


def test_backup_survives_a_missing_config(db, tmp_path, monkeypatch):
    """No config to copy must not cost the user the rest of the backup."""
    monkeypatch.setattr(SnippetDB, "config_source", staticmethod(lambda: None))

    out = tmp_path / "out"
    _, _, archive = db.backup_before_migration(export_dir=out)

    assert archive is not None
    members = archive_members(archive)
    assert any(m.endswith(".db") for m in members)
    assert not any("config-backup" in m for m in members)


def test_config_source_returns_none_when_absent(tmp_path, monkeypatch):
    from utils.file_utils import FileUtils

    empty = tmp_path / "empty"
    empty.mkdir()
    original = FileUtils.get_default_paths
    monkeypatch.setattr(
        FileUtils,
        "get_default_paths",
        staticmethod(lambda: {**original(), "app_data": empty}),
    )

    assert SnippetDB.config_source() is None


def test_config_source_survives_a_broken_path_lookup(monkeypatch):
    from utils.file_utils import FileUtils

    def explode():
        raise RuntimeError("no paths")

    monkeypatch.setattr(FileUtils, "get_default_paths", staticmethod(explode))

    assert SnippetDB.config_source() is None

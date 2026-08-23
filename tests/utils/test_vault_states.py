"""
Tests for vault state classification and the disable safety net.

The password key material lives in config.yaml while the data it protects
lives in the database, so the two can drift apart. Every combination has to
be named correctly, because the wrong answer either offers a setup that
strands data or hides a vault the user still has.
"""

import pytest

from utils.vault_manager import (
    VaultManager,
    VAULT_NOT_SET_UP,
    VAULT_READY,
    VAULT_ORPHANED_LOST,
    VAULT_ORPHANED_RECOVERABLE,
    VAULT_STALE_KEYS,
)


class FakeDb:
    def __init__(self, snippets=0, placeholders=0, fail=False):
        self.counts = (snippets, placeholders)
        self.fail = fail

    def count_encrypted_rows(self):
        if self.fail:
            raise RuntimeError("database unavailable")
        return self.counts


@pytest.fixture
def vm():
    return VaultManager()


def config(**vault):
    return {"vault": vault}


READY = config(salt="s", verifier="v")
BLANK = config(salt="", verifier="", auto_lock_minutes=15)
RECOVERY_ONLY = config(salt="", verifier="", rec_salt="a", rec_verifier="b",
                       rec_key_blob="c")


# ----- CLASSIFICATION -----

def test_nothing_anywhere_is_not_set_up(vm):
    status = vm.describe(config(), FakeDb())

    assert status.state == VAULT_NOT_SET_UP
    assert not status.blocks_setup
    assert not status.has_data


def test_blank_strings_are_not_a_vault(vm):
    """A disabled vault leaves the keys present but empty."""
    status = vm.describe(BLANK, FakeDb())

    assert status.state == VAULT_NOT_SET_UP
    assert not status.blocks_setup


def test_usable_key_material_is_ready(vm):
    status = vm.describe(READY, FakeDb(snippets=3))

    assert status.state == VAULT_READY
    assert status.is_ready
    assert status.blocks_setup
    assert status.rows == 3


def test_data_without_keys_is_orphaned_and_lost(vm):
    status = vm.describe(BLANK, FakeDb(snippets=2, placeholders=2))

    assert status.state == VAULT_ORPHANED_LOST
    assert status.is_orphaned
    assert status.blocks_setup
    assert not status.has_recovery
    assert status.rows == 4


def test_data_with_recovery_material_is_recoverable(vm):
    status = vm.describe(RECOVERY_ONLY, FakeDb(snippets=1))

    assert status.state == VAULT_ORPHANED_RECOVERABLE
    assert status.is_orphaned
    assert status.has_recovery


def test_leftover_keys_with_no_data_are_stale(vm):
    status = vm.describe(RECOVERY_ONLY, FakeDb())

    assert status.state == VAULT_STALE_KEYS
    assert not status.blocks_setup, "stale keys protect nothing and must not block setup"


def test_half_written_config_is_flagged_as_partial(vm):
    """Salt without verifier means the config was damaged, not absent."""
    status = vm.describe(config(salt="s"), FakeDb(snippets=1))

    assert status.partial_config
    assert status.state == VAULT_ORPHANED_LOST

    both = vm.describe(READY, FakeDb())
    assert not both.partial_config


def test_partial_config_with_no_data_is_only_stale(vm):
    status = vm.describe(config(verifier="v"), FakeDb())

    assert status.state == VAULT_STALE_KEYS
    assert status.partial_config
    assert not status.blocks_setup


def test_unreadable_database_reports_unknown_not_zero(vm):
    """A failed count must not be mistaken for "there is no data"."""
    status = vm.describe(BLANK, FakeDb(fail=True))

    assert status.counted is False
    assert status.rows == 0


def test_describe_without_a_database_says_so(vm):
    status = vm.describe(READY)

    assert status.counted is False
    assert status.state == VAULT_READY


def test_strip_crypto_material_keeps_preferences(vm):
    stripped = VaultManager.strip_crypto_material(
        config(salt="s", verifier="v", rec_salt="a", rec_verifier="b",
               rec_key_blob="c", auto_lock_minutes=30, unlock_on_launch=True)
    )

    vault = stripped["vault"]
    for gone in ("salt", "verifier", "rec_salt", "rec_verifier", "rec_key_blob"):
        assert gone not in vault
    assert vault["auto_lock_minutes"] == 30
    assert vault["unlock_on_launch"] is True


def test_strip_crypto_material_does_not_mutate_the_original(vm):
    original = config(salt="s", verifier="v")
    VaultManager.strip_crypto_material(original)

    assert original["vault"]["salt"] == "s"


# ----- DISABLE SAFETY NET -----

class DisableDb:
    """A database whose decryption of one row always fails."""

    def __init__(self, failing_ids=(), placeholders=()):
        self.failing_ids = set(failing_ids)
        self.snippets = [
            {"id": 1, "snippet": "blob1", "vault_uuid": "u1"},
            {"id": 2, "snippet": "blob2", "vault_uuid": "u2"},
        ]
        self.placeholder_rows = list(placeholders)
        self.folders_cleared = False
        self.updated = []

    def get_vault_snippets(self):
        return list(self.snippets)

    def get_all_custom_placeholders(self):
        return list(self.placeholder_rows)

    def update_snippet_content(self, snippet_id, plain):
        self.updated.append(snippet_id)

    def update_snippet_folder(self, snippet_id, folder):
        pass

    def set_snippet_encrypted(self, snippet_id, value):
        pass

    def set_snippet_vault_uuid(self, snippet_id, value):
        pass

    def clear_vault_folders(self):
        self.folders_cleared = True


def prepared_manager(monkeypatch, failing_ids):
    """A manager that is 'unlocked' and fails to decrypt the named rows."""
    vm = VaultManager()
    monkeypatch.setattr(vm, "unlock", lambda pw, cfg: True)
    monkeypatch.setattr(vm, "pause_timer", lambda: None)
    monkeypatch.setattr(vm, "resume_timer", lambda: None)
    monkeypatch.setattr(vm, "lock", lambda: None)

    calls = {"n": 0}

    def decrypt(blob, aad=b""):
        calls["n"] += 1
        if blob in failing_ids:
            raise ValueError("authentication failed")
        return "plain"

    monkeypatch.setattr(vm, "decrypt", decrypt)
    return vm


def test_disable_keeps_keys_when_a_row_cannot_be_decrypted(monkeypatch):
    """
    The bug that stranded real data: disable logged the failure, carried on
    and blanked the key material anyway, leaving the row encrypted forever.
    """
    vm = prepared_manager(monkeypatch, failing_ids={"blob2"})
    db = DisableDb()
    cfg = {"vault": {"salt": "s", "verifier": "v"}}

    ok, updated = vm.disable_vault("pw", cfg, db)

    assert ok is False, "disable reported success despite a failed row"
    assert updated["vault"]["salt"] == "s", "key material was destroyed"
    assert updated["vault"]["verifier"] == "v"
    assert not db.folders_cleared, "vault folders were cleared despite the failure"
    assert vm.last_disable_failures, "the failure was not reported to the caller"


def test_disable_clears_keys_when_everything_decrypts(monkeypatch):
    vm = prepared_manager(monkeypatch, failing_ids=set())
    db = DisableDb()
    cfg = {"vault": {"salt": "s", "verifier": "v", "auto_lock_minutes": 30}}

    ok, updated = vm.disable_vault("pw", cfg, db)

    assert ok is True
    assert updated["vault"]["salt"] == ""
    assert updated["vault"]["verifier"] == ""
    assert updated["vault"]["auto_lock_minutes"] == 30, "preferences were lost"
    assert db.folders_cleared
    assert vm.last_disable_failures == []


def test_disable_failures_reset_between_runs(monkeypatch):
    """A stale failure list would mislabel the next run's outcome."""
    vm = prepared_manager(monkeypatch, failing_ids={"blob2"})
    db = DisableDb()
    cfg = {"vault": {"salt": "s", "verifier": "v"}}

    vm.disable_vault("pw", cfg, db)
    assert vm.last_disable_failures

    monkeypatch.setattr(vm, "decrypt", lambda blob, aad=b"": "plain")
    ok, _ = vm.disable_vault("pw", cfg, DisableDb())

    assert ok is True
    assert vm.last_disable_failures == []


def test_wrong_password_leaves_everything_alone(monkeypatch):
    vm = VaultManager()
    monkeypatch.setattr(vm, "unlock", lambda pw, cfg: False)
    db = DisableDb()
    cfg = {"vault": {"salt": "s", "verifier": "v"}}

    ok, updated = vm.disable_vault("wrong", cfg, db)

    assert ok is False
    assert updated["vault"]["salt"] == "s"
    assert not db.folders_cleared
    assert vm.last_disable_failures == []

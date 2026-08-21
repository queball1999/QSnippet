"""
Tests for VaultManager - AES-256-GCM encryption, PBKDF2 key derivation,
password verification, change password, and disable vault flows.
"""
import pytest
from utils.vault_manager import VaultManager, VaultError


@pytest.fixture(autouse=True)
def reset_vault():
    """Reset the singleton between tests so state never leaks."""
    vm = VaultManager.get_instance()
    vm.lock()
    # Disable auto-lock so timers don't interfere with tests
    vm.set_auto_lock_minutes(0)
    yield
    vm.lock()


@pytest.fixture
def vm():
    return VaultManager.get_instance()


@pytest.fixture
def setup_config(vm):
    """Return a config dict with vault set up using 'correct-password'."""
    return vm.setup("correct-password", {})


class TestIsSetup:
    def test_empty_config_is_not_setup(self, vm):
        assert vm.is_setup({}) is False

    def test_config_missing_verifier_is_not_setup(self, vm):
        assert vm.is_setup({"vault": {"salt": "abc"}}) is False

    def test_config_missing_salt_is_not_setup(self, vm):
        assert vm.is_setup({"vault": {"verifier": "abc"}}) is False

    def test_setup_returns_is_setup(self, vm, setup_config):
        assert vm.is_setup(setup_config) is True


class TestSetup:
    def test_setup_populates_salt_and_verifier(self, vm):
        cfg = vm.setup("my-password", {})
        assert cfg["vault"]["salt"]
        assert cfg["vault"]["verifier"]

    def test_setup_unlocks_vault(self, vm):
        vm.setup("my-password", {})
        assert vm.is_unlocked() is True

    def test_two_setups_produce_different_salts(self, vm):
        cfg1 = vm.setup("pass", {})
        vm.lock()
        cfg2 = vm.setup("pass", {})
        assert cfg1["vault"]["salt"] != cfg2["vault"]["salt"]

    def test_setup_preserves_existing_config_keys(self, vm):
        cfg = vm.setup("pass", {"program_name": "QSnippet"})
        assert cfg["program_name"] == "QSnippet"

    def test_setup_with_recovery_code_stores_verifier(self, vm):
        cfg = vm.setup("pass", {}, recovery_code="abcd-ef01-2345-6789-abcd")
        assert cfg["vault"].get("rec_verifier")
        assert cfg["vault"].get("rec_salt")
        assert cfg["vault"].get("rec_key_blob")

    def test_setup_without_recovery_code_no_rec_material(self, vm):
        cfg = vm.setup("pass", {})
        assert "rec_verifier" not in cfg["vault"]
        assert "rec_key_blob" not in cfg["vault"]


class TestUnlock:
    def test_correct_password_unlocks(self, vm, setup_config):
        vm.lock()
        assert vm.unlock("correct-password", setup_config) is True
        assert vm.is_unlocked() is True

    def test_wrong_password_rejected(self, vm, setup_config):
        vm.lock()
        assert vm.unlock("wrong-password", setup_config) is False
        assert vm.is_unlocked() is False

    def test_empty_config_returns_false(self, vm):
        assert vm.unlock("any", {}) is False

    def test_corrupt_salt_returns_false(self, vm):
        cfg = {"vault": {"salt": "!!!not-base64!!!", "verifier": "abc"}}
        assert vm.unlock("any", cfg) is False

    def test_wrong_password_does_not_leak_key(self, vm, setup_config):
        vm.lock()
        vm.unlock("wrong", setup_config)
        assert vm.is_unlocked() is False


class TestLock:
    def test_lock_clears_key(self, vm, setup_config):
        assert vm.is_unlocked() is True
        vm.lock()
        assert vm.is_unlocked() is False

    def test_lock_is_idempotent(self, vm):
        vm.lock()
        vm.lock()
        assert vm.is_unlocked() is False


class TestEncryptDecrypt:
    def test_round_trip(self, vm, setup_config):
        plaintext = "super secret snippet"
        cipher = vm.encrypt(plaintext)
        assert vm.decrypt(cipher) == plaintext

    def test_cipher_differs_from_plaintext(self, vm, setup_config):
        cipher = vm.encrypt("hello")
        assert cipher != "hello"

    def test_two_encryptions_produce_different_ciphers(self, vm, setup_config):
        c1 = vm.encrypt("same text")
        c2 = vm.encrypt("same text")
        assert c1 != c2  # different nonces

    def test_encrypt_while_locked_raises(self, vm):
        vm.lock()
        with pytest.raises(VaultError):
            vm.encrypt("text")

    def test_decrypt_while_locked_raises(self, vm, setup_config):
        cipher = vm.encrypt("text")
        vm.lock()
        with pytest.raises(VaultError):
            vm.decrypt(cipher)

    def test_decrypt_tampered_data_raises(self, vm, setup_config):
        import base64
        cipher = vm.encrypt("original")
        data = bytearray(base64.b64decode(cipher))
        data[-1] ^= 0xFF  # flip last byte of auth tag
        tampered = base64.b64encode(bytes(data)).decode()
        with pytest.raises(Exception):
            vm.decrypt(tampered)

    def test_empty_string_round_trip(self, vm, setup_config):
        assert vm.decrypt(vm.encrypt("")) == ""

    def test_unicode_round_trip(self, vm, setup_config):
        text = "héllo wörld"
        assert vm.decrypt(vm.encrypt(text)) == text

    def test_multiline_round_trip(self, vm, setup_config):
        text = "line one\nline two\ttabbed\r\nwindows"
        assert vm.decrypt(vm.encrypt(text)) == text


class TestChangePassword:
    def make_db(self, vm, snippets):
        """Minimal stub DB for change_password tests."""
        class _DB:
            def __init__(self, rows):
                self.rows = rows
                self.content = {r["id"]: r["snippet"] for r in rows}

            def get_vault_snippets(self):
                return list(self.rows)

            def update_snippet_content(self, sid, content):
                self.content[sid] = content
                for r in self.rows:
                    if r["id"] == sid:
                        r["snippet"] = content

            def bulk_update_snippet_content(self, updates):
                for sid, content in updates:
                    self.update_snippet_content(sid, content)

        return _DB(snippets)

    def test_wrong_old_password_returns_false(self, vm, setup_config):
        db = self.make_db(vm, [])
        ok, cfg = vm.change_password("wrong", "new-pass", setup_config, db)
        assert ok is False
        assert cfg is setup_config  # unchanged

    def test_change_password_succeeds(self, vm, setup_config):
        snippets = [{"id": 1, "snippet": vm.encrypt("secret")}]
        db = self.make_db(vm, snippets)
        ok, new_cfg = vm.change_password("correct-password", "new-pass", setup_config, db)
        assert ok is True
        assert new_cfg["vault"]["salt"] != setup_config["vault"]["salt"]

    def test_old_password_rejected_after_change(self, vm, setup_config):
        db = self.make_db(vm, [])
        _, new_cfg = vm.change_password("correct-password", "new-pass", setup_config, db)
        vm.lock()
        assert vm.unlock("correct-password", new_cfg) is False

    def test_new_password_works_after_change(self, vm, setup_config):
        db = self.make_db(vm, [])
        _, new_cfg = vm.change_password("correct-password", "new-pass", setup_config, db)
        vm.lock()
        assert vm.unlock("new-pass", new_cfg) is True

    def test_snippets_re_encrypted_with_new_key(self, vm, setup_config):
        original_text = "my secret snippet"
        snippets = [{"id": 1, "snippet": vm.encrypt(original_text)}]
        db = self.make_db(vm, snippets)

        _, new_cfg = vm.change_password("correct-password", "new-pass", setup_config, db)
        vm.lock()
        vm.unlock("new-pass", new_cfg)
        assert vm.decrypt(db.content[1]) == original_text


class TestDisableVault:
    def make_db(self, vm, snippets):
        class _DB:
            def __init__(self, rows):
                self.rows = list(rows)
                self.content = {r["id"]: r["snippet"] for r in rows}
                self.folders = {r["id"]: r.get("folder", "") for r in rows}
                self.encrypted = {r["id"]: bool(r.get("is_encrypted", True)) for r in rows}
                self.vault_folders_cleared = False

            def get_vault_snippets(self):
                return list(self.rows)

            def update_snippet_content(self, sid, content):
                self.content[sid] = content

            def update_snippet_folder(self, sid, folder):
                self.folders[sid] = folder

            def set_snippet_encrypted(self, sid, flag):
                self.encrypted[sid] = flag

            def set_snippet_vault_uuid(self, sid, vault_uuid):
                pass

            def delete_snippet(self, sid):
                self.rows = [r for r in self.rows if r["id"] != sid]

            def get_all_custom_placeholders(self):
                return []

            def update_custom_placeholder(self, entry):
                return True

            def delete_custom_placeholder(self, placeholder_id):
                return True

            def clear_vault_folders(self):
                self.vault_folders_cleared = True

        return _DB(snippets)

    def test_wrong_password_returns_false(self, vm, setup_config):
        db = self.make_db(vm, [])
        ok, cfg = vm.disable_vault("wrong", setup_config, db, "Unlocked")
        assert ok is False

    def test_disable_clears_vault_config(self, vm, setup_config):
        db = self.make_db(vm, [])
        _, new_cfg = vm.disable_vault("correct-password", setup_config, db, "Unlocked")
        assert new_cfg["vault"]["salt"] == ""
        assert new_cfg["vault"]["verifier"] == ""

    def test_disable_decrypts_snippets(self, vm, setup_config):
        plaintext = "secret content"
        snippets = [{"id": 1, "snippet": vm.encrypt(plaintext), "is_encrypted": True}]
        db = self.make_db(vm, snippets)

        vm.disable_vault("correct-password", setup_config, db, "Unlocked")
        assert db.content[1] == plaintext

    def test_disable_moves_snippets_to_target_folder(self, vm, setup_config):
        snippets = [{"id": 1, "snippet": vm.encrypt("x"), "is_encrypted": True}]
        db = self.make_db(vm, snippets)

        vm.disable_vault("correct-password", setup_config, db, "My Folder")
        assert db.folders[1] == "My Folder"

    def test_disable_marks_snippets_unencrypted(self, vm, setup_config):
        snippets = [{"id": 1, "snippet": vm.encrypt("x"), "is_encrypted": True}]
        db = self.make_db(vm, snippets)

        vm.disable_vault("correct-password", setup_config, db, "Safe")
        assert db.encrypted[1] is False

    def test_disable_clears_vault_folders(self, vm, setup_config):
        db = self.make_db(vm, [])
        vm.disable_vault("correct-password", setup_config, db, "Safe")
        assert db.vault_folders_cleared is True

    def test_disable_locks_vault(self, vm, setup_config):
        db = self.make_db(vm, [])
        vm.disable_vault("correct-password", setup_config, db, "Safe")
        assert vm.is_unlocked() is False

    def test_disable_delete_data_deletes_snippets_instead_of_decrypting(self, vm, setup_config):
        snippets = [{"id": 1, "snippet": vm.encrypt("x"), "is_encrypted": True}]
        db = self.make_db(vm, snippets)

        ok, _ = vm.disable_vault(
            "correct-password", setup_config, db, "", delete_data=True
        )
        assert ok is True
        assert db.rows == []

    def test_disable_delete_data_still_clears_vault_folders(self, vm, setup_config):
        db = self.make_db(vm, [])
        vm.disable_vault("correct-password", setup_config, db, "", delete_data=True)
        assert db.vault_folders_cleared is True


class TestExportEncryption:
    """Tests for the portable export encryption helpers (independent of vault state)."""

    def test_encrypt_export_returns_required_fields(self):
        header = VaultManager.encrypt_export(b"hello", "password")
        assert "kdf_salt" in header
        assert "kdf_iterations" in header
        assert "data" in header

    def test_encrypt_export_iterations_value(self):
        header = VaultManager.encrypt_export(b"data", "pw")
        assert header["kdf_iterations"] == 600_000

    def test_decrypt_export_round_trip(self):
        original = b"some sensitive snippet data"
        header = VaultManager.encrypt_export(original, "my-export-password")
        result = VaultManager.decrypt_export(header, "my-export-password")
        assert result == original

    def test_decrypt_export_wrong_password_raises(self):
        header = VaultManager.encrypt_export(b"secret", "correct-pw")
        with pytest.raises(Exception):
            VaultManager.decrypt_export(header, "wrong-pw")

    def test_two_exports_have_different_salts(self):
        h1 = VaultManager.encrypt_export(b"data", "pw")
        h2 = VaultManager.encrypt_export(b"data", "pw")
        assert h1["kdf_salt"] != h2["kdf_salt"]

    def test_decrypt_export_missing_field_raises_value_error(self):
        with pytest.raises(ValueError, match="Malformed export header"):
            VaultManager.decrypt_export({}, "pw")

    def test_encrypt_export_produces_decodable_base64(self):
        import base64
        header = VaultManager.encrypt_export(b"x", "pw")
        base64.b64decode(header["kdf_salt"])  # must not raise
        base64.b64decode(header["data"])

    def test_round_trip_unicode_content(self):
        original = "secret with ünïcödé".encode("utf-8")
        header = VaultManager.encrypt_export(original, "pw")
        assert VaultManager.decrypt_export(header, "pw") == original

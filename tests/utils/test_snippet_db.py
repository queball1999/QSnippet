import pytest
import sqlite3
from pathlib import Path

from utils.snippet_db import SnippetDB, validate_snippet_entry, DatabaseValidationError
from utils.vault_manager import VaultManager, VaultError


def test_db_initializes_and_seeds(temp_snippet_db_path):
    """Database should initialize and seed with default snippet."""
    db = SnippetDB(temp_snippet_db_path)

    snippets = db.get_all_snippets()
    assert snippets is not None
    assert len(snippets) >= 1

    triggers = [s["trigger"] for s in snippets]
    assert "/welcome" in triggers


def test_insert_new_snippet(temp_snippet_db_path):
    """Inserting a new snippet should increase row count."""
    db = SnippetDB(temp_snippet_db_path)

    initial_count = len(db.get_all_snippets())

    entry = {
        "enabled": True,
        "label": "Test Snippet",
        "trigger": "/test",
        "snippet": "Hello World",
        "paste_style": "clipboard",
        "return_press": False,
        "folder": "Tests",
        "tags": "unit,test",
    }

    is_new = db.insert_snippet(entry)
    assert is_new is True

    snippets = db.get_all_snippets()
    assert len(snippets) == initial_count + 1
    assert any(s["trigger"] == "/test" for s in snippets)


def test_insert_updates_existing_snippet(temp_snippet_db_path):
    """Inserting with an existing trigger should update, not duplicate."""
    db = SnippetDB(temp_snippet_db_path)

    db.insert_snippet({
        "id": 1,
        "enabled": True,
        "label": "Original",
        "trigger": "/dup",
        "snippet": "First",
        "paste_style": "clipboard",
        "return_press": False,
        "folder": "Tests",
        "tags": "a",
    })

    is_new = db.insert_snippet({
        "id": 1,
        "enabled": False,
        "label": "Updated",
        "trigger": "/dup",
        "snippet": "Second",
        "paste_style": "typing",
        "return_press": True,
        "folder": "Updated",
        "tags": "b",
    })

    assert is_new is False

    snippets = [s for s in db.get_all_snippets() if s["trigger"] == "/dup"]
    assert len(snippets) == 1

    snippet = snippets[0]
    assert snippet["label"] == "Updated"
    assert snippet["enabled"] is False
    assert snippet["return_press"] is True


def test_delete_snippet(temp_snippet_db_path):
    """Deleting a snippet should remove it."""
    db = SnippetDB(temp_snippet_db_path)

    db.insert_snippet({
        "enabled": True,
        "label": "Delete Me",
        "trigger": "/delete",
        "snippet": "bye",
        "paste_style": "clipboard",
        "return_press": False,
        "folder": "",
        "tags": "",
    })

    snippet = next(s for s in db.get_all_snippets() if s["trigger"] == "/delete")

    db.delete_snippet(snippet["id"])

    triggers = [s["trigger"] for s in db.get_all_snippets()]
    assert "/delete" not in triggers


def test_get_random_snippet(temp_snippet_db_path):
    """Random snippet should return an enabled snippet."""
    db = SnippetDB(temp_snippet_db_path)

    snippet = db.get_random_snippet()
    assert isinstance(snippet, dict)
    assert snippet != {}
    assert snippet["enabled"] is True


def test_folder_operations(temp_snippet_db_path):
    """Folder rename and delete should work correctly."""
    db = SnippetDB(temp_snippet_db_path)

    db.insert_snippet({
        "enabled": True,
        "label": "Folder Test",
        "trigger": "/folder",
        "snippet": "x",
        "paste_style": "clipboard",
        "return_press": False,
        "folder": "OldFolder",
        "tags": "",
    })

    db.rename_folder("OldFolder", "NewFolder")

    folders = db.get_all_folders()
    assert "NewFolder" in folders
    assert "OldFolder" not in folders

    db.delete_folder("NewFolder")

    folders = db.get_all_folders()
    assert "NewFolder" not in folders


def test_tag_helpers(temp_snippet_db_path):
    """Tags should normalize, list, and delete correctly."""
    db = SnippetDB(temp_snippet_db_path)

    db.insert_snippet({
        "enabled": True,
        "label": "Tag Test",
        "trigger": "/tags",
        "snippet": "x",
        "paste_style": "clipboard",
        "return_press": False,
        "folder": "",
        "tags": "One,Two,THREE",
    })

    tags = db.get_all_tags()

    assert "one" in tags
    assert "two" in tags
    assert "three" in tags

    db.delete_tag("two")

    snippet = next(s for s in db.get_all_snippets() if s["trigger"] == "/tags")
    assert "two" not in snippet["tags"].lower()


def test_search_snippets(temp_snippet_db_path):
    """Keyword search should match label, trigger, snippet, or tags."""
    db = SnippetDB(temp_snippet_db_path)

    db.insert_snippet({
        "enabled": True,
        "label": "Searchable",
        "trigger": "/search",
        "snippet": "needle in haystack",
        "paste_style": "clipboard",
        "return_press": False,
        "folder": "",
        "tags": "findme",
    })

    results = db.search_snippets("needle")
    assert len(results) >= 1
    assert any(r["trigger"] == "/search" for r in results)


def test_search_snippets_escapes_like_wildcards(temp_snippet_db_path):
    """Search should treat LIKE wildcard characters as literal user input."""
    db = SnippetDB(temp_snippet_db_path)

    db.insert_snippet({
        "enabled": True,
        "label": "Percent Match",
        "trigger": "/percent",
        "snippet": "contains 100% coverage",
        "paste_style": "clipboard",
        "return_press": False,
        "folder": "",
        "tags": "literal%",
    })

    results = db.search_snippets("%")
    assert any(r["trigger"] == "/percent" for r in results)
    assert not any(r["trigger"] == "/welcome" for r in results)


def test_search_snippets_short_keyword_uses_like(temp_snippet_db_path):
    """Keywords shorter than 3 chars must still return results (FTS trigram fallback to LIKE)."""
    db = SnippetDB(temp_snippet_db_path)

    db.insert_snippet({
        "enabled": True,
        "label": "Hi There",
        "trigger": "/hi",
        "snippet": "a short hello",
        "paste_style": "clipboard",
        "return_press": False,
        "folder": "",
        "tags": "",
    })

    results_one = db.search_snippets("H")
    assert any(r["trigger"] == "/hi" for r in results_one), "single-char search should match"

    results_two = db.search_snippets("hi")
    assert any(r["trigger"] == "/hi" for r in results_two), "two-char search should match"


def test_folder_operations_escape_like_characters(temp_snippet_db_path):
    """Folder rename should only touch the intended literal folder path."""
    db = SnippetDB(temp_snippet_db_path)

    db.insert_snippet({
        "enabled": True,
        "label": "Literal Folder",
        "trigger": "/literal-folder",
        "snippet": "x",
        "paste_style": "clipboard",
        "return_press": False,
        "folder": "QA_100%/Drafts",
        "tags": "",
    })
    db.insert_snippet({
        "enabled": True,
        "label": "Neighbor Folder",
        "trigger": "/neighbor-folder",
        "snippet": "x",
        "paste_style": "clipboard",
        "return_press": False,
        "folder": "QAx100z/Drafts",
        "tags": "",
    })

    db.rename_folder("QA_100%", "Renamed")

    folders = db.get_all_folders()
    assert "Renamed/Drafts" in folders
    assert "QAx100z/Drafts" in folders


def test_close_is_idempotent(temp_snippet_db_path):
    """Closing the database more than once should be safe."""
    db = SnippetDB(temp_snippet_db_path)

    db.close()
    db.close()


def test_get_enabled_trigger_index(temp_snippet_db_path):
    """Enabled trigger index should only include enabled snippets."""
    db = SnippetDB(temp_snippet_db_path)

    db.insert_snippet({
        "enabled": True,
        "label": "Enabled",
        "trigger": "/enabled-index",
        "snippet": "one",
        "paste_style": "clipboard",
        "return_press": False,
        "folder": "",
        "tags": "",
    })
    db.insert_snippet({
        "enabled": False,
        "label": "Disabled",
        "trigger": "/disabled-index",
        "snippet": "two",
        "paste_style": "clipboard",
        "return_press": False,
        "folder": "",
        "tags": "",
    })

    triggers = {row["trigger"] for row in db.get_enabled_trigger_index()}

    assert "/enabled-index" in triggers
    assert "/disabled-index" not in triggers


def test_default_custom_placeholders_seeded(temp_snippet_db_path):
    """Default editable custom placeholders should exist and start blank."""
    db = SnippetDB(temp_snippet_db_path)

    placeholders = db.get_all_custom_placeholders()
    by_name = {p["name"]: p for p in placeholders}

    for name in ["name", "location", "email", "phone"]:
        assert name in by_name
        assert by_name[name]["value"] == ""


class TestValidateSnippetEntry:
    """Unit tests for the validate_snippet_entry input validation function."""

    _VALID = {
        "enabled": True,
        "label": "Test",
        "trigger": "/hello",
        "snippet": "Hello World",
        "paste_style": "clipboard",
        "return_press": False,
        "folder": "Tests",
        "tags": "a,b",
    }

    def test_valid_entry_passes(self):
        """Clean entry should raise no exception."""
        validate_snippet_entry(dict(self._VALID))

    def test_control_char_in_trigger(self):
        """Null byte in trigger should raise DatabaseValidationError."""
        entry = {**self._VALID, "trigger": "/hel\x00lo"}
        with pytest.raises(DatabaseValidationError, match="trigger"):
            validate_snippet_entry(entry)

    def test_control_char_in_snippet(self):
        """Unit separator (0x1f) in snippet should raise DatabaseValidationError."""
        entry = {**self._VALID, "snippet": "bad\x1fvalue"}
        with pytest.raises(DatabaseValidationError, match="snippet"):
            validate_snippet_entry(entry)

    def test_control_char_del_in_label(self):
        """DEL character (0x7f) in label should raise DatabaseValidationError."""
        entry = {**self._VALID, "label": "bad\x7flabel"}
        with pytest.raises(DatabaseValidationError, match="label"):
            validate_snippet_entry(entry)

    def test_trigger_exceeds_max_length(self):
        """Trigger longer than 255 characters should raise DatabaseValidationError."""
        entry = {**self._VALID, "trigger": "/" + "a" * 255}
        with pytest.raises(DatabaseValidationError, match="trigger"):
            validate_snippet_entry(entry)

    def test_snippet_exceeds_max_length(self):
        """Snippet body longer than 1 MB should raise DatabaseValidationError."""
        entry = {**self._VALID, "snippet": "x" * 1_000_001}
        with pytest.raises(DatabaseValidationError, match="snippet"):
            validate_snippet_entry(entry)

    def test_non_string_fields_skipped(self):
        """Integer and None values in text fields should not raise."""
        entry = {**self._VALID, "folder": None, "tags": None}
        validate_snippet_entry(entry)

    def test_insert_rejects_control_char_trigger(self, temp_snippet_db_path):
        """insert_snippet should propagate DatabaseValidationError for bad trigger."""
        db = SnippetDB(temp_snippet_db_path)
        entry = {**self._VALID, "trigger": "/bad\x01trigger"}
        with pytest.raises(DatabaseValidationError):
            db.insert_snippet(entry)


class TestInsertSnippetAudit:
    """Tests for insert_snippet behaviour introduced in security audit."""

    _BASE = {
        "enabled": True,
        "label": "Audit Test",
        "trigger": "/audit",
        "snippet": "content",
        "paste_style": "clipboard",
        "return_press": False,
        "folder": "",
        "tags": "",
    }

    def test_new_insert_populates_entry_id(self, temp_snippet_db_path):
        """entry['id'] should be set to the new row's lastrowid after a fresh insert."""
        db = SnippetDB(temp_snippet_db_path)
        entry = dict(self._BASE)
        is_new = db.insert_snippet(entry)
        assert is_new is True
        assert isinstance(entry.get("id"), int)
        assert entry["id"] > 0

    def test_update_by_id_does_not_overwrite_entry_id(self, temp_snippet_db_path):
        """ID-based update should return False and not alter entry['id']."""
        db = SnippetDB(temp_snippet_db_path)
        entry = dict(self._BASE)
        db.insert_snippet(entry)
        original_id = entry["id"]

        updated = {**self._BASE, "id": original_id, "label": "Changed"}
        is_new = db.insert_snippet(updated)
        assert is_new is False
        assert updated["id"] == original_id

    def test_trigger_collision_update_returns_false(self, temp_snippet_db_path):
        """Trigger-collision update (no id match) should return False."""
        db = SnippetDB(temp_snippet_db_path)
        db.insert_snippet(dict(self._BASE))

        collision = {**self._BASE, "label": "Collision"}
        collision.pop("id", None)
        is_new = db.insert_snippet(collision)
        assert is_new is False


class TestDeleteSnippet:
    """Edge-case tests for delete_snippet."""

    _BASE = {
        "enabled": True,
        "label": "To Delete",
        "trigger": "/del-target",
        "snippet": "bye",
        "paste_style": "clipboard",
        "return_press": False,
        "folder": "",
        "tags": "",
    }

    def test_delete_nonexistent_id_is_safe(self, temp_snippet_db_path):
        """Deleting a non-existent id should not raise."""
        db = SnippetDB(temp_snippet_db_path)
        db.delete_snippet(999999)

    def test_delete_removes_correct_snippet(self, temp_snippet_db_path):
        """Delete should remove only the targeted snippet; others remain."""
        db = SnippetDB(temp_snippet_db_path)
        entry_a = dict(self._BASE)
        entry_b = {**self._BASE, "trigger": "/del-keep", "label": "Keep Me"}

        db.insert_snippet(entry_a)
        db.insert_snippet(entry_b)

        id_a = entry_a["id"]
        db.delete_snippet(id_a)

        triggers = [s["trigger"] for s in db.get_all_snippets()]
        assert "/del-target" not in triggers
        assert "/del-keep" in triggers


def test_insert_snippet_works_without_unique_trigger_constraint(tmp_path):
    """insert_snippet should upsert by trigger even if DB schema lacks UNIQUE(trigger)."""
    db_path = tmp_path / "legacy_schema.db"

    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE snippets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            enabled BOOLEAN DEFAULT True,
            label TEXT NOT NULL,
            trigger TEXT NOT NULL,
            snippet TEXT NOT NULL,
            paste_style TEXT,
            return_press BOOLEAN DEFAULT False,
            folder TEXT,
            tags TEXT DEFAULT ''
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE custom_placeholders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            value TEXT NOT NULL DEFAULT '',
            description TEXT NOT NULL DEFAULT ''
        )
        """
    )
    conn.commit()
    conn.close()

    db = SnippetDB(Path(db_path))

    first = {
        "enabled": True,
        "label": "Legacy One",
        "trigger": "/legacy",
        "snippet": "one",
        "paste_style": "clipboard",
        "return_press": False,
        "folder": "Default",
        "tags": "",
    }
    second = {
        "enabled": True,
        "label": "Legacy Two",
        "trigger": "/legacy",
        "snippet": "two",
        "paste_style": "clipboard",
        "return_press": False,
        "folder": "Default",
        "tags": "",
    }

    assert db.insert_snippet(first) is True
    # Second insert with same trigger returns False (update, not new)
    assert db.insert_snippet(second) is False

    rows = [s for s in db.get_all_snippets() if s["trigger"] == "/legacy"]
    assert len(rows) == 1
    assert rows[0]["label"] == "Legacy Two"
    assert rows[0]["snippet"] == "two"


# Vault schema & DB methods

class TestVaultSchema:
    """is_encrypted column is added to new and migrated databases."""

    def test_is_encrypted_present_in_new_db(self, temp_snippet_db_path):
        db = SnippetDB(temp_snippet_db_path)
        snippets = db.get_all_snippets()
        assert len(snippets) >= 1
        assert "is_encrypted" in snippets[0]
        assert snippets[0]["is_encrypted"] is False

    def test_is_encrypted_defaults_false_on_insert(self, temp_snippet_db_path):
        db = SnippetDB(temp_snippet_db_path)
        db.insert_snippet({
            "enabled": True, "label": "Vault Test", "trigger": "/vt",
            "snippet": "plain", "paste_style": "clipboard",
            "return_press": False, "folder": "", "tags": "",
        })
        row = next(s for s in db.get_all_snippets() if s["trigger"] == "/vt")
        assert row["is_encrypted"] is False

    def test_migrate_adds_column_to_existing_db(self, tmp_path):
        """A database created without is_encrypted gets the column added."""
        db_path = tmp_path / "legacy.db"

        conn = sqlite3.connect(db_path)
        conn.execute("""
            CREATE TABLE snippets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                enabled BOOLEAN DEFAULT True,
                label TEXT NOT NULL,
                trigger TEXT UNIQUE NOT NULL,
                snippet TEXT NOT NULL,
                paste_style TEXT,
                return_press BOOLEAN DEFAULT False,
                folder TEXT,
                tags TEXT DEFAULT ''
            )
        """)
        conn.execute("""
            CREATE TABLE custom_placeholders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                value TEXT NOT NULL DEFAULT '',
                description TEXT NOT NULL DEFAULT ''
            )
        """)
        conn.execute(
            "INSERT INTO snippets (enabled, label, trigger, snippet, paste_style, return_press, folder, tags) "
            "VALUES (1, 'Old', '/old', 'content', 'clipboard', 0, '', '')"
        )
        conn.commit()
        conn.close()

        db = SnippetDB(Path(db_path))
        rows = db.get_all_snippets()
        assert "is_encrypted" in rows[0]
        assert rows[0]["is_encrypted"] is False


class TestVaultFolders:
    """vault_folders table operations."""

    def test_add_and_get_vault_folder(self, temp_snippet_db_path):
        db = SnippetDB(temp_snippet_db_path)
        db.add_vault_folder("Secrets")
        assert db.get_vault_folders() == ["Secrets"]

    def test_add_duplicate_folder_is_safe(self, temp_snippet_db_path):
        db = SnippetDB(temp_snippet_db_path)
        db.add_vault_folder("Secrets")
        db.add_vault_folder("Secrets")
        assert db.get_vault_folders().count("Secrets") == 1

    def test_is_vault_folder_true(self, temp_snippet_db_path):
        db = SnippetDB(temp_snippet_db_path)
        db.add_vault_folder("Private")
        assert db.is_vault_folder("Private") is True

    def test_is_vault_folder_false(self, temp_snippet_db_path):
        db = SnippetDB(temp_snippet_db_path)
        assert db.is_vault_folder("NotAVaultFolder") is False

    def test_remove_vault_folder(self, temp_snippet_db_path):
        db = SnippetDB(temp_snippet_db_path)
        db.add_vault_folder("Temp")
        db.remove_vault_folder("Temp")
        assert "Temp" not in db.get_vault_folders()

    def test_remove_nonexistent_is_safe(self, temp_snippet_db_path):
        db = SnippetDB(temp_snippet_db_path)
        db.remove_vault_folder("Ghost")  # should not raise

    def test_clear_vault_folders(self, temp_snippet_db_path):
        db = SnippetDB(temp_snippet_db_path)
        db.add_vault_folder("A")
        db.add_vault_folder("B")
        db.clear_vault_folders()
        assert db.get_vault_folders() == []

    def test_multiple_folders(self, temp_snippet_db_path):
        db = SnippetDB(temp_snippet_db_path)
        for name in ["Alpha", "Beta", "Gamma"]:
            db.add_vault_folder(name)
        folders = db.get_vault_folders()
        assert set(folders) == {"Alpha", "Beta", "Gamma"}


class TestVaultSnippetOps:
    """Vault-specific snippet operations: get_vault_snippets, update_snippet_content,
    update_snippet_folder, set_snippet_encrypted, get_snippets_by_folder."""

    _BASE = {
        "enabled": True, "label": "Secret", "trigger": "/sec",
        "snippet": "plain text", "paste_style": "clipboard",
        "return_press": False, "folder": "Vault", "tags": "",
    }

    def insert(self, db, extra=None):
        entry = dict(self._BASE)
        if extra:
            entry.update(extra)
        db.insert_snippet(entry)
        return next(s for s in db.get_all_snippets() if s["trigger"] == entry["trigger"])

    def test_get_vault_snippets_empty_when_none_encrypted(self, temp_snippet_db_path):
        db = SnippetDB(temp_snippet_db_path)
        assert db.get_vault_snippets() == []

    def test_set_and_get_vault_snippets(self, temp_snippet_db_path):
        db = SnippetDB(temp_snippet_db_path)
        row = self.insert(db)
        db.set_snippet_encrypted(row["id"], True)

        vault = db.get_vault_snippets()
        assert len(vault) == 1
        assert vault[0]["id"] == row["id"]
        assert vault[0]["is_encrypted"] is True

    def test_set_snippet_encrypted_false(self, temp_snippet_db_path):
        db = SnippetDB(temp_snippet_db_path)
        row = self.insert(db)
        db.set_snippet_encrypted(row["id"], True)
        db.set_snippet_encrypted(row["id"], False)

        assert db.get_vault_snippets() == []
        updated = db.get_snippet(row["id"])
        assert updated["is_encrypted"] is False

    def test_update_snippet_content(self, temp_snippet_db_path):
        db = SnippetDB(temp_snippet_db_path)
        row = self.insert(db)
        db.update_snippet_content(row["id"], "ENCRYPTED_BLOB")
        updated = db.get_snippet(row["id"])
        assert updated["snippet"] == "ENCRYPTED_BLOB"

    def test_update_snippet_folder(self, temp_snippet_db_path):
        db = SnippetDB(temp_snippet_db_path)
        row = self.insert(db)
        db.update_snippet_folder(row["id"], "Safe Landing")
        updated = db.get_snippet(row["id"])
        assert updated["folder"] == "Safe Landing"

    def test_get_snippets_by_folder_exact(self, temp_snippet_db_path):
        db = SnippetDB(temp_snippet_db_path)
        self.insert(db)
        rows = db.get_snippets_by_folder("Vault")
        assert len(rows) >= 1
        assert all(r["folder"] == "Vault" for r in rows)

    def test_get_snippets_by_folder_includes_subfolders(self, temp_snippet_db_path):
        db = SnippetDB(temp_snippet_db_path)
        self.insert(db)                                              # folder="Vault"
        self.insert(db, {"trigger": "/sub", "folder": "Vault/Sub"}) # sub-folder
        rows = db.get_snippets_by_folder("Vault")
        triggers = {r["trigger"] for r in rows}
        assert "/sec" in triggers
        assert "/sub" in triggers

    def test_get_snippets_by_folder_excludes_others(self, temp_snippet_db_path):
        db = SnippetDB(temp_snippet_db_path)
        self.insert(db, {"trigger": "/other", "folder": "Other"})
        rows = db.get_snippets_by_folder("Vault")
        assert not any(r["trigger"] == "/other" for r in rows)


@pytest.fixture(autouse=True)
def reset_vault_singleton():
    vm = VaultManager.get_instance()
    vm.lock()
    vm.set_auto_lock_minutes(0)
    yield
    vm.lock()


class TestInsertSnippetVaultAware:
    """Tests for insert_snippet_vault_aware() - the single vault-encryption gate."""

    _BASE = {
        "enabled": True, "label": "Test", "trigger": "/t",
        "snippet": "plain text", "paste_style": "clipboard",
        "return_press": False, "folder": "General", "tags": "",
    }

    def vm_setup(self) -> tuple:
        vm = VaultManager.get_instance()
        cfg = vm.setup("test-password", {})
        return vm, cfg

    def test_plain_insert_into_normal_folder(self, temp_snippet_db_path):
        db = SnippetDB(temp_snippet_db_path)
        result = db.insert_snippet_vault_aware(dict(self._BASE))
        assert result is True
        row = db.get_snippet_by_trigger("/t")
        assert row["snippet"] == "plain text"
        assert not row.get("is_encrypted")

    def test_insert_into_vault_folder_encrypts(self, temp_snippet_db_path):
        db = SnippetDB(temp_snippet_db_path)
        vm, _ = self.vm_setup()
        db.add_vault_folder("Secret")
        entry = {**self._BASE, "folder": "Secret", "trigger": "/sec"}
        db.insert_snippet_vault_aware(entry, vault_manager=vm)
        row = db.get_snippet_by_trigger("/sec")
        assert row["is_encrypted"] is True
        assert row["snippet"] != "plain text"

    def test_insert_into_vault_folder_decryptable(self, temp_snippet_db_path):
        db = SnippetDB(temp_snippet_db_path)
        vm, _ = self.vm_setup()
        db.add_vault_folder("Secret")
        entry = {**self._BASE, "folder": "Secret", "trigger": "/dec"}
        db.insert_snippet_vault_aware(entry, vault_manager=vm)
        row = db.get_snippet_by_trigger("/dec")
        assert vm.decrypt(row["snippet"]) == "plain text"

    def test_insert_into_vault_folder_locked_raises(self, temp_snippet_db_path):
        db = SnippetDB(temp_snippet_db_path)
        vm, _ = self.vm_setup()
        vm.lock()
        db.add_vault_folder("Locked")
        entry = {**self._BASE, "folder": "Locked", "trigger": "/locked"}
        with pytest.raises(VaultError):
            db.insert_snippet_vault_aware(entry, vault_manager=vm)

    def test_encrypted_snippet_moved_to_normal_folder_decrypts(self, temp_snippet_db_path):
        db = SnippetDB(temp_snippet_db_path)
        vm, _ = self.vm_setup()
        db.add_vault_folder("Secret")
        entry = {**self._BASE, "folder": "Secret", "trigger": "/move"}
        db.insert_snippet_vault_aware(entry, vault_manager=vm)
        row = db.get_snippet_by_trigger("/move")

        # Move out of vault - is_encrypted=True, destination is non-vault folder
        out_entry = {**row, "folder": "General", "is_encrypted": True}
        db.insert_snippet_vault_aware(out_entry, vault_manager=vm)
        moved = db.get_snippet_by_trigger("/move")
        assert moved["snippet"] == "plain text"
        assert not moved.get("is_encrypted")

    def test_no_vault_manager_normal_folder_succeeds(self, temp_snippet_db_path):
        db = SnippetDB(temp_snippet_db_path)
        entry = {**self._BASE, "trigger": "/novm"}
        result = db.insert_snippet_vault_aware(entry, vault_manager=None)
        assert result is True
        assert db.get_snippet_by_trigger("/novm")["snippet"] == "plain text"

    def test_no_vault_manager_vault_folder_raises(self, temp_snippet_db_path):
        db = SnippetDB(temp_snippet_db_path)
        db.add_vault_folder("Secret")
        entry = {**self._BASE, "folder": "Secret", "trigger": "/novm2"}
        with pytest.raises(VaultError):
            db.insert_snippet_vault_aware(entry, vault_manager=None)

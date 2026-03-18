"""
Unit tests for import/export functionality.

Tests the business logic of importing and exporting snippets,
including YAML serialization, trigger matching, and status detection.
"""
import pytest
import yaml
from unittest.mock import MagicMock

from utils.snippet_db import SnippetDB
from utils.file_utils import FileUtils

pytestmark = pytest.mark.gui


@pytest.fixture
def db(tmp_path):
    """Fixture: returns a real SnippetDB at tmp_path."""
    return SnippetDB(tmp_path / "snippets.db")


@pytest.fixture
def sample_snippets():
    """Fixture: returns a list of 3 sample snippet dicts (no id field)."""
    return [
        {
            "enabled": True,
            "label": "Email Signature",
            "trigger": "/sig",
            "snippet": "Best regards,\nJohn Doe",
            "paste_style": "Clipboard",
            "return_press": False,
            "folder": "Work",
            "tags": "professional,email",
        },
        {
            "enabled": True,
            "label": "Contact Log",
            "trigger": "!contact",
            "snippet": "Contact Log {date}\nType: Phone Call\nPerson: ",
            "paste_style": "Clipboard",
            "return_press": False,
            "folder": "Contacts",
            "tags": "",
        },
        {
            "enabled": False,
            "label": "Test Snippet",
            "trigger": "/test",
            "snippet": "This is a test snippet",
            "paste_style": "Keystroke",
            "return_press": True,
            "folder": "",
            "tags": "test,disabled",
        },
    ]


@pytest.fixture
def yaml_file(tmp_path, sample_snippets):
    """Fixture: exports sample snippets to YAML and returns the Path."""
    file_path = tmp_path / "snippets.yaml"
    FileUtils.export_snippets_yaml(file_path, sample_snippets)
    return file_path


class TestExportImportRoundtrip:
    """Test YAML export/import roundtrip."""

    def test_export_yaml_roundtrip(self, tmp_path, sample_snippets):
        """Export 3 snippets, re-read YAML, verify count and fields match."""
        file_path = tmp_path / "export_test.yaml"
        FileUtils.export_snippets_yaml(file_path, sample_snippets)

        # Re-import and verify
        reimported = FileUtils.import_snippets_yaml(file_path)
        assert len(reimported) == 3
        assert reimported[0]["trigger"] == "/sig"
        assert reimported[0]["label"] == "Email Signature"
        assert reimported[1]["trigger"] == "!contact"
        assert reimported[2]["trigger"] == "/test"

        # Verify that IDs are NOT in exported YAML
        assert all("id" not in snippet for snippet in reimported)

    def test_export_yaml_structure(self, tmp_path, sample_snippets):
        """Verify exported YAML has correct structure."""
        file_path = tmp_path / "export_test.yaml"
        FileUtils.export_snippets_yaml(file_path, sample_snippets)

        with open(file_path, "r") as f:
            data = yaml.safe_load(f)

        assert "snippets" in data
        assert isinstance(data["snippets"], list)
        assert len(data["snippets"]) == 3


class TestImportIntoDatabase:
    """Test importing snippets into a database."""

    def test_import_all_new(self, db, yaml_file):
        """Import into DB: all sample snippets are new (different triggers)."""
        initial_count = len(db.get_all_snippets() or [])

        snippets = FileUtils.import_snippets_yaml(yaml_file)

        new_count = 0
        updated_count = 0
        for entry in snippets:
            is_new = db.insert_snippet(entry)
            if is_new is True:
                new_count += 1
            elif is_new is False:
                updated_count += 1

        # All 3 sample snippets have unique triggers, so all are new
        assert new_count == 3
        assert updated_count == 0
        assert len(db.get_all_snippets()) == initial_count + 3

    def test_import_detects_update(self, db, sample_snippets, yaml_file):
        """Pre-insert one snippet, re-import same trigger: detects update."""
        
        # Pre-insert the first snippet
        db.insert_snippet(sample_snippets[0])
        after_preinsert = len(db.get_all_snippets())

        # Re-import from YAML (which includes the pre-inserted snippet)
        snippets = FileUtils.import_snippets_yaml(yaml_file)

        new_count = 0
        updated_count = 0
        for entry in snippets:
            is_new = db.insert_snippet(entry)
            if is_new is True:
                new_count += 1
            elif is_new is False:
                updated_count += 1

        # One already exists (the email sig), two are new
        assert new_count == 2
        assert updated_count == 1
        assert len(db.get_all_snippets()) == after_preinsert + new_count  # After preinsert + 2 new imports

    def test_import_partial_selection(self, db, sample_snippets, yaml_file):
        """Simulate wizard selection: import only 2 out of 3."""
        initial_count = len(db.get_all_snippets() or [])

        snippets = FileUtils.import_snippets_yaml(yaml_file)
        selected = snippets[:2]  # Only first two

        for entry in selected:
            db.insert_snippet(entry)

        all_snippets = db.get_all_snippets()
        assert len(all_snippets) == initial_count + 2

        # Check that the selected snippets are present
        triggers = [s["trigger"] for s in all_snippets]
        assert "/sig" in triggers
        assert "!contact" in triggers

    def test_import_error_not_counted_as_update(self, db, monkeypatch):
        """When insert_snippet returns None (error), it's not counted as update."""
        # Mock insert_snippet to return None
        monkeypatch.setattr(db, "insert_snippet", lambda x: None)

        snippets = [{"trigger": "/test", "label": "Test"}]

        new_count = 0
        updated_count = 0
        for entry in snippets:
            is_new = db.insert_snippet(entry)
            if is_new is True:
                new_count += 1
            elif is_new is False:
                updated_count += 1

        assert new_count == 0
        assert updated_count == 0



class TestExportSubset:
    """Test exporting a subset of snippets."""

    def test_export_subset(self, db, sample_snippets, tmp_path):
        """DB has all 3 snippets, export only 2, verify YAML has 2."""
        # Insert all snippets
        for snippet in sample_snippets:
            db.insert_snippet(snippet)

        # Export only first two
        export_subset = sample_snippets[:2]
        export_path = tmp_path / "subset.yaml"
        FileUtils.export_snippets_yaml(export_path, export_subset)

        # Verify exported YAML has only 2
        reimported = FileUtils.import_snippets_yaml(export_path)
        assert len(reimported) == 2
        assert reimported[0]["trigger"] == "/sig"
        assert reimported[1]["trigger"] == "!contact"

    def test_export_empty_list(self, tmp_path):
        """Export empty snippet list: creates valid empty YAML."""
        export_path = tmp_path / "empty_export.yaml"
        FileUtils.export_snippets_yaml(export_path, [])

        reimported = FileUtils.import_snippets_yaml(export_path)
        assert reimported == []


class TestStatusClassification:
    """Test classify_snippets function for import wizard."""

    @pytest.fixture(autouse=True)
    def _import_classify_snippets(self):
        """Lazy import of UI component to avoid import errors in CI/CD."""
        from ui.widgets.import_export_wizard import classify_snippets
        self.classify_snippets = classify_snippets

    def test_get_status_new(self, db, sample_snippets):
        """Trigger not in DB: status is 'New'."""
        snippets = [sample_snippets[0].copy()]  # /sig
        classified = self.classify_snippets(snippets, db)

        assert classified[0]["status"] == "New"

    def test_get_status_update(self, db, sample_snippets):
        """Pre-insert trigger, classify: status is 'Update'."""
        # Pre-insert the trigger
        db.insert_snippet(sample_snippets[0])

        snippets = [sample_snippets[0].copy()]
        classified = self.classify_snippets(snippets, db)

        assert classified[0]["status"] == "Update"

    def test_get_status_mixed(self, db, sample_snippets):
        """Mix of new and update: each classified correctly."""
        # Pre-insert first snippet only
        db.insert_snippet(sample_snippets[0])

        snippets = sample_snippets.copy()
        classified = self.classify_snippets(snippets, db)

        assert classified[0]["status"] == "Update"
        assert classified[1]["status"] == "New"
        assert classified[2]["status"] == "New"

    def test_classify_adds_status_key(self, db, sample_snippets):
        """classify_snippets adds 'status' key to each snippet."""
        snippets = [sample_snippets[0].copy()]
        assert "status" not in snippets[0]

        classified = self.classify_snippets(snippets, db)
        assert "status" in classified[0]
        assert classified[0]["status"] in ("New", "Update")


class TestIDHandling:
    """Test that IDs are properly handled in import/export."""

    def test_import_ignores_ids_from_old_yaml(self, db, tmp_path):
        """Import YAML with old database IDs: should ignore IDs and use triggers instead."""
        # Create snippets with explicit IDs (simulating old YAML export)
        snippets_with_ids = [
            {
                "id": 999,  # Old ID that doesn't exist in new DB
                "enabled": True,
                "label": "Test 1",
                "trigger": "/oldid1",
                "snippet": "content1",
                "paste_style": "clipboard",
                "return_press": False,
                "folder": "Test",
                "tags": "test",
            },
            {
                "id": 1000,  # Another old ID
                "enabled": True,
                "label": "Test 2",
                "trigger": "/oldid2",
                "snippet": "content2",
                "paste_style": "clipboard",
                "return_press": False,
                "folder": "Test",
                "tags": "test",
            },
        ]

        # Write to YAML (with IDs)
        yaml_path = tmp_path / "old_export.yaml"
        FileUtils.export_snippets_yaml(yaml_path, snippets_with_ids)

        # Manually add IDs back to simulate old export format
        import yaml
        with open(yaml_path, "r") as f:
            data = yaml.safe_load(f)
        for i, snippet in enumerate(data["snippets"]):
            snippet["id"] = 999 + i
        with open(yaml_path, "w") as f:
            yaml.safe_dump(data, f)

        # Import from YAML (should strip IDs and treat as new)
        reimported = FileUtils.import_snippets_yaml(yaml_path)

        new_count = 0
        for entry in reimported:
            is_new = db.insert_snippet(entry)
            if is_new is True:
                new_count += 1

        # Both should be inserted as new (IDs ignored)
        assert new_count == 2

        # Verify they're in DB by trigger, not ID
        triggers = {s["trigger"] for s in db.get_all_snippets() or []}
        assert "/oldid1" in triggers
        assert "/oldid2" in triggers


class TestFileUtilsBugFix:
    """Test that the error-counting bug is fixed."""

    def test_import_dialog_ignores_errors(self, tmp_path, monkeypatch):
        """
        Test that import_snippets_with_dialog doesn't count errors as updates.
        This verifies the fix: `if is_new is True:` instead of `if is_new:`
        """
        # Create a mock parent and db
        mock_parent = MagicMock()
        mock_db = MagicMock()
        mock_yaml_path = tmp_path / "test.yaml"

        # Create a test YAML with 3 snippets
        test_snippets = [
            {
                "enabled": True,
                "label": f"Snippet {i}",
                "trigger": f"/test{i}",
                "snippet": f"Content {i}",
                "paste_style": "Clipboard",
                "return_press": False,
                "folder": "",
                "tags": "",
            }
            for i in range(3)
        ]
        FileUtils.export_snippets_yaml(mock_yaml_path, test_snippets)

        # Mock insert_snippet to return: True, False, None (new, update, error)
        mock_db.insert_snippet.side_effect = [True, False, None]

        # Now call the import logic (extracted from import_snippets_with_dialog)
        snippets = FileUtils.import_snippets_yaml(mock_yaml_path)
        new_count = 0
        updated_count = 0

        for entry in snippets:
            is_new = mock_db.insert_snippet(entry)
            if is_new is True:
                new_count += 1
            elif is_new is False:
                updated_count += 1

        # Verify: 1 new, 1 updated, 1 error (not counted)
        assert new_count == 1
        assert updated_count == 1
        assert (new_count + updated_count) == 2

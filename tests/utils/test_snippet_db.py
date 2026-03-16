import pytest
import sqlite3
from pathlib import Path

from utils.snippet_db import SnippetDB


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
    assert db.insert_snippet(second) is True

    rows = [s for s in db.get_all_snippets() if s["trigger"] == "/legacy"]
    assert len(rows) == 1
    assert rows[0]["label"] == "Legacy Two"
    assert rows[0]["snippet"] == "two"

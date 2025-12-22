import pytest

from utils.snippet_db import SnippetDB


def test_db_initializes_and_seeds(temp_snippet_db_path):
    """
    Database should initialize and seed with default snippet.
    """
    db = SnippetDB(temp_snippet_db_path)

    snippets = db.get_all_snippets()
    assert snippets is not None
    assert len(snippets) >= 1

    triggers = [s["trigger"] for s in snippets]
    assert "/welcome" in triggers


def test_insert_new_snippet(temp_snippet_db_path):
    """
    Inserting a new snippet should increase row count.
    """
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
    """
    Inserting with an existing trigger should update, not duplicate.
    """
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
    """
    Deleting a snippet should remove it.
    """
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
    """
    Random snippet should return an enabled snippet.
    """
    db = SnippetDB(temp_snippet_db_path)

    snippet = db.get_random_snippet()
    assert isinstance(snippet, dict)
    assert snippet != {}
    assert snippet["enabled"] is True


def test_folder_operations(temp_snippet_db_path):
    """
    Folder rename and delete should work correctly.
    """
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
    """
    Tags should normalize, list, and delete correctly.
    """
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
    """
    Keyword search should match label, trigger, snippet, or tags.
    """
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

import sqlite3
import logging
import random
from pathlib import Path
from typing import List, Dict, Any

from .file_utils import FileUtils

logger = logging.getLogger(__name__)



class SnippetDB:
    DEFAULT_CUSTOM_PLACEHOLDERS = [
        {
            "name": "name",
            "value": "",
            "description": "Your name (editable, blank by default)",
        },
        {
            "name": "location",
            "value": "",
            "description": "Your location (editable, blank by default)",
        },
        {
            "name": "email",
            "value": "",
            "description": "Your email address (editable, blank by default)",
        },
        {
            "name": "phone",
            "value": "",
            "description": "Your phone number (editable, blank by default)",
        },
    ]

    def __init__(self, db_path: Path) -> None:
        """
        Initialize the SnippetDB instance.

        Establishes a SQLite connection, ensures required tables and indexes
        exist, and seeds the database with default snippets if empty.

        Args:
            db_path (Path): Path to the SQLite database file.

        Returns:
            None
        """
        logger.info("Initializing SnippetDB")
        self.db_path = db_path
        logger.debug("SQLite path: %s", db_path)
        self.conn = sqlite3.connect(self.db_path)
        self.create_table()
        self.create_indexes()
        self.create_custom_placeholders_table()
        self.seed_default_custom_placeholders()
        self.seed_empty_db()
        logger.info("SnippetDB initialized successfully")

    def create_table(self) -> None:
        """
        Create the snippets table if it does not exist.

        Returns:
            None
        """
        logger.info("Ensuring snippet table exists in database")
        try:
            with self.conn:
                self.conn.execute("""
                    CREATE TABLE IF NOT EXISTS snippets (
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
            logger.info("Snippet table should now exist in database")
        except Exception:
            logger.exception("An error occurred while ensuring snippet table exists in database")
            return None

    def create_indexes(self) -> None:
        """
        Create database indexes to improve query performance.

        Returns:
            None
        """
        logger.info("Ensuring indexes exists in database")
        try:
            with self.conn:
                self.conn.execute("CREATE INDEX IF NOT EXISTS idx_snippets_enabled ON snippets(enabled);")
                self.conn.execute("CREATE INDEX IF NOT EXISTS idx_snippets_folder ON snippets(folder);")
                self.conn.execute("CREATE INDEX IF NOT EXISTS idx_snippets_label ON snippets(label);")
                self.conn.execute("CREATE INDEX IF NOT EXISTS idx_snippets_tags ON snippets(tags);")

                logger.info("Indexes should now exist in database")
        except Exception:
            logger.exception("An error occurred while ensuring indexes exist in database")
            return None

    def seed_empty_db(self) -> None:
        """
        Seed the database with default snippets if it is empty.

        Returns:
            None
        """
        logger.info("Checking to see if the database needs to be seeded.")
        try:
            cur = self.conn.cursor()
            cur.execute("SELECT COUNT(*) FROM snippets")
            count = cur.fetchone()[0]

            if count > 0:
                logger.info("Database has already been seeded. Skipping...")
                return  # DB already has snippets, do nothing
        
        except Exception:
            logger.exception("An error occurred while checking whether the database needs seeding")
            return

        default_snippets = [
            {
                "enabled": True,
                "label": "Welcome Snippet",
                "trigger": "/welcome",
                "snippet": "Welcome to QSnippet! Click `New Snippet` below to create your first snippet.",
                "paste_style": "clipboard",
                "return_press": False,
                "folder": "Getting Started",
                "tags": "default,example",
            }
        ]

        logger.info("Attempting to seed the database with default snippets")
        logger.debug("Default snippet seed count: %d", len(default_snippets))
        try:
            with self.conn:
                for entry in default_snippets:
                    self.conn.execute(
                        """
                        INSERT INTO snippets
                        (enabled, label, trigger, snippet, paste_style, return_press, folder, tags)
                        VALUES
                        (:enabled, :label, :trigger, :snippet, :paste_style, :return_press, :folder, :tags)
                        """,
                        entry,
                    )
                logger.info("The database has been seeded successfully!")

        except Exception:
            logger.exception("An error occurred while seeding the database")
            return

    # CRUD Operations
    def insert_snippet(self, entry: Dict[str, Any]) -> bool:
        """
        Insert a new snippet or update an existing one.

        If an entry with the same id exists, it is updated. Otherwise,
        a new snippet is inserted. Conflicts on trigger result in an update.

        Args:
            entry (Dict[str, Any]): Snippet data to insert or update.

        Returns:
            bool | None: True if a new snippet was created, False if updated,
                or None if an error occurred.
        """
        logger.info("Inserting snippet into the database")
        logger.debug(
            "Snippet entry fields: id=%s trigger=%s folder=%s enabled=%s",
            entry.get("id"),
            entry.get("trigger"),
            entry.get("folder"),
            entry.get("enabled"),
        )
        entry_id = entry.get("id")

        # Commenting out as this breaks making new snippets
        """ if entry_id is None:
            logger.info("No valid entry id was detected. Skipping...")
            return None """
        
        try:
            with self.conn:
                cur = self.conn.cursor()
                cur.execute("SELECT 1 FROM snippets WHERE id = ?", (entry_id,))
                exists = cur.fetchone() is not None

                if exists:  # update existing
                    logger.info("Found existing snippet. Updating entry.")
                    self.conn.execute("""
                        UPDATE snippets
                        SET
                            enabled = :enabled,
                            label = :label,
                            trigger = :trigger,
                            snippet = :snippet,
                            paste_style = :paste_style,
                            return_press = :return_press,
                            folder = :folder,
                            tags = :tags
                        WHERE id = :id
                    """, entry)
                    
                else:   # insert new snippet
                    logger.info("No existing snippet id found; checking for existing trigger")

                    trigger = entry.get("trigger")
                    cur.execute(
                        "SELECT id FROM snippets WHERE trigger = ?",
                        (trigger,),
                    )
                    trigger_row = cur.fetchone()

                    if trigger_row:
                        logger.info(
                            "Existing snippet found for trigger '%s' (id=%s). Updating entry.",
                            trigger,
                            trigger_row[0],
                        )
                        update_entry = dict(entry)
                        update_entry["id"] = trigger_row[0]
                        self.conn.execute("""
                            UPDATE snippets
                            SET
                                enabled = :enabled,
                                label = :label,
                                trigger = :trigger,
                                snippet = :snippet,
                                paste_style = :paste_style,
                                return_press = :return_press,
                                folder = :folder,
                                tags = :tags
                            WHERE id = :id
                        """, update_entry)
                    else:
                        logger.info("No existing trigger found. Inserting new entry.")
                        self.conn.execute("""
                            INSERT INTO snippets (enabled, label, trigger, snippet, paste_style, return_press, folder, tags)
                            VALUES (:enabled, :label, :trigger, :snippet, :paste_style, :return_press, :folder, :tags)
                        """, entry)

                logger.info("Snippet created successfully.")
                return not exists   # True if it was new
            
        except Exception:
            logger.exception("An error occurred while inserting a snippet into the database")
            return None

    def delete_snippet(self, snippet_id: id) -> None:
        """
        Delete a snippet from the database.

        Args:
            snippet_id (id): The identifier of the snippet to delete.

        Returns:
            None
        """
        logger.info("Deleting snippet from the database.")
        logger.debug("Snippet ID: %s", snippet_id)

        try:
            with self.conn:
                self.conn.execute("DELETE FROM snippets WHERE id = ?", (snippet_id,))
                logger.info("Snippet deleted from the database")

        except Exception:
            logger.exception("An error occurred while deleting a snippet from the database")
            return None

    def get_all_snippets(self) -> List[Dict[str, Any]]:
        """
        Retrieve all snippets from the database.

        Returns:
            List[Dict[str, Any]] | None: A list of snippet dictionaries,
                or None if an error occurred.
        """
        logger.info("Fetching all snippets from the database.")

        try:
            cur = self.conn.cursor()
            cur.execute("SELECT * FROM snippets ORDER BY folder, id")
            columns = [col[0] for col in cur.description]
            rows = cur.fetchall()
            result = []

            for row in rows:
                item = dict(zip(columns, row))
                item["enabled"] = bool(item["enabled"])  # convert 1/0 to True/False
                item["return_press"] = bool(item["return_press"])
                result.append(item)

            logger.info("Successfully fetched all snippets from database.")
            logger.debug("Fetched snippets count: %d", len(result))
            return result
        except Exception:
            logger.exception("An error occurred while retrieving snippets from the database")
            return None

    def get_snippet(self, snippet_id: int) -> Dict[str, Any]:
        """
        Retrieve a single snippet from the database.

        Args:
            snippet_id (int): The identifier used to query the snippet.

        Returns:
            Dict[str, Any] | None: The snippet dictionary if found,
                an empty dictionary if not found, or None if an error occurred.
        """
        logger.info("Fetching snippet from the database.")
        logger.debug("Snippet ID: %s", snippet_id)

        try:
            cur = self.conn.cursor()
            cur.execute("SELECT * FROM snippets WHERE trigger = ?", (snippet_id,))
            row = cur.fetchone()

            if row:
                columns = [col[0] for col in cur.description]
                result = dict(zip(columns, row))
                logger.info("Successfully fetched all snippets from database.")
                logger.debug(
                    "Snippet fetched: id=%s trigger=%s folder=%s",
                    result.get("id"),
                    result.get("trigger"),
                    result.get("folder"),
                )
                return result
            
            logger.info("No entry found for the snippet provided.")
            return {}
        except Exception:
            logger.exception("An error occurred while retrieving a snippet from the database")
            return None
    
    def get_random_snippet(self) -> Dict[str, Any]:
        """
        Retrieve a random enabled snippet.

        Returns:
            Dict[str, Any] | None: A randomly selected snippet dictionary,
                an empty dictionary if none exist, or None if an error occurred.
        """
        logger.info("Fetching random snippet from the database.")

        try:
            cur = self.conn.cursor()
            cur.execute("SELECT * FROM snippets WHERE enabled = 1")
            rows = cur.fetchall()

            if not rows:
                logger.info("No entry found for the snippet.")
                return {}
            
            columns = [col[0] for col in cur.description]
            row = random.choice(rows)
            item = dict(zip(columns, row))
            item["enabled"] = bool(item["enabled"])
            item["return_press"] = bool(item["return_press"])

            logger.info("Successfully fetched random snippets from database.")
            logger.debug(
                "Random snippet selected: id=%s trigger=%s folder=%s",
                item.get("id"),
                item.get("trigger"),
                item.get("folder"),
            )
            return item
        except Exception:
            logger.exception("An error occurred while retrieving a random snippet from the database")
            return None
    
    def rename_folder(self, old_folder: str, new_folder: str) -> None:
        """
        Rename a folder and all nested sub-folders for associated snippets.

        For example, renaming "work" to "office" will also rename
        "work/drafts" to "office/drafts".

        Args:
            old_folder (str): The current folder path (may be nested, e.g. "a/b").
            new_folder (str): The new folder path.

        Returns:
            None
        """
        logger.info("Renaming a folder within the database.")
        logger.debug("Renaming folder: old=%s new=%s", old_folder, new_folder)

        try:
            with self.conn:
                # Rename exact match
                self.conn.execute(
                    "UPDATE snippets SET folder = ? WHERE folder = ?",
                    (new_folder, old_folder)
                )
                # Rename any sub-paths: old_folder/... -> new_folder/...
                self.conn.execute(
                    "UPDATE snippets SET folder = ? || substr(folder, ? + 1) WHERE folder LIKE ?",
                    (new_folder, len(old_folder), old_folder + "/%")
                )
                logger.info("Successfully renamed folder and its sub-folders.")
        except Exception:
            logger.exception("An error occurred while renaming a folder within the database")
            return None
        
    def delete_folder(self, folder: str) -> None:
        """
        Delete all snippets within a specified folder and any nested sub-folders.

        For example, deleting "work" will also delete snippets in "work/drafts".

        Args:
            folder (str): The folder path to delete (may be nested, e.g. "a/b").

        Returns:
            None
        """
        logger.info("Deleting a folder within the database.")
        logger.debug("Folder: %s", folder)

        try:
            with self.conn:
                self.conn.execute(
                    "DELETE FROM snippets WHERE folder = ? OR folder LIKE ?",
                    (folder, folder + "/%")
                )
                logger.info("Successfully deleted folder and its sub-folders.")
        except Exception:
            logger.exception("An error occurred while deleting a folder from the database")
            return None

    def get_all_folders(self) -> List[str]:
        """
        Retrieve all distinct folder names.

        Returns:
            List[str] | None: A list of folder names, or None if an error occurred.
        """
        logger.info("Fetching all folders within the database.")

        try:
            cur = self.conn.cursor()
            cur.execute("SELECT DISTINCT folder FROM snippets WHERE folder IS NOT NULL AND folder != ''")
            rows = cur.fetchall()
            folders = [row[0] for row in rows if row[0]]

            logger.info("Successfully fetched all folders.")
            logger.debug("Folders: %s", folders)
            return folders
        except Exception:
            logger.exception("An error occurred while fetching all folders from the database")
            return None

    def rename_snippet(self, snippet_id: int, new_label: str) -> None:
        """
        Rename a snippet by updating its label.

        Args:
            snippet_id (int): The identifier of the snippet.
            new_label (str): The new label for the snippet.

        Returns:
            None
        """
        logger.info("Renaming a snippet within the database.")
        logger.debug("Snippet ID: %s | New label: %s", snippet_id, new_label)

        try:
            with self.conn:
                self.conn.execute("UPDATE snippets SET label = ? WHERE id = ?", (new_label, snippet_id))
                logger.info("Successfully renamed snippet.")

        except Exception:
            logger.exception("An error occurred while renaming a snippet within the database")
            return None
        
    def search_snippets(self, keyword: str) -> List[Dict[str, Any]]:
        """
        Search for snippets matching a keyword.

        Performs a case-insensitive search across label, snippet,
        trigger, and tags fields.

        Args:
            keyword (str): The search keyword.

        Returns:
            List[Dict[str, Any]] | None: A list of matching snippets,
                or None if an error occurred.
        """
        logger.info("Searching snippets in the database.")
        logger.debug("Keyword: %s", keyword)
        
        try:
            cur = self.conn.cursor()
            query = """
                SELECT * FROM snippets
                WHERE label LIKE ? OR snippet LIKE ? OR trigger LIKE ? OR tags LIKE ?
            """
            wildcard = f"%{keyword}%"
            cur.execute(query, (wildcard, wildcard, wildcard, wildcard))
            columns = [col[0] for col in cur.description]
            results =  [dict(zip(columns, row)) for row in cur.fetchall()]

            logger.info("Successfully searched snippets.")
            logger.debug("Search results count: %d", len(results))
            return results
        except Exception:
            logger.exception("An error occurred while searching snippets within the database")
            return None
    
    def get_all_tags(self) -> list[str]:
        """
        Retrieve all distinct tags across snippets.

        Tags are normalized to lowercase and split by comma.

        Returns:
            list[str] | None: A sorted list of unique tags,
                or None if an error occurred.
        """
        logger.info("Fetching all tags from the database.")

        try:
            cur = self.conn.cursor()
            cur.execute("SELECT DISTINCT tags FROM snippets WHERE tags IS NOT NULL AND tags != ''")
            rows = cur.fetchall()
            tags = set()
            for row in rows:
                for tag in row[0].split(","):
                    tag = tag.strip().lower()
                    if tag:
                        tags.add(tag)

            result = sorted(tags)
            logger.info("Successfully fetched all tags.")
            logger.debug("Tags: %s", result)
            return result
        except Exception:
            logger.exception("An error occurred while fetching tags from the database")
            return None
    
    def delete_tag(self, tag: str) -> None:
        """
        Remove a tag from all snippets that contain it.

        Args:
            tag (str): The tag to remove.

        Returns:
            None
        """
        logger.info("Deleting tag from snippets.")
        logger.debug("Tag: %s", tag)

        try:
            cur = self.conn.cursor()
            cur.execute("SELECT id, tags FROM snippets WHERE tags LIKE ?", (f"%{tag}%",))
            rows = cur.fetchall()

            for row in rows:
                sid, tags = row
                tag_list = [t.strip() for t in tags.split(",") if t.strip().lower() != tag.lower()]
                new_tags = ",".join(tag_list)
                with self.conn:
                    self.conn.execute("UPDATE snippets SET tags = ? WHERE id = ?", (new_tags, sid))
                    logger.info("Successfully deleted tag from snippets.")
        except Exception:
            logger.exception("An error occurred while deleting a tag from the database")
            return None

    # Import / Export
    def export_to_yaml(self, yaml_path: Path) -> None:
        """
        Export all snippets to a YAML file.

        Args:
            yaml_path (Path): The destination YAML file path.

        Returns:
            None
        """
        logger.info("Exporting snippets to YAML.")
        logger.debug("YAML path: %s", yaml_path)

        try:
            snippets = self.get_all_snippets()
            FileUtils.export_snippets_yaml(yaml_path, snippets)
            logger.info("Successfully exported snippets to YAML.")
        except Exception:
            logger.exception("An error occurred while exporting snippets")
            return None

    def import_from_yaml(self, yaml_path: Path) -> None:
        """
        Import snippets from a YAML file into the database.

        Args:
            yaml_path (Path): The source YAML file path.

        Returns:
            None
        """
        logger.info("Importing snippets from YAML.")
        logger.debug("YAML path: %s", yaml_path)

        try:
            snippets = FileUtils.import_snippets_yaml(yaml_path)
            logger.debug("Imported snippets count: %d", len(snippets))

            for entry in snippets:
                self.insert_snippet(entry)

            logger.info("Successfully imported snippets from YAML.")
        except Exception:
            logger.exception("An error occurred while importing snippets")
            return None

    # Custom Placeholders

    def create_custom_placeholders_table(self) -> None:
        """
        Create the custom_placeholders table if it does not exist.

        Returns:
            None
        """
        logger.info("Ensuring custom_placeholders table exists in database")
        try:
            with self.conn:
                self.conn.execute("""
                    CREATE TABLE IF NOT EXISTS custom_placeholders (
                        id          INTEGER PRIMARY KEY AUTOINCREMENT,
                        name        TEXT UNIQUE NOT NULL,
                        value       TEXT NOT NULL DEFAULT '',
                        description TEXT NOT NULL DEFAULT ''
                    )
                """)
            logger.info("custom_placeholders table ensured")
        except Exception:
            logger.exception("Error ensuring custom_placeholders table")

    def seed_default_custom_placeholders(self) -> None:
        """
        Ensure built-in editable custom placeholders exist.

        Inserts the defaults once and leaves any user-modified values intact.

        Returns:
            None
        """
        logger.info("Ensuring built-in editable custom placeholders exist")
        try:
            with self.conn:
                for entry in self.DEFAULT_CUSTOM_PLACEHOLDERS:
                    self.conn.execute(
                        """
                        INSERT OR IGNORE INTO custom_placeholders (name, value, description)
                        VALUES (?, ?, ?)
                        """,
                        (entry["name"], entry["value"], entry["description"]),
                    )
            logger.info("Built-in editable custom placeholders ensured")
        except Exception:
            logger.exception("Error seeding built-in custom placeholders")

    def get_all_custom_placeholders(self) -> List[Dict[str, Any]]:
        """
        Retrieve all user-defined custom placeholders.

        Returns:
            list[dict]: A list of dicts with keys id, name, value, description.
        """
        logger.info("Fetching all custom placeholders")
        try:
            cur = self.conn.cursor()
            cur.execute("SELECT id, name, value, description FROM custom_placeholders ORDER BY name ASC")
            rows = cur.fetchall()
            result = [{"id": r[0], "name": r[1], "value": r[2], "description": r[3]} for r in rows]
            logger.debug("Custom placeholders fetched: %d", len(result))
            return result
        except Exception:
            logger.exception("Error fetching custom placeholders")
            return []

    def insert_custom_placeholder(self, entry: Dict[str, Any]) -> bool:
        """
        Insert a new custom placeholder.

        Args:
            entry (dict): Dict with keys name, value, description.

        Returns:
            bool: True on success, False otherwise.
        """
        logger.info("Inserting custom placeholder: %s", entry.get("name"))
        try:
            with self.conn:
                self.conn.execute(
                    "INSERT INTO custom_placeholders (name, value, description) VALUES (:name, :value, :description)",
                    entry,
                )
            logger.info("Custom placeholder inserted successfully")
            return True
        except Exception:
            logger.exception("Error inserting custom placeholder")
            return False

    def update_custom_placeholder(self, entry: Dict[str, Any]) -> bool:
        """
        Update an existing custom placeholder by id.

        Args:
            entry (dict): Dict with keys id, name, value, description.

        Returns:
            bool: True on success, False otherwise.
        """
        logger.info("Updating custom placeholder id=%s", entry.get("id"))
        try:
            with self.conn:
                self.conn.execute(
                    "UPDATE custom_placeholders SET name=:name, value=:value, description=:description WHERE id=:id",
                    entry,
                )
            logger.info("Custom placeholder updated successfully")
            return True
        except Exception:
            logger.exception("Error updating custom placeholder")
            return False

    def delete_custom_placeholder(self, placeholder_id: int) -> bool:
        """
        Delete a custom placeholder by id.

        Args:
            placeholder_id (int): The id of the placeholder to delete.

        Returns:
            bool: True on success, False otherwise.
        """
        logger.info("Deleting custom placeholder id=%s", placeholder_id)
        try:
            with self.conn:
                self.conn.execute("DELETE FROM custom_placeholders WHERE id=?", (placeholder_id,))
            logger.info("Custom placeholder deleted successfully")
            return True
        except Exception:
            logger.exception("Error deleting custom placeholder")
            return False

    # Close Connection
    def close(self):
        """
        Close the database connection.

        Returns:
            None
        """
        logger.info("Closing database connection.")
        try:
            self.conn.close()
            logger.info("Database connection closed successfully.")
        except Exception:
            logger.exception("An error occurred while closing the database connection")
            return None

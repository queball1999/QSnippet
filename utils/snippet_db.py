import sqlite3
import logging
import random
from pathlib import Path
from typing import List, Dict, Any

from .file_utils import FileUtils

logger = logging.getLogger(__name__)


class SnippetDB:
    def __init__(self, db_path: Path):
        logger.info("Initializing SnippetDB")
        self.db_path = db_path
        logger.debug(f"SQLite Path: {db_path}")
        self.conn = sqlite3.connect(self.db_path)
        self._create_table()
        self._create_indexes()
        self._seed_empty_db()
        logger.info("SnippetDB initialized successfully")

    def _create_table(self):
        """Ensure the table exists."""
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
            logger.info("Snippet tabe should now exist in database")
        except Exception as e:
            logger.error(f"An error occured while ensuring snippet table exists in database: {e}")
            return None

    def _create_indexes(self):
        """Create indexes for faster lookups"""
        logger.info("Ensuring indexes exists in database")
        try:
            with self.conn:
                self.conn.execute("CREATE INDEX IF NOT EXISTS idx_snippets_enabled ON snippets(enabled);")
                self.conn.execute("CREATE INDEX IF NOT EXISTS idx_snippets_folder ON snippets(folder);")
                self.conn.execute("CREATE INDEX IF NOT EXISTS idx_snippets_label ON snippets(label);")
                self.conn.execute("CREATE INDEX IF NOT EXISTS idx_snippets_tags ON snippets(tags);")

                logger.info("Indexes should now exist in database")
        except Exception as e:
            logger.error(f"An error occured while ensuring indexes exists in database: {e}")
            return None

    def _seed_empty_db(self):
        """Seed the database with default snippets if it is empty."""
        logger.info("Checking to see if the database needs to be seeded.")
        try:
            cur = self.conn.cursor()
            cur.execute("SELECT COUNT(*) FROM snippets")
            count = cur.fetchone()[0]

            if count > 0:
                logger.info("Database has already been seeded. Skipping...")
                return  # DB already has snippets, do nothing
        
        except Exception as e:
            logger.error(f"An error occured: {e}")
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

        logger.info("Attempting to seed the databse with default snippets.")
        logger.debug(f"Default Snippets: {default_snippets}")
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

        except Exception as e:
            logger.error(f"An error occured while seeding the database: {e}")
            return

    # CRUD Operations
    def insert_snippet(self, entry: Dict[str, Any]) -> bool:
        """
        Insert a new snippet or update existing. 
        Returns True if new, False if updated.
        Returns None if no valid entry id is provided or an error occured.
        """
        logger.info("Inserting snippet into the databse.")
        logger.debug(f"Entry: {entry}")
        entry_id = entry.get("id")

        if entry_id is None:
            logger.info("No valid entry id was detected. Skipping...")
            return None
        
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
                    logger.info("No existing snippet found. Making new entry.")
                    self.conn.execute("""
                        INSERT INTO snippets (enabled, label, trigger, snippet, paste_style, return_press, folder, tags)
                        VALUES (:enabled, :label, :trigger, :snippet, :paste_style, :return_press, :folder, :tags)
                        ON CONFLICT(trigger) DO UPDATE SET
                            enabled = excluded.enabled,
                            label = excluded.label,
                            snippet = excluded.snippet,
                            paste_style = excluded.paste_style,
                            return_press = excluded.return_press,
                            folder = excluded.folder,
                            tags = excluded.tags
                    """, entry)

                logger.info("Snippet created successfully.")
                return not exists   # True if it was new
            
        except Exception as e:
            logger.error(f"An error occured while inserting a snippet into the database: {e}")
            return None

    def delete_snippet(self, trigger: str):
        """ Delete a snippet from the database. """
        # FIXME: This needs to be updated to id!
        logger.info("Deleting snippet from the database.")
        logger.debug(f"Trigger: {trigger}")

        try:
            with self.conn:
                self.conn.execute("DELETE FROM snippets WHERE trigger = ?", (trigger,))
                logger.info("Snippet deleted from the database")

        except Exception as e:
            logger.error(f"An error occured while deleting a snippet from the database: {e}")
            return None

    def get_all_snippets(self) -> List[Dict[str, Any]]:
        """ Get all snippets from the database. """
        logger.info("Fetching all snippets from the database.")

        try:
            cur = self.conn.cursor()
            cur.execute("SELECT * FROM snippets")
            columns = [col[0] for col in cur.description]
            rows = cur.fetchall()
            result = []

            for row in rows:
                item = dict(zip(columns, row))
                item["enabled"] = bool(item["enabled"])  # convert 1/0 to True/False
                item["return_press"] = bool(item["return_press"])
                result.append(item)

            logger.info("Successfully fetched all snippets from database.")
            logger.debug(f"Snippets: {result}")
            return result
        except Exception as e:
            logger.error(f"An error occured while retrieving snippets from the database: {e}")
            return None

    def get_snippet(self, trigger: str) -> Dict[str, Any]:
        """ Get single snippets from the database. """
        # FIXME: This needs to be updated to id!
        logger.info("Fetching snippet from the database.")
        logger.debug(f"Trigger: {trigger}")

        try:
            cur = self.conn.cursor()
            cur.execute("SELECT * FROM snippets WHERE trigger = ?", (trigger,))
            row = cur.fetchone()

            if row:
                columns = [col[0] for col in cur.description]
                result = dict(zip(columns, row))
                logger.info("Successfully fetched all snippets from database.")
                logger.debug(f"Snippet: {result}")
                return result
            
            logger.info("No entry found for the snippet provided.")
            return {}
        except Exception as e:
            logger.error(f"An error occured while retrieving a snippet from the database: {e}")
            return None
    
    def get_random_snippet(self) -> Dict[str, Any]:
        """Return a random enabled snippet, or empty dict if none exist."""
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
            logger.debug(f"Snippet: {item}")
            return item
        except Exception as e:
            logger.error(f"An error occured while retrieving a random snippet from the database: {e}")
            return None
    
    def rename_folder(self, old_folder: str, new_folder: str):
        """ 
        Rename a folder within the database provided the old and new name. 
        This updates every entry within the old folder.
        """
        logger.info("Renaming a folder within the database.")
        logger.debug(f"OLD Folder: {old_folder} - NEW Folder {new_folder}")

        try:
            with self.conn:
                self.conn.execute("UPDATE snippets SET folder = ? WHERE folder = ?", (new_folder, old_folder))
                logger.info("Successfully renamed folder.")
        except Exception as e:
            logger.error(f"An error occured while renaming a folder within the database: {e}")
            return None
        
    def delete_folder(self, folder: str):
        """ Delete a folder within the database given its name. """
        logger.info("Deleting a folder within the database.")
        logger.debug(f"Folder {folder}")

        try:
            with self.conn:
                self.conn.execute("DELETE FROM snippets WHERE folder = ?", (folder,))
                logger.info("Successfully deleted folder.")
        except Exception as e:
            logger.error(f"An error occured while deleting a folder from the database: {e}")
            return None

    def get_all_folders(self) -> List[str]:
        """Return a list of distinct folder names."""
        logger.info("Fetching all folders within the database.")

        try:
            cur = self.conn.cursor()
            cur.execute("SELECT DISTINCT folder FROM snippets WHERE folder IS NOT NULL AND folder != ''")
            rows = cur.fetchall()
            folders = [row[0] for row in rows if row[0]]

            logger.info("Successfully fetched all folders.")
            logger.debug(f"Folders: {folders}")
            return folders
        except Exception as e:
            logger.error(f"An error occured while fetching all folders from the database: {e}")
            return None

    def rename_snippet(self, trigger: str, new_label: str):
        """
        Rename a snippet by updating its label.
        """
        # FIXME: This needs to be updated to id!
        logger.info("Renaming a snippet within the database.")
        logger.debug(f"Trigger: {trigger} | New Label: {new_label}")

        try:
            with self.conn:
                self.conn.execute("UPDATE snippets SET label = ? WHERE trigger = ?", (new_label, trigger))
                logger.info("Successfully renamed snippet.")

        except Exception as e:
            logger.error(f"An error occured while renaming a snippit within the database: {e}")
            return None
        
    def search_snippets(self, keyword: str) -> List[Dict[str, Any]]:
        """
        Search for snippets matching a keyword in label, snippet,
        trigger, or tags.
        """
        logger.info("Searching snippets in the database.")
        logger.debug(f"Keyword: {keyword}")
        
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
            logger.debug(f"Results: {results}")
            return results
        except Exception as e:
            logger.error(f"An error occured while searching snippets within the database: {e}")
            return None
    
    def get_all_tags(self) -> list[str]:
        """
        Return a list of all distinct tags across snippets.
        Tags are normalized to lowercase and split by comma.
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
            logger.debug(f"Tags: {result}")
            return result
        except Exception as e:
            logger.error(f"An error occured while fetching tags from the database: {e}")
            return None
    
    def delete_tag(self, tag: str):
        """
        Remove a tag from all snippets that contain it.
        """
        logger.info("Deleting tag from snippets.")
        logger.debug(f"Tag: {tag}")

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
        except Exception as e:
            logger.error(f"An error occured while deleting a tag from the database: {e}")
            return None

    # Import / Export
    def export_to_yaml(self, yaml_path: Path):
        """
        Export all snippets to a YAML file.
        """
        logger.info("Exporting snippets to YAML.")
        logger.debug(f"YAML Path: {yaml_path}")

        try:
            snippets = self.get_all_snippets()
            FileUtils.export_snippets_yaml(yaml_path, snippets)
            logger.info("Successfully exported snippets to YAML.")
        except Exception as e:
            logger.error(f"An error occured while exporting your snippets: {e}")
            return None

    def import_from_yaml(self, yaml_path: Path):
        """
        Import snippets from a YAML file into the database.
        """
        logger.info("Importing snippets from YAML.")
        logger.debug(f"YAML Path: {yaml_path}")

        try:
            snippets = FileUtils.import_snippets_yaml(yaml_path)
            logger.debug(f"Imported Snippets: {snippets}")

            for entry in snippets:
                self.insert_snippet(entry)

            logger.info("Successfully imported snippets from YAML.")
        except Exception as e:
            logger.error(f"An error occured while importing your snippets: {e}")
            return None

    # Close Connection
    def close(self):
        """
        Close the database connection.
        """
        logger.info("Closing database connection.")
        try:
            self.conn.close()
            logger.info("Database connection closed successfully.")
        except Exception as e:
            logger.error(f"An error occured while closing the database connection: {e}")
            return None

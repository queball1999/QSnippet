import sqlite3
import logging
import random
from pathlib import Path
from typing import List, Dict, Any

from .file_utils import FileUtils

logger = logging.getLogger(__name__)


class SnippetDB:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        logging.info(f"SQLite Path: {db_path}")
        self.conn = sqlite3.connect(self.db_path)
        self._create_table()
        self._create_indexes()
        self._seed_empty_db()

    def _create_table(self):
        """Ensure the table exists."""
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

    def _create_indexes(self):
        """Create indexes for faster lookups"""
        with self.conn:
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_snippets_enabled ON snippets(enabled);")
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_snippets_folder ON snippets(folder);")
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_snippets_label ON snippets(label);")
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_snippets_tags ON snippets(tags);")

    def _seed_empty_db(self):
        """Seed the database with default snippets if it is empty."""
        try:
            cur = self.conn.cursor()
            cur.execute("SELECT COUNT(*) FROM snippets")
            count = cur.fetchone()[0]

            if count > 0:
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
        entry_id = entry.get("id")

        if entry_id is None:
            return None
        try:
            with self.conn:
                cur = self.conn.cursor()
                cur.execute("SELECT 1 FROM snippets WHERE id = ?", (entry_id,))
                exists = cur.fetchone() is not None

                if exists:  # update existing
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

                        return False  # updated
                else:   # insert new snippet
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

                return not exists   # True if it was new
        except Exception as e:
            logger.error(f"An error occured while inserting a snippet into the database: {e}")
            return None

    def delete_snippet(self, trigger: str):
        try:
            with self.conn:
                self.conn.execute("DELETE FROM snippets WHERE trigger = ?", (trigger,))
        except Exception as e:
            logger.error(f"An error occured while deleting a snippet from the database: {e}")
            return None

    def get_all_snippets(self) -> List[Dict[str, Any]]:
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
            return result
        except Exception as e:
            logger.error(f"An error occured while retrieving snippets from the database: {e}")
            return None

    def get_snippet(self, trigger: str) -> Dict[str, Any]:
        try:
            cur = self.conn.cursor()
            cur.execute("SELECT * FROM snippets WHERE trigger = ?", (trigger,))
            row = cur.fetchone()
            if row:
                columns = [col[0] for col in cur.description]
                return dict(zip(columns, row))
            return {}
        except Exception as e:
            logger.error(f"An error occured while retrieving a snippet from the database: {e}")
            return None
    
    def get_random_snippet(self) -> Dict[str, Any]:
        """Return a random enabled snippet, or empty dict if none exist."""
        try:
            cur = self.conn.cursor()
            cur.execute("SELECT * FROM snippets WHERE enabled = 1")
            rows = cur.fetchall()
            if not rows:
                return {}
            columns = [col[0] for col in cur.description]
            row = random.choice(rows)
            item = dict(zip(columns, row))
            item["enabled"] = bool(item["enabled"])
            item["return_press"] = bool(item["return_press"])
            return item
        except Exception as e:
            logger.error(f"An error occured while retrieving a random snippet from the database: {e}")
            return None
    
    def rename_folder(self, old_folder: str, new_folder: str):
        """ Rename a folder within the database provided the old and new name. """
        try:
            with self.conn:
                self.conn.execute("UPDATE snippets SET folder = ? WHERE folder = ?", (new_folder, old_folder))
        except Exception as e:
            logger.error(f"An error occured while renaming a folder within the database: {e}")
            return None
        
    def delete_folder(self, folder: str):
        """ Delete a folder within the database given its name. """
        try:
            with self.conn:
                self.conn.execute("DELETE FROM snippets WHERE folder = ?", (folder,))
        except Exception as e:
            logger.error(f"An error occured while deleting a folder from the database: {e}")
            return None

    def get_all_folders(self) -> List[str]:
        """Return a list of distinct folder names."""
        try:
            cur = self.conn.cursor()
            cur.execute("SELECT DISTINCT folder FROM snippets WHERE folder IS NOT NULL AND folder != ''")
            rows = cur.fetchall()
            return [row[0] for row in rows if row[0]]
        except Exception as e:
            logger.error(f"An error occured while fetching all folders from the database: {e}")
            return None

    def rename_snippet(self, trigger: str, new_label: str):
        try:
            with self.conn:
                self.conn.execute("UPDATE snippets SET label = ? WHERE trigger = ?", (new_label, trigger))
        except Exception as e:
            logger.error(f"An error occured while renaming a snippit within the database: {e}")
            return None
        
    def search_snippets(self, keyword: str) -> List[Dict[str, Any]]:
        try:
            cur = self.conn.cursor()
            query = """
                SELECT * FROM snippets
                WHERE label LIKE ? OR snippet LIKE ? OR trigger LIKE ? OR tags LIKE ?
            """
            wildcard = f"%{keyword}%"
            cur.execute(query, (wildcard, wildcard, wildcard, wildcard))
            columns = [col[0] for col in cur.description]
            return [dict(zip(columns, row)) for row in cur.fetchall()]
        except Exception as e:
            logger.error(f"An error occured while searching snippets within the database: {e}")
            return None
    
    def get_all_tags(self) -> list[str]:
        """Return a list of distinct tags (split by comma)."""
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

            return sorted(tags)
        except Exception as e:
            logger.error(f"An error occured while fetching tags from the database: {e}")
            return None
    
    def delete_tag(self, tag: str):
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
        except Exception as e:
            logger.error(f"An error occured while deleting a tag from the database: {e}")
            return None

    # Import / Export
    def export_to_yaml(self, yaml_path: Path):
        try:
            snippets = self.get_all_snippets()
            FileUtils.export_snippets_yaml(yaml_path, snippets)
        except Exception as e:
            logger.error(f"An error occured while exporting your snippets: {e}")
            return None

    def import_from_yaml(self, yaml_path: Path):
        try:
            snippets = FileUtils.import_snippets_yaml(yaml_path)
            for entry in snippets:
                self.insert_snippet(entry)
        except Exception as e:
            logger.error(f"An error occured while importing your snippets: {e}")
            return None

    # Close Connection
    def close(self):
        self.conn.close()

# snippet_db.py
import sqlite3
import yaml
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

    def insert_snippet(self, entry: Dict[str, Any]) -> bool:
        """Insert a new snippet or update existing. Returns True if new, False if updated."""
        cur = self.conn.cursor()
        cur.execute("SELECT 1 FROM snippets WHERE trigger = ?", (entry["trigger"],))
        exists = cur.fetchone() is not None

        with self.conn:
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

    def delete_snippet(self, trigger: str):
        with self.conn:
            self.conn.execute("DELETE FROM snippets WHERE trigger = ?", (trigger,))

    def get_all_snippets(self) -> List[Dict[str, Any]]:
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

    def get_snippet(self, trigger: str) -> Dict[str, Any]:
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM snippets WHERE trigger = ?", (trigger,))
        row = cur.fetchone()
        if row:
            columns = [col[0] for col in cur.description]
            return dict(zip(columns, row))
        return {}
    
    def get_random_snippet(self) -> Dict[str, Any]:
        """Return a random enabled snippet, or empty dict if none exist."""
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
    
    def rename_folder(self, old_folder: str, new_folder: str):
        with self.conn:
            self.conn.execute("UPDATE snippets SET folder = ? WHERE folder = ?", (new_folder, old_folder))

    def delete_folder(self, folder: str):
        with self.conn:
            self.conn.execute("DELETE FROM snippets WHERE folder = ?", (folder,))

    def get_all_folders(self) -> List[str]:
        """Return a list of distinct folder names."""
        cur = self.conn.cursor()
        cur.execute("SELECT DISTINCT folder FROM snippets WHERE folder IS NOT NULL AND folder != ''")
        rows = cur.fetchall()
        return [row[0] for row in rows if row[0]]

    def rename_snippet(self, trigger: str, new_label: str):
        with self.conn:
            self.conn.execute("UPDATE snippets SET label = ? WHERE trigger = ?", (new_label, trigger))

    def search_snippets(self, keyword: str) -> List[Dict[str, Any]]:
        cur = self.conn.cursor()
        query = """
            SELECT * FROM snippets
            WHERE label LIKE ? OR snippet LIKE ? OR trigger LIKE ? OR tags LIKE ?
        """
        wildcard = f"%{keyword}%"
        cur.execute(query, (wildcard, wildcard, wildcard, wildcard))
        columns = [col[0] for col in cur.description]
        return [dict(zip(columns, row)) for row in cur.fetchall()]
    
    def get_all_tags(self) -> list[str]:
        """Return a list of distinct tags (split by comma)."""
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
    
    def delete_tag(self, tag: str):
        cur = self.conn.cursor()
        cur.execute("SELECT id, tags FROM snippets WHERE tags LIKE ?", (f"%{tag}%",))
        rows = cur.fetchall()
        for row in rows:
            sid, tags = row
            tag_list = [t.strip() for t in tags.split(",") if t.strip().lower() != tag.lower()]
            new_tags = ",".join(tag_list)
            with self.conn:
                self.conn.execute("UPDATE snippets SET tags = ? WHERE id = ?", (new_tags, sid))

    def export_to_yaml(self, yaml_path: Path):
        snippets = self.get_all_snippets()
        FileUtils.export_snippets_yaml(yaml_path, snippets)

    def import_from_yaml(self, yaml_path: Path):
        snippets = FileUtils.import_snippets_yaml(yaml_path)
        for entry in snippets:
            self.insert_snippet(entry)

    def close(self):
        self.conn.close()

# snippet_db.py
import sqlite3
import yaml
import logging
from pathlib import Path
from typing import List, Dict, Any

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

    def insert_snippet(self, entry: Dict[str, Any]):
        """Insert or update a snippet by trigger."""
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
    
    def rename_folder(self, old_folder: str, new_folder: str):
        with self.conn:
            self.conn.execute("UPDATE snippets SET folder = ? WHERE folder = ?", (new_folder, old_folder))

    def delete_folder(self, folder: str):
        with self.conn:
            self.conn.execute("DELETE FROM snippets WHERE folder = ?", (folder,))

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

    def export_to_yaml(self, yaml_path: Path):
        data = {'snippets': self.get_all_snippets()}
        with open(yaml_path, 'w', encoding='utf-8') as f:
            yaml.safe_dump(data, f)

    def import_from_yaml(self, yaml_path: Path):
        with open(yaml_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f) or {}
        for entry in data.get('snippets', []):
            self.insert_snippet(entry)

    def close(self):
        self.conn.close()

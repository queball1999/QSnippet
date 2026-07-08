import re
import sqlite3
import logging
import random
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import List, Dict, Any

from .file_utils import FileUtils

logger = logging.getLogger(__name__)


# Custom exception classes for specific error conditions
class DatabaseError(Exception):
    """Base exception for database-related errors"""
    pass


class DatabaseConnectionError(DatabaseError):
    """Raised when database connection fails"""
    pass


class DatabaseOperationError(DatabaseError):
    """Raised when a database operation fails"""
    pass


class DatabaseValidationError(DatabaseError):
    """Raised when input validation fails"""
    pass


# Input validation - reject control chars and enforce field length
# limits before any data reaches the database.
CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

FIELD_MAX_LENGTHS: Dict[str, int] = {
    "trigger": 255,
    "label":   500,
    "folder":  500,
    "tags":    1000,
    "snippet": 1_000_000,  # 1 MB hard cap
}


def validate_snippet_entry(entry: Dict[str, Any]) -> None:
    """
    Validate snippet field content before any database write.

    Checks each text field for control characters (0x00-0x1F, 0x7F) and
    enforces per-field maximum lengths.

    Args:
        entry (Dict[str, Any]): Snippet data dict (same shape as insert_snippet expects).
    
    Raises:
        DatabaseValidationError: If any field contains invalid content.
    """
    text_fields = ("trigger", "label", "snippet", "folder", "tags", "paste_style")
    for field in text_fields:
        value = entry.get(field)
        if value is None or not isinstance(value, str):
            continue

        if CONTROL_CHAR_RE.search(value):
            raise DatabaseValidationError(
                f"Field '{field}' contains invalid control characters."
            )

        max_len = FIELD_MAX_LENGTHS.get(field)
        if max_len and len(value) > max_len:
            raise DatabaseValidationError(
                f"Field '{field}' exceeds maximum length of {max_len} characters "
                f"(got {len(value)})."
            )


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
        self.lock = threading.RLock()
        self.closed = False
        self.was_freshly_created = False
        logger.debug("SQLite path: %s", db_path)
        self.conn = sqlite3.connect(
            self.db_path,
            timeout=30.0,
            check_same_thread=False,
        )
        self.conn.row_factory = sqlite3.Row
        self.configure_connection()
        self.fts_available = False
        self.create_table()
        self.migrate_vault_schema()
        self.create_indexes()
        self.setup_fts()
        self.create_vault_folders_table()
        # "Vault" is the one reserved, always-protected folder - register it
        # automatically on every startup (idempotent) so it's never possible
        # for it to end up unregistered (and thus silently unencrypted) as a
        # result of a bug, a manual DB edit, or a removed UI action. Nothing
        # else should ever need to "mark" this specific folder as a vault.
        self.add_vault_folder("Vault")
        self.create_custom_placeholders_table()
        self.migrate_custom_placeholders_vault_schema()
        self.migrate_aad_binding_schema()
        self.seed_default_custom_placeholders()
        self.seed_empty_db()
        logger.info("SnippetDB initialized successfully")

    def configure_connection(self) -> None:
        """
        Configure SQLite pragmas for safer concurrent local access.
        
        Returns:
            None
        """
        logger.debug("Configuring SQLite connection pragmas")
        with self.lock:
            self.conn.execute("PRAGMA journal_mode=WAL")
            self.conn.execute("PRAGMA busy_timeout = 30000")
            self.conn.execute("PRAGMA synchronous = NORMAL")
            self.conn.execute("PRAGMA foreign_keys = ON")

    def ensure_open(self) -> None:
        """
        Ensure the database connection is still open.
        
        Returns:
            None
        
        Raises:
            RuntimeError: If the database connection has already been closed.
        """
        if self.closed:
            raise RuntimeError("The database connection is already closed")

    @contextmanager
    def managed_connection(self, write: bool = False):
        """
        Provide synchronized access to the shared SQLite connection.

        Args:
            write (bool): When True, wrap the connection in a transaction.
        
        Returns:
            sqlite3.Connection: The active SQLite connection.
        """
        with self.lock:
            self.ensure_open()
            if write:
                with self.conn:
                    yield self.conn
            else:
                yield self.conn

    def normalize_snippet_row(self, row: sqlite3.Row | None) -> Dict[str, Any]:
        """
        Normalize a snippet row from SQLite into application types.

        Args:
            row (sqlite3.Row | None): The row to normalize.
        
        Returns:
            Dict[str, Any]: A normalized snippet dictionary.
        """
        if row is None:
            return {}

        item = dict(row)
        if "enabled" in item:
            item["enabled"] = bool(item["enabled"])
        if "return_press" in item:
            item["return_press"] = bool(item["return_press"])
        if "is_encrypted" in item:
            item["is_encrypted"] = bool(item["is_encrypted"])
        return item

    def escape_like_value(self, value: str) -> str:
        """
        Escape SQLite LIKE wildcard characters in user-supplied text.

        Args:
            value (str): The raw value to escape.
        
        Returns:
            str: The escaped value.
        """
        return (
            str(value)
            .replace("\\", "\\\\")
            .replace("%", "\\%")
            .replace("_", "\\_")
        )

    def create_table(self) -> None:
        """
        Create the snippets table if it does not exist.
        
        Returns:
            None
        
        Raises:
            DatabaseOperationError: If table creation fails.
        """
        logger.info("Ensuring snippet table exists in database")
        try:
            with self.managed_connection(write=True) as conn:
                conn.execute("""
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
        except sqlite3.Error as e:
            logger.exception("Failed to create snippet table in database")
            raise DatabaseOperationError(f"Failed to create snippet table: {e}") from e

    def create_indexes(self) -> None:
        """
        Create database indexes to improve query performance.

        Includes basic indexes on commonly queried columns and a full-text
        search index (FTS5) for efficient searching across multiple fields.
        
        Returns:
            None
        
        Raises:
            DatabaseOperationError: If index creation fails.
        """
        logger.info("Ensuring indexes exist in database")
        try:
            with self.managed_connection(write=True) as conn:
                conn.execute("CREATE INDEX IF NOT EXISTS idx_snippets_enabled ON snippets(enabled);")
                # Composite index serves ORDER BY folder, id in get_all_snippets
                conn.execute("CREATE INDEX IF NOT EXISTS idx_snippets_folder_id ON snippets(folder, id);")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_snippets_label ON snippets(label);")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_snippets_tags ON snippets(tags);")
                # idx_snippets_trigger is intentionally omitted: the UNIQUE constraint
                # on the trigger column already creates an implicit index.
                conn.execute("CREATE INDEX IF NOT EXISTS idx_snippets_encrypted ON snippets(is_encrypted);")

                logger.info("Indexes created/verified in database")
        except sqlite3.Error as e:
            logger.exception("Failed to create indexes in database")
            raise DatabaseOperationError(f"Failed to create indexes: {e}") from e

    def setup_fts(self) -> None:
        """
        Create or migrate the FTS5 full-text search index with the trigram tokenizer
        and install the four sync triggers that keep it current.

        The trigram tokenizer indexes every 3-character sequence, enabling infix
        (substring) matching equivalent to LIKE '%keyword%' but via the index.
        Safe to call on every startup: exits immediately if already configured.

        Returns:
            None
        """
        try:
            with self.managed_connection(write=True) as conn:
                cur = conn.cursor()

                # Check whether FTS table already uses the trigram tokenizer
                cur.execute(
                    "SELECT sql FROM sqlite_master WHERE type='table' AND name='snippets_fts'"
                )
                row = cur.fetchone()
                has_trigram = row and "trigram" in (row[0] or "")

                cur.execute(
                    "SELECT count(*) FROM sqlite_master WHERE type='trigger'"
                    " AND name IN ('snippets_ai','snippets_bd','snippets_bu','snippets_au')"
                )
                trigger_count = cur.fetchone()[0]

                # Also verify the insert/update/delete triggers are vault-aware (have a WHEN clause),
                # since deleting a never-indexed (encrypted) rowid from FTS5 corrupts the index.
                cur.execute(
                    "SELECT name, sql FROM sqlite_master WHERE type='trigger'"
                    " AND name IN ('snippets_ai','snippets_bd','snippets_bu')"
                )
                rows = {r[0]: r[1] for r in cur.fetchall()}
                all_vault_aware = all(
                    "WHEN" in (rows.get(name) or "") for name in ("snippets_ai", "snippets_bd", "snippets_bu")
                )

                if has_trigram and trigger_count == 4 and all_vault_aware:
                    logger.debug("FTS5 trigram index already configured")
                    self.fts_available = True
                    return

                # Drop stale FTS table (may exist without trigram from a previous run)
                conn.execute("DROP TABLE IF EXISTS snippets_fts")

                conn.execute("""
                    CREATE VIRTUAL TABLE snippets_fts USING fts5(
                        label, trigger, snippet, tags,
                        content='snippets', content_rowid='id',
                        tokenize='trigram'
                    )
                """)

                for name in ("snippets_ai", "snippets_bd", "snippets_bu", "snippets_au"):
                    conn.execute(f"DROP TRIGGER IF EXISTS {name}")

                # Only index non-encrypted snippets so vault content (labels, triggers)
                # cannot be found via FTS when the vault is locked.
                conn.execute("""
                    CREATE TRIGGER snippets_ai AFTER INSERT ON snippets
                    WHEN new.is_encrypted = 0
                    BEGIN
                        INSERT INTO snippets_fts(rowid, label, trigger, snippet, tags)
                        VALUES (new.id, new.label, new.trigger, new.snippet, new.tags);
                    END
                """)
                conn.execute("""
                    CREATE TRIGGER snippets_bd BEFORE DELETE ON snippets
                    WHEN old.is_encrypted = 0
                    BEGIN
                        INSERT INTO snippets_fts(snippets_fts, rowid, label, trigger, snippet, tags)
                        VALUES ('delete', old.id, old.label, old.trigger, old.snippet, old.tags);
                    END
                """)
                conn.execute("""
                    CREATE TRIGGER snippets_bu BEFORE UPDATE ON snippets
                    WHEN old.is_encrypted = 0
                    BEGIN
                        INSERT INTO snippets_fts(snippets_fts, rowid, label, trigger, snippet, tags)
                        VALUES ('delete', old.id, old.label, old.trigger, old.snippet, old.tags);
                    END
                """)
                conn.execute("""
                    CREATE TRIGGER snippets_au AFTER UPDATE ON snippets BEGIN
                        INSERT INTO snippets_fts(rowid, label, trigger, snippet, tags)
                        SELECT new.id, new.label, new.trigger, new.snippet, new.tags
                        WHERE new.is_encrypted = 0;
                    END
                """)

                # Populate index from non-encrypted rows only
                conn.execute("""
                    INSERT INTO snippets_fts(rowid, label, trigger, snippet, tags)
                    SELECT id, label, trigger, snippet, tags FROM snippets
                    WHERE is_encrypted = 0
                """)
                self.fts_available = True
                logger.info("FTS5 trigram index created and populated")

        except sqlite3.OperationalError as e:
            logger.warning("FTS5 trigram unavailable, search will use LIKE: %s", e)
            self.fts_available = False

    def seed_empty_db(self) -> None:
        """
        Seed the database with default snippets if it is empty.
        
        Returns:
            None
        
        Raises:
            DatabaseOperationError: If seeding fails.
        """
        logger.info("Checking to see if the database needs to be seeded.")
        try:
            with self.managed_connection() as conn:
                cur = conn.cursor()
                cur.execute("SELECT COUNT(*) FROM snippets")
                count = cur.fetchone()[0]

            if count > 0:
                logger.info("Database has already been seeded. Skipping...")
                return  # DB already has snippets, do nothing

        except sqlite3.Error as e:
            logger.exception("Failed to check if database needs seeding")
            raise DatabaseOperationError(f"Failed to check database seed status: {e}") from e

        default_snippets = [
            {
                "enabled": True,
                "label": "Welcome Snippet",
                "trigger": "/welcome",
                "snippet": "Welcome to QSnippet! Click `New Snippet` below to create your first snippet.",
                "paste_style": "clipboard",
                "return_press": False,
                "folder": "Getting Started",
                "tags": "default,welcome",
            }
        ]

        logger.info("Attempting to seed the database with default snippets")
        logger.debug("Default snippet seed count: %d", len(default_snippets))
        try:
            with self.managed_connection(write=True) as conn:
                for entry in default_snippets:
                    conn.execute(
                        """
                        INSERT INTO snippets
                        (enabled, label, trigger, snippet, paste_style, return_press, folder, tags)
                        VALUES
                        (:enabled, :label, :trigger, :snippet, :paste_style, :return_press, :folder, :tags)
                        """,
                        entry,
                    )
                logger.info("The database has been seeded successfully!")
                self.was_freshly_created = True

        except sqlite3.Error as e:
            logger.exception("Failed to seed database with default snippets")
            raise DatabaseOperationError(f"Failed to seed database: {e}") from e

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
        validate_snippet_entry(entry)  # Audit 1.5: validate before write
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
            with self.managed_connection(write=True) as conn:
                cur = conn.cursor()
                cur.execute("SELECT 1 FROM snippets WHERE id = ?", (entry_id,))
                exists = cur.fetchone() is not None

                if exists:  # update existing
                    logger.info("Found existing snippet. Updating entry.")
                    cur.execute("""
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
                    rows_changed = cur.rowcount
                    logger.info(f"ID-based update complete. Rows changed: {rows_changed}")
                    return False  # was an update

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
                        entry["id"] = trigger_row[0]  # populate id for callers relying on this side effect
                        cur.execute("""
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
                        rows_changed = cur.rowcount
                        logger.info(f"Trigger-based update complete for trigger '{trigger}'. Rows changed: {rows_changed}")
                        return False  # was an update
                    else:
                        logger.info("No existing trigger found. Inserting new entry for trigger '%s'.", trigger)
                        cur.execute("""
                            INSERT INTO snippets (enabled, label, trigger, snippet, paste_style, return_press, folder, tags)
                            VALUES (:enabled, :label, :trigger, :snippet, :paste_style, :return_press, :folder, :tags)
                        """, entry)
                        rows_changed = cur.rowcount
                        entry["id"] = cur.lastrowid  # Audit 3.2: populate id for incremental expander update
                        logger.info(f"Insert complete for trigger '{trigger}'. Rows changed: {rows_changed}")
                        return True  # was new

        except sqlite3.Error as e:
            trigger = entry.get('trigger', 'unknown')
            logger.exception(f"Database error while inserting snippet with trigger: {trigger}")
            raise DatabaseOperationError(f"Failed to insert snippet with trigger '{trigger}': {e}") from e

    def delete_snippet(self, snippet_id: id) -> None:
        """
        Delete a snippet from the database.

        Args:
            snippet_id (id): The identifier of the snippet to delete.
        
        Returns:
            None
        
        Raises:
            DatabaseOperationError: If deletion fails.
        """
        logger.info("Deleting snippet from the database.")
        logger.debug("Snippet ID: %s", snippet_id)

        try:
            with self.managed_connection(write=True) as conn:
                conn.execute("DELETE FROM snippets WHERE id = ?", (snippet_id,))
                logger.info("Snippet deleted from the database")

        except sqlite3.Error as e:
            logger.exception("Failed to delete snippet from database")
            raise DatabaseOperationError(f"Failed to delete snippet with id '{snippet_id}': {e}") from e

    def get_all_snippets(self) -> List[Dict[str, Any]]:
        """
        Retrieve all snippets from the database.
        
        Returns:
            List[Dict[str, Any]]: A list of snippet dictionaries (empty list if none exist).
        
        Raises:
            DatabaseOperationError: If retrieval fails.
        """
        logger.info("Fetching all snippets from the database.")

        try:
            with self.managed_connection() as conn:
                cur = conn.cursor()
                cur.execute("SELECT * FROM snippets ORDER BY folder, id")
                result = [self.normalize_snippet_row(row) for row in cur.fetchall()]

            logger.info("Successfully fetched all snippets from database.")
            logger.debug("Fetched snippets count: %d", len(result))
            return result
        except sqlite3.Error as e:
            logger.exception("Failed to retrieve snippets from database")
            raise DatabaseOperationError(f"Failed to fetch snippets: {e}") from e

    def get_snippet_count(self) -> int:
        """
        Get the total count of snippets in the database.

        Returns:
            int: Total number of snippets.

        Raises:
            DatabaseOperationError: If query fails.
        """
        try:
            with self.managed_connection() as conn:
                cur = conn.cursor()
                cur.execute("SELECT COUNT(*) FROM snippets")
                count = cur.fetchone()[0]
            return count
        except sqlite3.Error as e:
            logger.exception("Failed to get snippet count")
            raise DatabaseOperationError(f"Failed to count snippets: {e}") from e

    def get_snippet(self, snippet_id: int) -> Dict[str, Any]:
        """
        Retrieve a single snippet from the database.

        Args:
            snippet_id (int): The identifier used to query the snippet.
        
        Returns:
            Dict[str, Any]: The snippet dictionary if found, or empty dict if not found.
        
        Raises:
            DatabaseOperationError: If retrieval fails.
        """
        logger.info("Fetching snippet from the database.")
        logger.debug("Snippet ID: %s", snippet_id)

        try:
            with self.managed_connection() as conn:
                cur = conn.cursor()
                cur.execute("SELECT * FROM snippets WHERE id = ?", (snippet_id,))
                row = cur.fetchone()

            if row:
                result = self.normalize_snippet_row(row)
                logger.info("Successfully fetched snippet from database.")
                logger.debug(
                    "Snippet fetched: id=%s trigger=%s folder=%s",
                    result.get("id"),
                    result.get("trigger"),
                    result.get("folder"),
                )
                return result

            logger.info("No entry found for snippet id %s.", snippet_id)
            return {}
        except sqlite3.Error as e:
            logger.exception("Failed to retrieve snippet from database")
            raise DatabaseOperationError(f"Failed to fetch snippet with id '{snippet_id}': {e}") from e

    def get_snippet_by_trigger(self, trigger: str) -> Dict[str, Any]:
        """
        Retrieve a single snippet by trigger.

        Args:
            trigger (str): The trigger text to query.
        
        Returns:
            Dict[str, Any]: The snippet dictionary if found, or empty dict if not found.
        
        Raises:
            DatabaseOperationError: If retrieval fails.
        """
        logger.info("Fetching snippet by trigger from the database.")
        logger.debug("Trigger: %s", trigger)

        try:
            with self.managed_connection() as conn:
                cur = conn.cursor()
                cur.execute("SELECT * FROM snippets WHERE trigger = ?", (trigger,))
                row = cur.fetchone()

            if row:
                return self.normalize_snippet_row(row)

            return {}
        except sqlite3.Error as e:
            logger.exception("Failed to retrieve snippet by trigger")
            raise DatabaseOperationError(f"Failed to fetch snippet by trigger '{trigger}': {e}") from e

    def get_enabled_trigger_index(self) -> List[Dict[str, Any]]:
        """
        Retrieve the index of enabled trigger.
        
        Returns:
            List[Dict[str, Any]]: Trigger metadata used by the keyboard expander
                (empty list if none exist).
        
        Raises:
            DatabaseOperationError: If retrieval fails.
        """
        logger.info("Fetching enabled trigger index from the database.")

        try:
            with self.managed_connection() as conn:
                cur = conn.cursor()
                cur.execute(
                    """
                    SELECT id, trigger, paste_style, return_press
                    FROM snippets
                    WHERE enabled = 1
                    ORDER BY LENGTH(trigger) DESC, trigger ASC
                    """
                )
                rows = cur.fetchall()

            result = []
            for row in rows:
                item = dict(row)
                item["return_press"] = bool(item["return_press"])
                result.append(item)

            logger.debug("Enabled trigger index count: %d", len(result))
            return result
        except sqlite3.Error as e:
            logger.exception("Failed to retrieve enabled trigger index")
            raise DatabaseOperationError(f"Failed to fetch enabled trigger index: {e}") from e
    
    def get_random_snippet(self) -> Dict[str, Any]:
        """
        Retrieve a random enabled snippet.
        
        Returns:
            Dict[str, Any]: A randomly selected snippet dictionary,
                or empty dictionary if none exist.
        
        Raises:
            DatabaseOperationError: If retrieval fails.
        """
        logger.info("Fetching random snippet from the database.")

        try:
            with self.managed_connection() as conn:
                cur = conn.cursor()
                cur.execute("SELECT * FROM snippets WHERE enabled = 1")
                rows = cur.fetchall()

            if not rows:
                logger.info("No enabled snippets found in the database.")
                return {}

            row = random.choice(rows)
            return self.normalize_snippet_row(row)
        except sqlite3.Error as e:
            logger.exception("Failed to retrieve random snippet")
            raise DatabaseOperationError(f"Failed to fetch random snippet: {e}") from e
    
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
        
        Raises:
            DatabaseOperationError: If renaming fails.
        """
        logger.info("Renaming a folder within the database.")
        logger.debug("Renaming folder: old=%s new=%s", old_folder, new_folder)

        try:
            escaped_old_folder = self.escape_like_value(old_folder)

            with self.managed_connection(write=True) as conn:
                # Rename exact match
                conn.execute(
                    "UPDATE snippets SET folder = ? WHERE folder = ?",
                    (new_folder, old_folder)
                )
                # Rename any sub-paths: old_folder/... -> new_folder/...
                conn.execute(
                    "UPDATE snippets SET folder = ? || substr(folder, ? + 1) WHERE folder LIKE ? ESCAPE '\\'",
                    (new_folder, len(old_folder), f"{escaped_old_folder}/%")
                )
                logger.info("Successfully renamed folder and its sub-folders.")
        except sqlite3.Error as e:
            logger.exception("Failed to rename folder in database")
            raise DatabaseOperationError(f"Failed to rename folder '{old_folder}' to '{new_folder}': {e}") from e
        
    def delete_folder(self, folder: str) -> None:
        """
        Delete all snippets within a specified folder and any nested sub-folders.

        For example, deleting "work" will also delete snippets in "work/drafts".

        Args:
            folder (str): The folder path to delete (may be nested, e.g. "a/b").
        
        Returns:
            None
        
        Raises:
            DatabaseOperationError: If deletion fails.
        """
        logger.info("Deleting a folder within the database.")
        logger.debug("Folder: %s", folder)

        try:
            escaped_folder = self.escape_like_value(folder)

            with self.managed_connection(write=True) as conn:
                conn.execute(
                    "DELETE FROM snippets WHERE folder = ? OR folder LIKE ? ESCAPE '\\'",
                    (folder, f"{escaped_folder}/%")
                )
                logger.info("Successfully deleted folder and its sub-folders.")
        except sqlite3.Error as e:
            logger.exception("Failed to delete folder from database")
            raise DatabaseOperationError(f"Failed to delete folder '{folder}': {e}") from e

    def get_all_folders(self) -> List[str]:
        """
        Retrieve all distinct folder names.
        
        Returns:
            List[str]: A list of folder names (empty list if none exist).
        
        Raises:
            DatabaseOperationError: If retrieval fails.
        """
        logger.info("Fetching all folders within the database.")

        try:
            with self.managed_connection() as conn:
                cur = conn.cursor()
                cur.execute("SELECT DISTINCT folder FROM snippets WHERE folder IS NOT NULL AND folder != ''")
                rows = cur.fetchall()
            folders = [row[0] for row in rows if row[0]]

            logger.info("Successfully fetched all folders.")
            logger.debug("Folders: %s", folders)
            return folders
        except sqlite3.Error as e:
            logger.exception("Failed to retrieve folders from database")
            raise DatabaseOperationError(f"Failed to fetch folders: {e}") from e

    def rename_snippet(self, snippet_id: int, new_label: str) -> None:
        """
        Rename a snippet by updating its label.

        Args:
            snippet_id (int): The identifier of the snippet.
            new_label (str): The new label for the snippet.
        
        Returns:
            None
        
        Raises:
            DatabaseOperationError: If renaming fails.
        """
        logger.info("Renaming a snippet within the database.")
        logger.debug("Snippet ID: %s | New label: %s", snippet_id, new_label)

        try:
            with self.managed_connection(write=True) as conn:
                conn.execute("UPDATE snippets SET label = ? WHERE id = ?", (new_label, snippet_id))
                logger.info("Successfully renamed snippet.")

        except sqlite3.Error as e:
            logger.exception("Failed to rename snippet in database")
            raise DatabaseOperationError(f"Failed to rename snippet '{snippet_id}' to '{new_label}': {e}") from e
        
    def search_snippets(self, keyword: str) -> List[Dict[str, Any]]:
        """
        Search for snippets matching a keyword.

        Performs a case-insensitive search across label, snippet,
        trigger, and tags fields.

        Args:
            keyword (str): The search keyword.
        
        Returns:
            List[Dict[str, Any]]: A list of matching snippets (empty list if none found).
        
        Raises:
            DatabaseOperationError: If search fails.
        """
        logger.info("Searching snippets in the database.")
        logger.debug("Keyword: %s", keyword)

        if not keyword:
            return self.get_all_snippets()

        try:
            # FTS5 trigram requires at least 3 characters; shorter queries return no rows.
            if self.fts_available and len(keyword) >= 3:
                # Wrap in double quotes for a trigram phrase/substring match.
                # This is equivalent to LIKE '%keyword%' but uses the index.
                fts_query = f'"{keyword.replace(chr(34), chr(34) * 2)}"'
                with self.managed_connection() as conn:
                    cur = conn.cursor()
                    cur.execute(
                        """
                        SELECT s.* FROM snippets s
                        WHERE s.id IN (
                            SELECT rowid FROM snippets_fts WHERE snippets_fts MATCH ?
                        )
                        ORDER BY s.folder, s.id
                        """,
                        (fts_query,),
                    )
                    results = [self.normalize_snippet_row(row) for row in cur.fetchall()]
                logger.debug("FTS search results count: %d", len(results))
                return results

            # Fallback: LIKE scan (short keyword, or FTS5/trigram unavailable)
            escaped_keyword = self.escape_like_value(keyword)
            wildcard = f"%{escaped_keyword}%"
            with self.managed_connection() as conn:
                cur = conn.cursor()
                cur.execute(
                    """
                    SELECT * FROM snippets
                    WHERE label   LIKE ? ESCAPE '\\'
                       OR snippet LIKE ? ESCAPE '\\'
                       OR trigger LIKE ? ESCAPE '\\'
                       OR tags    LIKE ? ESCAPE '\\'
                    """,
                    (wildcard, wildcard, wildcard, wildcard),
                )
                results = [self.normalize_snippet_row(row) for row in cur.fetchall()]

            logger.debug("LIKE search results count: %d", len(results))
            return results
        except sqlite3.Error as e:
            logger.exception("Failed to search snippets in database")
            raise DatabaseOperationError(f"Failed to search snippets for keyword '{keyword}': {e}") from e
    
    def get_all_tags(self) -> list[str]:
        """
        Retrieve all distinct tags across snippets.

        Tags are normalized to lowercase and split by comma.
        
        Returns:
            list[str]: A sorted list of unique tags (empty list if none exist).
        
        Raises:
            DatabaseOperationError: If retrieval fails.
        """
        logger.info("Fetching all tags from the database.")

        try:
            with self.managed_connection() as conn:
                cur = conn.cursor()
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
        except sqlite3.Error as e:
            logger.exception("Failed to retrieve tags from database")
            raise DatabaseOperationError(f"Failed to fetch tags: {e}") from e
    
    def delete_tag(self, tag: str) -> None:
        """
        Remove a tag from all snippets that contain it.

        Args:
            tag (str): The tag to remove.
        
        Returns:
            None
        
        Raises:
            DatabaseOperationError: If deletion fails.
        """
        logger.info("Deleting tag from snippets.")
        logger.debug("Tag: %s", tag)

        try:
            wildcard = f"%{self.escape_like_value(tag)}%"
            with self.managed_connection(write=True) as conn:
                cur = conn.cursor()
                cur.execute(
                    "SELECT id, tags FROM snippets WHERE tags LIKE ? ESCAPE '\\'",
                    (wildcard,),
                )
                rows = cur.fetchall()

                for row in rows:
                    sid, tags = row
                    tag_list = [t.strip() for t in tags.split(",") if t.strip().lower() != tag.lower()]
                    new_tags = ",".join(tag_list)
                    conn.execute("UPDATE snippets SET tags = ? WHERE id = ?", (new_tags, sid))

                logger.info("Successfully deleted tag from snippets.")
        except sqlite3.Error as e:
            logger.exception("Failed to delete tag from database")
            raise DatabaseOperationError(f"Failed to delete tag '{tag}': {e}") from e

    # Import / Export
    def export_to_yaml(self, yaml_path: Path) -> None:
        """
        Export all snippets to a YAML file.

        Args:
            yaml_path (Path): The destination YAML file path.
        
        Returns:
            None
        
        Raises:
            DatabaseOperationError: If export fails.
        """
        logger.info("Exporting snippets to YAML.")
        logger.debug("YAML path: %s", yaml_path)

        try:
            snippets = self.get_all_snippets()
            FileUtils.export_snippets_yaml(yaml_path, snippets)
            logger.info("Successfully exported snippets to YAML.")
        except Exception as e:
            logger.exception("Failed to export snippets to YAML")
            raise DatabaseOperationError(f"Failed to export snippets to '{yaml_path}': {e}") from e

    def import_from_yaml(self, yaml_path: Path) -> None:
        """
        Import snippets from a YAML file into the database.

        Args:
            yaml_path (Path): The source YAML file path.
        
        Returns:
            None
        
        Raises:
            DatabaseOperationError: If import fails.
        """
        logger.info("Importing snippets from YAML.")
        logger.debug("YAML path: %s", yaml_path)

        try:
            snippets = FileUtils.import_snippets_yaml(yaml_path)
            logger.debug("Imported snippets count: %d", len(snippets))

            for entry in snippets:
                self.insert_snippet(entry)

            logger.info("Successfully imported snippets from YAML.")
        except Exception as e:
            logger.exception("Failed to import snippets from YAML")
            raise DatabaseOperationError(f"Failed to import snippets from '{yaml_path}': {e}") from e

    # Custom Placeholders

    def create_custom_placeholders_table(self) -> None:
        """
        Create the custom_placeholders table if it does not exist.

        Returns:
            None

        Raises:
            DatabaseOperationError: If table creation fails.
        """
        logger.info("Ensuring custom_placeholders table exists in database")
        try:
            with self.managed_connection(write=True) as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS custom_placeholders (
                        id          INTEGER PRIMARY KEY AUTOINCREMENT,
                        name        TEXT UNIQUE NOT NULL,
                        value       TEXT NOT NULL DEFAULT '',
                        description TEXT NOT NULL DEFAULT '',
                        is_encrypted BOOLEAN NOT NULL DEFAULT 0
                    )
                """)
            logger.info("custom_placeholders table ensured")
        except sqlite3.Error as e:
            logger.exception("Failed to create custom_placeholders table")
            raise DatabaseOperationError(f"Failed to create custom_placeholders table: {e}") from e

    def seed_default_custom_placeholders(self) -> None:
        """
        Ensure built-in editable custom placeholders exist.

        Inserts the defaults once and leaves any user-modified values intact.
        
        Returns:
            None
        
        Raises:
            DatabaseOperationError: If seeding fails.
        """
        logger.info("Ensuring built-in editable custom placeholders exist")
        try:
            with self.managed_connection(write=True) as conn:
                for entry in self.DEFAULT_CUSTOM_PLACEHOLDERS:
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO custom_placeholders (name, value, description)
                        VALUES (?, ?, ?)
                        """,
                        (entry["name"], entry["value"], entry["description"]),
                    )
            logger.info("Built-in editable custom placeholders ensured")
        except sqlite3.Error as e:
            logger.exception("Failed to seed built-in custom placeholders")
            raise DatabaseOperationError(f"Failed to seed custom placeholders: {e}") from e

    def get_all_custom_placeholders(self) -> List[Dict[str, Any]]:
        """
        Retrieve all user-defined custom placeholders.

        Returns:
            list[dict]: A list of dicts with keys id, name, value, description, is_encrypted.

        Raises:
            DatabaseOperationError: If retrieval fails.
        """
        logger.info("Fetching all custom placeholders")
        try:
            with self.managed_connection() as conn:
                cur = conn.cursor()
                cur.execute("SELECT id, name, value, description, is_encrypted, vault_uuid FROM custom_placeholders ORDER BY name ASC")
                rows = cur.fetchall()
            result = [{"id": r[0], "name": r[1], "value": r[2], "description": r[3], "is_encrypted": bool(r[4]), "vault_uuid": r[5]} for r in rows]
            logger.debug("Custom placeholders fetched: %d", len(result))
            return result
        except sqlite3.Error as e:
            logger.exception("Failed to fetch custom placeholders")
            raise DatabaseOperationError(f"Failed to fetch custom placeholders: {e}") from e

    def insert_custom_placeholder(self, entry: Dict[str, Any]) -> bool:
        """
        Insert a new custom placeholder.

        Args:
            entry (dict): Dict with keys name, value, description, is_encrypted (optional, defaults to 0).

        Returns:
            bool: True on success, False on error.
        """
        logger.info("Inserting custom placeholder: %s", entry.get("name"))
        try:
            with self.managed_connection(write=True) as conn:
                conn.execute(
                    "INSERT INTO custom_placeholders (name, value, description, is_encrypted, vault_uuid) "
                    "VALUES (:name, :value, :description, :is_encrypted, :vault_uuid)",
                    {
                        "name": entry.get("name"),
                        "value": entry.get("value", ""),
                        "description": entry.get("description", ""),
                        "is_encrypted": entry.get("is_encrypted", 0),
                        "vault_uuid": entry.get("vault_uuid"),
                    },
                )
            logger.info("Custom placeholder inserted successfully")
            return True
        except sqlite3.Error as e:
            logger.exception("Failed to insert custom placeholder")
            return False

    def update_custom_placeholder(self, entry: Dict[str, Any]) -> bool:
        """
        Update an existing custom placeholder by id.

        Args:
            entry (dict): Dict with keys id, name, value, description, is_encrypted (optional).

        Returns:
            bool: True on success, False on error.
        """
        placeholder_id = entry.get("id")
        is_encrypted_val = entry.get("is_encrypted", 0)
        vault_uuid_val = entry.get("vault_uuid")
        logger.info("Updating custom placeholder id=%s: is_encrypted=%s, vault_uuid=%s",
                   placeholder_id, is_encrypted_val, vault_uuid_val)
        try:
            with self.managed_connection(write=True) as conn:
                conn.execute(
                    "UPDATE custom_placeholders SET name=:name, value=:value, description=:description, "
                    "is_encrypted=:is_encrypted, vault_uuid=:vault_uuid WHERE id=:id",
                    {
                        "id": placeholder_id,
                        "name": entry.get("name"),
                        "value": entry.get("value", ""),
                        "description": entry.get("description", ""),
                        "is_encrypted": is_encrypted_val,
                        "vault_uuid": vault_uuid_val,
                    },
                )
            # Verify the update
            cur = conn.cursor()
            cur.execute("SELECT is_encrypted, vault_uuid FROM custom_placeholders WHERE id=?", (placeholder_id,))
            row = cur.fetchone()
            if row:
                actual_encrypted, actual_uuid = row
                if bool(actual_encrypted) != bool(is_encrypted_val):
                    logger.warning("Encryption flag mismatch after update: expected=%s, actual=%s",
                                 is_encrypted_val, actual_encrypted)
                logger.info("Custom placeholder id=%s updated successfully (is_encrypted=%s)",
                           placeholder_id, actual_encrypted)
            return True
        except sqlite3.Error as e:
            logger.exception("Failed to update custom placeholder")
            return False

    def delete_custom_placeholder(self, placeholder_id: int) -> bool:
        """
        Delete a custom placeholder by id.

        Args:
            placeholder_id (int): The id of the placeholder to delete.
        
        Returns:
            bool: True on success, False on error.
        """
        logger.info("Deleting custom placeholder id=%s", placeholder_id)
        try:
            with self.managed_connection(write=True) as conn:
                conn.execute("DELETE FROM custom_placeholders WHERE id=?", (placeholder_id,))
            logger.info("Custom placeholder deleted successfully")
            return True
        except sqlite3.Error as e:
            logger.exception("Failed to delete custom placeholder")
            return False

    # Vault Support

    def migrate_vault_schema(self) -> None:
        """Add is_encrypted column to snippets if it does not exist (migration)."""
        try:
            with self.managed_connection(write=True) as conn:
                cols = [row[1] for row in conn.execute("PRAGMA table_info(snippets)").fetchall()]
                if "is_encrypted" not in cols:
                    conn.execute("ALTER TABLE snippets ADD COLUMN is_encrypted BOOLEAN DEFAULT 0")
                    logger.info("Migrated: added is_encrypted column to snippets")
        except sqlite3.Error as exc:
            logger.warning("Vault schema migration failed: %s", exc)

    def migrate_aad_binding_schema(self) -> None:
        """Add vault_uuid column to snippets and custom_placeholders (migration).

        The vault_uuid is passed as AES-GCM AAD at encrypt/decrypt time so that
        ciphertext blobs are cryptographically bound to their row.  Existing
        encrypted rows (vault_uuid=NULL) remain backward-compatible: they were
        encrypted without AAD and will be re-encrypted with a UUID on next unlock.
        """
        try:
            with self.managed_connection(write=True) as conn:
                for table in ("snippets", "custom_placeholders"):
                    cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
                    if "vault_uuid" not in cols:
                        conn.execute(f"ALTER TABLE {table} ADD COLUMN vault_uuid TEXT DEFAULT NULL")
                        logger.info("Migrated: added vault_uuid to %s", table)
        except sqlite3.Error as exc:
            logger.warning("AAD binding schema migration failed: %s", exc)

    def migrate_custom_placeholders_vault_schema(self) -> None:
        """Add is_encrypted column to custom_placeholders if it does not exist (migration)."""
        try:
            with self.managed_connection(write=True) as conn:
                cols = [row[1] for row in conn.execute("PRAGMA table_info(custom_placeholders)").fetchall()]
                if "is_encrypted" not in cols:
                    conn.execute("ALTER TABLE custom_placeholders ADD COLUMN is_encrypted BOOLEAN NOT NULL DEFAULT 0")
                    logger.info("Migrated: added is_encrypted column to custom_placeholders")
        except sqlite3.Error as exc:
            logger.warning("Custom placeholder vault migration failed: %s", exc)

    def create_vault_folders_table(self) -> None:
        """Create the vault_folders table if it does not exist."""
        try:
            with self.managed_connection(write=True) as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS vault_folders (
                        id          INTEGER PRIMARY KEY AUTOINCREMENT,
                        folder_path TEXT UNIQUE NOT NULL
                    )
                """)
        except sqlite3.Error as exc:
            raise DatabaseOperationError(f"Failed to create vault_folders table: {exc}") from exc

    def add_vault_folder(self, path: str) -> None:
        try:
            with self.managed_connection(write=True) as conn:
                conn.execute("INSERT OR IGNORE INTO vault_folders (folder_path) VALUES (?)", (path,))
        except sqlite3.Error as exc:
            raise DatabaseOperationError(f"Failed to add vault folder '{path}': {exc}") from exc

    def remove_vault_folder(self, path: str) -> None:
        try:
            with self.managed_connection(write=True) as conn:
                conn.execute("DELETE FROM vault_folders WHERE folder_path = ?", (path,))
        except sqlite3.Error as exc:
            raise DatabaseOperationError(f"Failed to remove vault folder '{path}': {exc}") from exc

    def get_vault_folders(self) -> List[str]:
        try:
            with self.managed_connection() as conn:
                rows = conn.execute("SELECT folder_path FROM vault_folders").fetchall()
            return [r[0] for r in rows]
        except sqlite3.Error as exc:
            raise DatabaseOperationError(f"Failed to get vault folders: {exc}") from exc

    def is_vault_folder(self, path: str) -> bool:
        try:
            with self.managed_connection() as conn:
                row = conn.execute(
                    "SELECT 1 FROM vault_folders WHERE folder_path = ?", (path,)
                ).fetchone()
            return row is not None
        except sqlite3.Error:
            return False

    def clear_vault_folders(self) -> None:
        try:
            with self.managed_connection(write=True) as conn:
                conn.execute("DELETE FROM vault_folders")
        except sqlite3.Error as exc:
            raise DatabaseOperationError(f"Failed to clear vault folders: {exc}") from exc

    def get_vault_snippets(self) -> List[Dict[str, Any]]:
        """Return all snippets that are marked is_encrypted=1."""
        try:
            with self.managed_connection() as conn:
                cur = conn.cursor()
                cur.execute("SELECT * FROM snippets WHERE is_encrypted = 1")
                return [self.normalize_snippet_row(r) for r in cur.fetchall()]
        except sqlite3.Error as exc:
            raise DatabaseOperationError(f"Failed to get vault snippets: {exc}") from exc

    def update_snippet_vault_uuid(self, snippet_id: int, new_blob: str, vault_uuid: str) -> None:
        """Update the encrypted blob and vault_uuid for an existing vault snippet.

        Used by the AAD migration pass to re-encrypt legacy (no-AAD) blobs and
        assign each snippet a vault_uuid that acts as AES-GCM additional
        authenticated data, binding the ciphertext to this specific row.
        """
        try:
            with self.managed_connection(write=True) as conn:
                conn.execute(
                    "UPDATE snippets SET snippet=?, vault_uuid=? WHERE id=?",
                    (new_blob, vault_uuid, snippet_id),
                )
        except sqlite3.Error as exc:
            raise DatabaseOperationError(
                f"Failed to update vault_uuid for snippet {snippet_id}: {exc}"
            ) from exc

    def set_snippet_vault_uuid(self, snippet_id: int, vault_uuid: str) -> None:
        """Assign vault_uuid to a snippet without changing the blob (post-insert binding)."""
        try:
            with self.managed_connection(write=True) as conn:
                conn.execute(
                    "UPDATE snippets SET vault_uuid=? WHERE id=?",
                    (vault_uuid, snippet_id),
                )
        except sqlite3.Error as exc:
            raise DatabaseOperationError(
                f"Failed to set vault_uuid for snippet {snippet_id}: {exc}"
            ) from exc

    def set_placeholder_vault_uuid(self, placeholder_id: int, vault_uuid: str) -> None:
        """Assign vault_uuid to a placeholder without changing the blob (post-insert binding)."""
        try:
            with self.managed_connection(write=True) as conn:
                conn.execute(
                    "UPDATE custom_placeholders SET vault_uuid=? WHERE id=?",
                    (vault_uuid, placeholder_id),
                )
        except sqlite3.Error as exc:
            raise DatabaseOperationError(
                f"Failed to set vault_uuid for placeholder {placeholder_id}: {exc}"
            ) from exc

    def update_placeholder_vault_uuid(self, placeholder_id: int, new_blob: str, vault_uuid: str) -> None:
        """Update the encrypted blob and vault_uuid for an existing encrypted placeholder."""
        try:
            with self.managed_connection(write=True) as conn:
                conn.execute(
                    "UPDATE custom_placeholders SET value=?, vault_uuid=? WHERE id=?",
                    (new_blob, vault_uuid, placeholder_id),
                )
        except sqlite3.Error as exc:
            raise DatabaseOperationError(
                f"Failed to update vault_uuid for placeholder {placeholder_id}: {exc}"
            ) from exc

    def get_vault_placeholders(self) -> List[Dict[str, Any]]:
        """Return all custom_placeholders that are marked is_encrypted=1."""
        try:
            with self.managed_connection() as conn:
                cur = conn.cursor()
                cur.execute("SELECT * FROM custom_placeholders WHERE is_encrypted = 1")
                return [dict(r) for r in cur.fetchall()]
        except sqlite3.Error as exc:
            raise DatabaseOperationError(f"Failed to get vault placeholders: {exc}") from exc

    def get_snippets_by_folder(self, folder: str) -> List[Dict[str, Any]]:
        """Return all snippets in the given folder path (exact match only)."""
        try:
            escaped = self.escape_like_value(folder)
            with self.managed_connection() as conn:
                cur = conn.cursor()
                cur.execute(
                    "SELECT * FROM snippets WHERE folder = ? OR folder LIKE ? ESCAPE '\\'",
                    (folder, f"{escaped}/%"),
                )
                return [self.normalize_snippet_row(r) for r in cur.fetchall()]
        except sqlite3.Error as exc:
            raise DatabaseOperationError(f"Failed to get snippets for folder '{folder}': {exc}") from exc

    def update_snippet_content(self, snippet_id: int, content: str) -> None:
        try:
            with self.managed_connection(write=True) as conn:
                conn.execute("UPDATE snippets SET snippet = ? WHERE id = ?", (content, snippet_id))
        except sqlite3.Error as exc:
            raise DatabaseOperationError(f"Failed to update snippet content for id {snippet_id}: {exc}") from exc

    def bulk_update_snippet_content(self, updates: list) -> None:
        """Write all (snippet_id, content) pairs in a single atomic transaction."""
        if not updates:
            return
        try:
            with self.managed_connection(write=True) as conn:
                conn.executemany(
                    "UPDATE snippets SET snippet = ? WHERE id = ?",
                    [(content, sid) for sid, content in updates],
                )
        except sqlite3.Error as exc:
            raise DatabaseOperationError(f"Failed to bulk-update snippet content: {exc}") from exc

    def bulk_encrypt_folder_snippets(self, updates: list) -> None:
        """Atomically update snippet content, is_encrypted flag, and vault_uuid for a folder move.

        Args:
            updates: list of ``(snippet_id, new_content, is_encrypted_flag, vault_uuid)`` tuples.
        """
        if not updates:
            return
        try:
            with self.managed_connection(write=True) as conn:
                conn.executemany(
                    "UPDATE snippets SET snippet = ?, is_encrypted = ?, vault_uuid = ? WHERE id = ?",
                    [(content, 1 if flag else 0, vault_uuid, sid) for sid, content, flag, vault_uuid in updates],
                )
        except sqlite3.Error as exc:
            raise DatabaseOperationError(f"Failed to bulk-update folder snippets: {exc}") from exc

    def is_under_vault_folder(self, path: str) -> bool:
        """Return True if path is a vault folder root or is nested inside one.

        Unlike ``is_vault_folder`` (exact match), this walks up the path hierarchy
        so that e.g. ``"Vault/work"`` returns True when ``"Vault"`` is a vault root.
        """
        if self.is_vault_folder(path):
            return True
        parts = path.split("/")
        for depth in range(len(parts) - 1, 0, -1):
            if self.is_vault_folder("/".join(parts[:depth])):
                return True
        return False

    def update_snippet_folder(self, snippet_id: int, folder: str) -> None:
        try:
            with self.managed_connection(write=True) as conn:
                conn.execute("UPDATE snippets SET folder = ? WHERE id = ?", (folder, snippet_id))
        except sqlite3.Error as exc:
            raise DatabaseOperationError(f"Failed to update snippet folder for id {snippet_id}: {exc}") from exc

    def set_snippet_encrypted(self, snippet_id: int, is_encrypted: bool) -> None:
        try:
            with self.managed_connection(write=True) as conn:
                conn.execute(
                    "UPDATE snippets SET is_encrypted = ? WHERE id = ?",
                    (1 if is_encrypted else 0, snippet_id),
                )
        except sqlite3.Error as exc:
            raise DatabaseOperationError(f"Failed to set is_encrypted for id {snippet_id}: {exc}") from exc

    def insert_snippet_vault_aware(
        self,
        entry: Dict[str, Any],
        vault_manager=None,
    ) -> bool:
        """Insert or update a snippet, auto-encrypting or decrypting based on vault state.

        Inspects the source encryption state (``entry["is_encrypted"]``) and the
        destination folder to decide whether to encrypt, decrypt, or leave the
        content unchanged before writing to the database.

        This method is the single gate for all vault encrypt/decrypt transitions.
        Import, drag-drop, and any future programmatic write should use this
        instead of ``insert_snippet()`` so the invariant is enforced at the data
        layer regardless of which UI path triggers the write.

        Args:
            entry: Snippet data dict.  ``entry["folder"]`` is the **destination**
                folder; ``entry["is_encrypted"]`` reflects the **current** DB
                state; ``entry["snippet"]`` holds the current content (an
                encrypted blob when ``is_encrypted`` is ``True``).
            vault_manager: A ``VaultManager`` instance used for encrypt/decrypt.
                Pass ``None`` to skip vault handling (treats as a plain insert).

        Returns:
            bool: ``True`` if a new snippet was inserted, ``False`` if updated.

        Raises:
            VaultError: If the snippet must be encrypted/decrypted but the vault
                is locked (``vault_manager.is_unlocked()`` is ``False``).
        """
        from utils.vault_manager import VaultError

        src_encrypted = bool(entry.get("is_encrypted"))
        dest_is_vault = self.is_vault_folder(entry.get("folder", ""))

        entry = dict(entry)  # don't mutate caller's dict
        new_is_encrypted = src_encrypted
        new_vault_uuid = entry.get("vault_uuid")

        if src_encrypted and not dest_is_vault:
            # Moving out of vault - must decrypt content before storing
            if not vault_manager or not vault_manager.is_unlocked():
                raise VaultError(
                    "Vault must be unlocked to move encrypted snippets out of the vault."
                )
            aad = (entry.get("vault_uuid") or "").encode()
            entry["snippet"] = vault_manager.decrypt(entry["snippet"], aad=aad)
            new_is_encrypted = False
            new_vault_uuid = None

        elif not src_encrypted and dest_is_vault:
            # Moving into vault - must encrypt content before storing
            if not vault_manager or not vault_manager.is_unlocked():
                raise VaultError(
                    "Vault must be unlocked to save snippets into a vault folder."
                )
            import uuid as _uuid
            new_vault_uuid = str(_uuid.uuid4())
            entry["snippet"] = vault_manager.encrypt(entry["snippet"], aad=new_vault_uuid.encode())
            new_is_encrypted = True

        result = self.insert_snippet(entry)

        if new_is_encrypted != src_encrypted:
            snippet_id = entry.get("id")
            if snippet_id is not None:
                self.set_snippet_encrypted(snippet_id, new_is_encrypted)
                self.set_snippet_vault_uuid(snippet_id, new_vault_uuid)

        return result

    # Close Connection
    def close(self) -> None:
        """
        Close the database connection.
        
        Returns:
            None
        """
        logger.info("Closing database connection.")
        try:
            with self.lock:
                if self.closed:
                    logger.debug("Database connection already closed")
                    return

                self.conn.close()
                self.closed = True
            logger.info("Database connection closed successfully.")
        except sqlite3.Error as e:
            logger.exception("Failed to close database connection")
            # Don't raise here - this is cleanup code

    def __enter__(self):
        """
        Enter a context manager scope for the database instance.
        
        Returns:
            SnippetDB: The current database instance.
        """
        self.ensure_open()
        return self

    def __exit__(self, exc_type, exc, exc_tb) -> None:
        """
        Exit a context manager scope and close the database connection.
        
        Returns:
            None
        """
        self.close()

    def __del__(self) -> None:
        """
        Best-effort cleanup for the SQLite connection.
        
        Returns:
            None
        """
        try:
            self.close()
        except Exception:
            logger.debug("Database cleanup during object destruction failed", exc_info=True)

import logging
from pathlib import Path
from datetime import datetime

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QCheckBox, QAbstractItemView,
    QHeaderView, QFileDialog, QMessageBox
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

from utils.file_utils import FileUtils

logger = logging.getLogger(__name__)


def classify_snippets(snippets: list[dict], db) -> list[dict]:
    """Add 'status' key to each snippet: 'New' or 'Update' based on trigger in DB."""
    for s in snippets:
        existing = db.get_snippet_by_trigger(s.get("trigger", ""))
        s["status"] = "Update" if existing else "New"
    return snippets


class ImportExportWizard(QDialog):
    """
    Dialog for importing or exporting snippets with selection control.

    Modes:
    - "import": Load YAML, show preview with New/Update status, select which to import
    - "export": Load from DB, select which to export, save to YAML
    """

    def __init__(self, mode: str, snippet_db, import_path=None, parent=None):
        """
        Initialize the wizard.

        Args:
            mode (str): "import" or "export"
            snippet_db: SnippetDB instance
            import_path (Path | None): For import mode, the YAML file path
            parent: Parent widget
        """
        super().__init__(parent)
        self.mode = mode
        self.snippet_db = snippet_db
        self.import_path = import_path
        self.snippets = []

        title = "Import Snippets" if mode == "import" else "Export Snippets"
        self.setWindowTitle(title)
        self.resize(900, 600)
        self.setMinimumSize(700, 400)

        self.build_ui()

        if mode == "import":
            self.load_for_import(import_path)
        else:
            self.load_for_export()

        logger.debug(f"ImportExportWizard initialized in {mode} mode")

    def build_ui(self) -> None:
        """Construct the dialog UI."""
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        # Title
        title_label = QLabel(
            "Select Snippets to Import" if self.mode == "import"
            else "Select Snippets to Export"
        )
        title_font = title_label.font()
        title_font.setPointSize(11)
        title_font.setBold(True)
        title_label.setFont(title_font)
        root.addWidget(title_label)

        # Select all checkbox + count label
        checkbox_row = QHBoxLayout()
        self.select_all_checkbox = QCheckBox("Select All")
        self.select_all_checkbox.setChecked(True)
        self.select_all_checkbox.stateChanged.connect(self.on_select_all_toggled)
        checkbox_row.addWidget(self.select_all_checkbox)

        self.count_label = QLabel("0 / 0 selected")
        self.count_label.setStyleSheet("color: gray; margin-left: 12px;")
        checkbox_row.addWidget(self.count_label)
        checkbox_row.addStretch()

        root.addLayout(checkbox_row)

        # Table
        self.table = QTableWidget()
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)

        # Set columns based on mode
        if self.mode == "import":
            columns = ["", "Label", "Trigger", "Folder", "Tags", "Status"]
            col_count = 6
        else:
            columns = ["", "Label", "Trigger", "Folder", "Tags"]
            col_count = 5

        self.table.setColumnCount(col_count)
        self.table.setHorizontalHeaderLabels(columns)

        # Configure column widths
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)  # checkbox col
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)  # label
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)  # trigger
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)           # folder
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)  # tags
        if self.mode == "import":
            self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeToContents)  # status

        # Connect checkbox changes to update count
        self.table.itemChanged.connect(self.update_selection_count)

        root.addWidget(self.table)

        # Button bar
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_button)

        action_text = "Import" if self.mode == "import" else "Export"
        self.action_button = QPushButton(action_text)
        self.action_button.clicked.connect(self.on_confirm)
        button_layout.addWidget(self.action_button)

        root.addLayout(button_layout)

    def load_for_export(self) -> None:
        """Load all DB snippets into the table for export."""
        logger.debug("Loading snippets for export")
        self.snippets = self.snippet_db.get_all_snippets() or []
        logger.debug(f"Loaded {len(self.snippets)} snippets for export")

        self.populate_table()

    def load_for_import(self, path: Path) -> None:
        """
        Load YAML file with full validation and populate table with import status.

        Security checks applied:
        - File size validation (50MB max)
        - YAML parsing timeout (10s)
        - Field type/length validation
        - Unknown field stripping
        """
        logger.debug(f"Loading YAML for import: {path}")

        try:
            # Import with full validation (file size, timeout, field validation)
            self.snippets = FileUtils.import_snippets_yaml(path)
            self.snippets = classify_snippets(self.snippets, self.snippet_db)
            logger.debug(f"Loaded {len(self.snippets)} snippets from {path}")
        except (ValueError, TypeError) as e:
            logger.exception(f"YAML validation failed: {e}")
            QMessageBox.critical(self, "Import Error", f"Invalid YAML file:\n\n{str(e)}")
            self.reject()
            return
        except TimeoutError as e:
            logger.exception(f"YAML parsing timeout: {e}")
            QMessageBox.critical(
                self,
                "Import Error",
                "YAML file took too long to parse. File may be corrupted or too complex."
            )
            self.reject()
            return
        except Exception as e:
            logger.exception(f"Failed to load import YAML: {e}")
            QMessageBox.critical(self, "Import Error", f"Failed to load YAML file:\n\n{str(e)}")
            self.reject()
            return

        self.populate_table()

    def populate_table(self) -> None:
        """Fill the table with snippet rows and checkboxes."""
        self.table.setRowCount(len(self.snippets))

        for row_idx, snippet in enumerate(self.snippets):
            # Checkbox column
            checkbox_item = QTableWidgetItem()
            checkbox_item.setFlags(checkbox_item.flags() | Qt.ItemIsUserCheckable)
            checkbox_item.setCheckState(Qt.Checked)
            # Store snippet data on checkbox item
            checkbox_item.setData(Qt.UserRole, snippet)
            self.table.setItem(row_idx, 0, checkbox_item)

            # Label
            label_item = QTableWidgetItem(snippet.get("label", ""))
            label_item.setFlags(label_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row_idx, 1, label_item)

            # Trigger
            trigger_item = QTableWidgetItem(snippet.get("trigger", ""))
            trigger_item.setFlags(trigger_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row_idx, 2, trigger_item)

            # Folder
            folder_item = QTableWidgetItem(snippet.get("folder", ""))
            folder_item.setFlags(folder_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row_idx, 3, folder_item)

            # Tags
            tags_item = QTableWidgetItem(snippet.get("tags", ""))
            tags_item.setFlags(tags_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row_idx, 4, tags_item)

            # Status (import only)
            if self.mode == "import":
                status = snippet.get("status", "Unknown")
                status_item = QTableWidgetItem(status)
                status_item.setFlags(status_item.flags() & ~Qt.ItemIsEditable)
                # Color code text: green for New, orange for Update
                if status == "New":
                    status_item.setForeground(QColor(100, 180, 100))
                elif status == "Update":
                    status_item.setForeground(QColor(200, 140, 50))
                self.table.setItem(row_idx, 5, status_item)

        # Update selection count
        self.update_selection_count()

    def on_select_all_toggled(self) -> None:
        """Handle Select All checkbox state change."""
        # Block table signals while updating to avoid recursion
        self.table.blockSignals(True)

        # Use checkbox's actual check state instead of signal parameter
        check_state = self.select_all_checkbox.checkState()
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item:
                item.setCheckState(check_state)

        # Re-enable signals and update count
        self.table.blockSignals(False)
        self.update_selection_count()

    def get_selected_snippets(self) -> list[dict]:
        """Return list of checked snippet dicts."""
        selected = []
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item and item.checkState() == Qt.Checked:
                snippet = item.data(Qt.UserRole)
                selected.append(snippet)
        return selected

    def _update_count_only(self) -> None:
        """Update just the count label and button state."""
        total = self.table.rowCount()
        selected = len(self.get_selected_snippets())
        self.count_label.setText(f"{selected} / {total} selected")
        # Enable/disable action button based on selection
        self.action_button.setEnabled(selected > 0)

    def update_selection_count(self) -> None:
        """Update the selection count label and sync Select All checkbox."""
        self._update_count_only()

        # Sync Select All checkbox state (called when individual rows change, not from checkbox handler)
        if self.table.rowCount() > 0:
            self.select_all_checkbox.blockSignals(True)
            selected = len(self.get_selected_snippets())
            # Check if all are selected (not just "some")
            self.select_all_checkbox.setChecked(selected == self.table.rowCount())
            self.select_all_checkbox.blockSignals(False)

    def on_confirm(self) -> None:
        """Handle Import/Export button click."""
        selected = self.get_selected_snippets()

        if not selected:
            QMessageBox.warning(self, "No Selection", "Please select at least one snippet.")
            return

        if self.mode == "import":
            self.do_import(selected)
        else:
            self.do_export(selected)

    def do_import(self, snippets: list[dict]) -> None:
        """Import selected snippets into database."""
        logger.debug(f"Importing {len(snippets)} selected snippets")

        # Log snapshot of DB before import
        db_before = len(self.snippet_db.get_all_snippets() or [])
        logger.info(f"DB before import: {db_before} snippets")

        new_count = 0
        updated_count = 0
        error_count = 0

        for entry in snippets:
            # Strip internal database IDs to prevent ID-based conflicts
            # IDs should be auto-generated on import, not preserved from old databases
            clean_entry = {k: v for k, v in entry.items() if k != "id"}

            is_new = self.snippet_db.insert_snippet(clean_entry)
            if is_new is True:
                new_count += 1
            elif is_new is False:
                updated_count += 1
            else:
                error_count += 1
                logger.warning(f"Insert error for trigger: {entry.get('trigger')}")

        # Log snapshot of DB after import
        db_after = len(self.snippet_db.get_all_snippets() or [])
        logger.info(f"DB after import: {db_after} snippets (before: {db_before})")
        logger.info(f"Import complete: {new_count} new, {updated_count} updated, {error_count} errors")

        QMessageBox.information(
            self,
            "Import Complete",
            f"Imported {new_count} new snippets.\nUpdated {updated_count} existing snippets."
        )
        self.accept()

    def do_export(self, snippets: list[dict]) -> None:
        """Export selected snippets to YAML file."""
        date = datetime.now().date()
        default_name = f"qsnippets-export-{date}.yaml"

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Snippets to YAML",
            str(Path.home() / default_name),
            "YAML Files (*.yaml *.yml)",
        )

        if not path:
            logger.debug("Export cancelled by user")
            return

        try:
            logger.debug(f"Exporting {len(snippets)} snippets to {path}")
            FileUtils.export_snippets_yaml(Path(path), snippets)
            logger.info(f"Export complete: {len(snippets)} snippets to {path}")

            QMessageBox.information(
                self,
                "Export Complete",
                f"Exported {len(snippets)} snippets.",
            )
            self.accept()
        except Exception as e:
            logger.exception(f"Export failed: {e}")
            QMessageBox.critical(
                self,
                "Export Error",
                f"Failed to export snippets:\n{e}"
            )

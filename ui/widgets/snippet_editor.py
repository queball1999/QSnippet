import yaml
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QSplitter, QStackedWidget, QVBoxLayout, QMessageBox, QInputDialog,
    QLineEdit, QLabel, QHBoxLayout, QComboBox
)
from PySide6.QtGui import QIcon, QStandardItem
from PySide6.QtCore import Qt, Signal

from .snippet_table import SnippetTable
from .snippet_form  import SnippetForm
from .home_widget   import HomeWidget


class SnippetEditor(QWidget):
    trigger_reload = Signal()

    def __init__(self, config_path, main, parent=None):
        super().__init__()
        self.config_path = Path(config_path)
        self.main = main
        self.parent = parent

        self.initUI()
        self.load_config()

    def initUI(self):
        self.splitter = QSplitter(Qt.Horizontal, self)

        self.left_layout = QVBoxLayout()

        # Search bar and filters
        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("Search all the things...")
        self.search_bar.textChanged.connect(self.run_search)

        self.filter_dropdown = QComboBox()
        self.filter_dropdown.addItem("All Snippets")
        self.filter_dropdown.addItem("Enabled Only")
        self.filter_dropdown.addItem("Disabled Only")
        self.filter_dropdown.currentIndexChanged.connect(self.run_search)

        search_layout = QHBoxLayout()
        search_layout.addWidget(self.search_bar)
        search_layout.addWidget(self.filter_dropdown)

        # Left: snippet table
        self.table = SnippetTable(main=self.main, parent=self)
        self.table.entrySelected.connect(self.on_entry_selected)
        self.table.refreshSignal.connect(self.load_config)
        # folder signals
        self.table.addFolder.connect(self.on_add_folder)
        self.table.addSubFolder.connect(self.on_add_subfolder)
        self.table.renameFolder.connect(self.on_rename_folder)
        self.table.deleteFolder.connect(self.on_delete_folder)
        # snippet signals
        self.table.addSnippet.connect(self.on_add_snippet)
        self.table.editSnippet.connect(self.on_edit_snippet)
        self.table.renameSnippet.connect(self.on_rename_snippet)
        self.table.deleteSnippet.connect(self.on_delete_snippet)

        # Right: stack of home + form
        self.home_widget = HomeWidget(main=self.main, parent=self)
        self.home_widget.new_snippet.connect(self.show_new_form)

        self.form = SnippetForm(main=self.main, parent=self)
        self.form.newClicked.connect(self.show_new_form)
        self.form.saveClicked.connect(self.on_save)
        self.form.deleteClicked.connect(self.on_delete)
        self.form.cancelPressed.connect(self.show_home_widget)

        # Layout
        self.left_layout.addLayout(search_layout)
        self.left_layout.addWidget(self.table)
        self.left_widget = QWidget()
        self.left_widget.setLayout(self.left_layout)

        self.stack = QStackedWidget()
        self.stack.addWidget(self.home_widget)
        self.stack.addWidget(self.form)
        self.stack.setCurrentWidget(self.home_widget)

        self.splitter.addWidget(self.left_widget)
        self.splitter.addWidget(self.stack)

        # layout just needs to host the splitter
        container = QWidget(self)
        vlay = QVBoxLayout(container)
        vlay.addWidget(self.splitter)
        container.setLayout(vlay)
        self.setLayout(vlay)

    def load_config_old(self):
        # Set status label
        old_text = self.parent.statusBar().currentMessage()
        self.parent.statusBar().showMessage(f"Loading Snippets...")
        # Load config
        if not self.config_path.exists():
            return
        data = yaml.safe_load(self.config_path.read_text()) or {}
        self.table.load_entries(data.get('snippets', []))

        # Restore original text
        self.parent.statusBar().showMessage(old_text)
    
    def load_config(self):
        old_text = self.parent.statusBar().currentMessage()
        self.parent.statusBar().showMessage(f"Loading Snippets...")
        snippets = self.main.snippet_db.get_all_snippets()
        self.table.load_entries(snippets)
        self.parent.statusBar().showMessage(old_text)

    def on_entry_selected(self, entry):
        #print(f"Entry: {entry}")
        if entry:
            self.form.clear_form()
            self.stack.setCurrentWidget(self.form)
            self.form.load_entry(entry)
        else:
            self.stack.setCurrentWidget(self.home_widget)    

    def show_home_widget(self):
        # Should deselect any selected items in tree view
        self.stack.setCurrentWidget(self.home_widget)

    def show_new_form(self):
        # Clear the table selection and form inputs, then swap in form
        self.table.clear_selection()
        self.form.clear_form()
        self.stack.setCurrentWidget(self.form)

    def on_save_old(self):
        try:
            if not self.form.validate():
                return
            entry = self.form.get_entry()
            data = yaml.safe_load(self.config_path.read_text()) or {}
            snippets = data.get('snippets', [])

            # replace or append
            for i, e in enumerate(snippets):
                if e.get('trigger') == entry['trigger']:
                    snippets[i] = entry
                    break
            else:
                snippets.append(entry)

            data['snippets'] = snippets
            self.config_path.write_text(yaml.safe_dump(data), encoding='utf-8')

            # refresh table and re-select
            self.load_config()
            self.table.select_entry(entry)
            QMessageBox.information(None, 'Snippet Saved', 'Snippet Saved Successfully!')
        except:
            # Need to log this section for this error to make sense
            QMessageBox.information(None, 'Save Failed', 'Snippet Save Failed. See log for details.')

    def on_save(self):
        try:
            if not self.form.validate():
                return
            entry = self.form.get_entry()
            print(f"Save Entry: {entry}")
            self.main.snippet_db.insert_snippet(entry)
            self.load_config()
            self.table.select_entry(entry)
            self.show_new_form()
            self.trigger_reload.emit()  # Flag
            QMessageBox.information(None, 'Snippet Saved', 'Snippet Saved Successfully!')
        except Exception as e:
            QMessageBox.information(None, 'Save Failed', f'Snippet Save Failed: {e}')

    def on_delete_old(self):
        entry = self.table.current_entry()
        if not entry:
            return
        data = yaml.safe_load(self.config_path.read_text()) or {}
        data['snippets'] = [
            e for e in data.get('snippets', [])
            if e.get('trigger') != entry['trigger']
        ]
        self.config_path.write_text(yaml.safe_dump(data), encoding='utf-8')

        self.load_config()
        # go back to home screen after delete
        self.stack.setCurrentIndex(0)

    def on_delete(self):
        entry = self.table.current_entry()
        if not entry:
            return
        self.main.snippet_db.delete_snippet(entry["trigger"])
        self.load_config()
        self.stack.setCurrentIndex(0)

    # ----- Context Menu Actions -----
    def on_add_folder(self, parent_item):
        name, ok = QInputDialog.getText(self, 'New Folder', 'Folder name:')
        if not ok or not name.strip():
            return
        self.show_new_form()
        self.form.folder_input.setText(name.strip())

    def on_add_subfolder(self, parent_item):
        parent_name = parent_item.text()
        prompt = f'Sub-folder under "{parent_name}":'
        name, ok = QInputDialog.getText(self, 'New Sub-Folder', prompt)
        if not ok or not name.strip():
            return
        full = f"{parent_name}/{name.strip()}"
        self.show_new_form()
        self.form.folder_input.setText(full)

    def on_rename_folder_old(self, folder_item):
        old = folder_item.text()
        new, ok = QInputDialog.getText(self, 'Rename Folder',
                                       f'New name for "{old}":', text=old)
        if not ok or not new.strip() or new.strip() == old:
            return
        for sn in self.snippets:
            if sn.get('folder') == old:
                sn['folder'] = new.strip()
        self._save_snippets()
        QMessageBox.information(self, 'Folder Renamed',
                                f'"{old}" → "{new.strip()}"')
        
    def on_rename_folder(self, folder_item):
        old = folder_item.text()
        new, ok = QInputDialog.getText(self, 'Rename Folder', f'New name for "{old}":', text=old)
        if not ok or not new.strip() or new.strip() == old:
            return
        self.main.snippet_db.rename_folder(old, new.strip())
        self.load_config()
        QMessageBox.information(self, 'Folder Renamed', f'"{old}" → "{new.strip()}"')


    def on_delete_folder_old(self, folder_item):
        name = folder_item.text()
        confirm = QMessageBox.question(
            self, 'Delete Folder',
            f'Delete folder "{name}" and all its snippets?'
        )
        if confirm != QMessageBox.Yes:
            return
        self.snippets = [
            sn for sn in self.snippets
            if sn.get('folder') != name
        ]
        self._save_snippets()

    def on_add_snippet(self, parent_item):
        self.show_new_form()
        if isinstance(parent_item, QStandardItem):
            self.form.folder_input.setText(parent_item.text())

    def on_delete_folder(self, folder_item):
        name = folder_item.text()
        confirm = QMessageBox.question(
            self, 'Delete Folder',
            f'Delete folder "{name}" and all its snippets?'
        )
        if confirm != QMessageBox.Yes:
            return
        self.main.snippet_db.delete_folder(name)
        self.load_config()

    def on_edit_snippet(self, entry):
        self.on_entry_selected(entry)

    def on_rename_snippet_old(self, entry):
        old_label = entry.get('label', '')
        new_label, ok = QInputDialog.getText(
            self, 'Rename Snippet', 'New label:', text=old_label
        )
        if not ok or not new_label.strip() or new_label == old_label:
            return
        for sn in self.snippets:
            if sn['trigger'] == entry['trigger']:
                sn['label'] = new_label.strip()
                break
        self._save_snippets()
        QMessageBox.information(self, 'Snippet Renamed',
                                f'"{old_label}" → "{new_label.strip()}"')

    def on_rename_snippet(self, entry):
        old_label = entry.get('label', '')
        new_label, ok = QInputDialog.getText(
            self, 'Rename Snippet', 'New label:', text=old_label
        )
        if not ok or not new_label.strip() or new_label == old_label:
            return
        self.main.snippet_db.rename_snippet(entry['trigger'], new_label.strip())
        self.load_config()
        QMessageBox.information(self, 'Snippet Renamed', f'"{old_label}" → "{new_label.strip()}"')

    def on_delete_snippet_old(self, entry):
        confirm = QMessageBox.question(
            self, 'Delete Snippet',
            f'Delete snippet "{entry.get("label","")}"?'
        )
        if confirm != QMessageBox.Yes:
            return
        self.snippets = [
            sn for sn in self.snippets
            if sn['trigger'] != entry['trigger']
        ]
        self._save_snippets()
    
    def on_delete_snippet(self, entry):
        confirm = QMessageBox.question(
            self, 'Delete Snippet',
            f'Delete snippet "{entry.get("label","")}"?'
        )
        if confirm != QMessageBox.Yes:
            return
        self.main.snippet_db.delete_snippet(entry['trigger'])
        self.load_config()

    def run_search(self):
        keyword = self.search_bar.text().strip()
        filter_mode = self.filter_dropdown.currentText()

        # Get results from DB
        results = self.main.snippet_db.search_snippets(keyword)

        # Filter further if enabled/disabled only is selected
        if filter_mode == "Enabled Only":
            results = [s for s in results if s.get("enabled", True)]
        elif filter_mode == "Disabled Only":
            results = [s for s in results if not s.get("enabled", False)]

        self.table.load_entries(results)

    def applyStyles(self):
        """Fucntion to call when you need toupdate the UI. """
        self.home_widget.applyStyles()
        self.form.applyStyles()
        self.update()
        self.main.app.processEvents()

    def update_stylesheet(self):
        """ This function handles updating the stylesheet. """
        #self.setStyleSheet(f""" """)
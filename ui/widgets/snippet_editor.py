import yaml
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QSplitter, QStackedWidget, QVBoxLayout, QMessageBox
)
from PySide6.QtGui     import QIcon
from PySide6.QtCore    import Qt

from .snippet_table import SnippetTable
from .snippet_form  import SnippetForm
from .home_widget   import HomeWidget


class SnippetEditor(QWidget):
    def __init__(self, config_path, parent=None):
        super().__init__()
        self.config_path = Path(config_path)
        self.parent = parent

        self.initUI()
        self.load_config()

    def initUI(self):
        self.splitter = QSplitter(Qt.Horizontal, self)

        # Left: snippet table
        self.table = SnippetTable()
        self.table.entrySelected.connect(self.on_entry_selected)
        self.splitter.addWidget(self.table)

        # Right: stack of home + form
        self.home_widget = HomeWidget()
        self.home_widget.new_snippet.connect(self.show_new_form)

        self.form = SnippetForm()
        self.form.newClicked.connect(self.show_new_form)
        self.form.saveClicked.connect(self.on_save)
        self.form.deleteClicked.connect(self.on_delete)
        self.form.cancelPressed.connect(self.show_home_widget)

        self.stack = QStackedWidget()
        self.stack.addWidget(self.home_widget)
        self.stack.addWidget(self.form)
        self.stack.setCurrentWidget(self.home_widget)
        self.splitter.addWidget(self.stack)

        # layout just needs to host the splitter
        container = QWidget(self)
        vlay = QVBoxLayout(container)
        vlay.addWidget(self.splitter)
        container.setLayout(vlay)
        self.setLayout(vlay)

    def load_config(self):
        if not self.config_path.exists():
            return
        data = yaml.safe_load(self.config_path.read_text()) or {}
        self.table.load_entries(data.get('snippets', []))

    def on_entry_selected(self, entry):
        print(f"Entry: {entry}")
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

    def on_save(self):
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

    def on_delete(self):
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

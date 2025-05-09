import yaml
from pathlib import Path
from PySide6.QtWidgets import QWidget, QSplitter, QMessageBox
from PySide6.QtGui import QIcon
from PySide6.QtCore import Qt

from .snippet_table import SnippetTable
from .snippet_form import SnippetForm

class SnippetEditor(QWidget):
    def __init__(self, config_path, parent=None):
        super().__init__()
        self.config_path = Path(config_path)
        self.parent = parent
        self.setWindowTitle('QSnippet')
        self.setWindowIcon(QIcon(self.parent.program_icon))
        self.resize(800, 500)
        self.initUI()
        self.load_config()

    def initUI(self):
        self.splitter = QSplitter(Qt.Horizontal, self)

        # Table/Tree widget
        self.table = SnippetTable()
        self.table.entrySelected.connect(self.on_entry_selected)
        self.splitter.addWidget(self.table)

        # Detail form
        self.form = SnippetForm()
        self.form.newClicked.connect(self.on_new)
        self.form.saveClicked.connect(self.on_save)
        self.form.deleteClicked.connect(self.on_delete)
        self.splitter.addWidget(self.form)

        layout = QWidget(self)
        self.setLayout(self.splitter.layout())

    def load_config(self):
        # Read YAML and forward to table
        if not self.config_path.exists():
            return
        data = yaml.safe_load(self.config_path.read_text()) or {}
        snippets = data.get('snippets', [])
        self.table.load_entries(snippets)

    def on_entry_selected(self, entry):
        # Populate form or show message
        if entry:
            self.form.load_entry(entry)
        else:
            self.form.display_message(
                'Uh oh, nothing selected. Create a new snippet or select one.'
            )

    def on_new(self):
        self.table.clear_selection()
        self.form.clear_form()

    def on_save(self):
        if not self.form.validate():
            return
        entry = self.form.get_entry()
        # update YAML
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
        with open(self.config_path, 'w', encoding='utf-8') as f:
            yaml.safe_dump(data, f)
        self.load_config()
        self.table.select_entry(entry)

    def on_delete(self):
        entry = self.table.current_entry()
        if not entry:
            return
        data = yaml.safe_load(self.config_path.read_text()) or {}
        snippets = [e for e in data.get('snippets', []) if e.get('trigger') != entry['trigger']]
        data['snippets'] = snippets
        with open(self.config_path, 'w', encoding='utf-8') as f:
            yaml.safe_dump(data, f)
        self.load_config()
        self.form.display_message(
            'Uh oh, nothing selected. Create a new snippet or select one.'
        )

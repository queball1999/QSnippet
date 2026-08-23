"""
Tests the guard against setting up a vault that already exists.

Running the setup wizard a second time would generate a fresh key and
recovery code, leaving everything encrypted with the current key
unreadable, so the dialog has to refuse rather than proceed.
"""

import pytest


@pytest.fixture
def qt_app(mock_qt_app):
    from PySide6.QtWidgets import QApplication

    if not isinstance(mock_qt_app, QApplication):
        pytest.skip("GUI tests need a QApplication; run pytest with --gui")

    return mock_qt_app


CONFIGURED = {
    "vault": {
        "salt": "0123456789abcdef",
        "verifier": "fedcba9876543210",
        "configured": True,
    }
}

UNCONFIGURED = {"vault": {}}

# What a disabled or reset vault leaves behind: the keys exist but are blank
BLANKED = {
    "vault": {
        "salt": "",
        "verifier": "",
        "unlock_on_launch": False,
        "auto_lock_minutes": 15,
    }
}

RECOVERABLE = {
    "vault": {
        "salt": "",
        "verifier": "",
        "rec_salt": "aaaa",
        "rec_verifier": "bbbb",
        "rec_key_blob": "cccc",
    }
}


class FakeDb:
    """Stands in for SnippetDB for the orphaned-data checks."""

    def __init__(self, snippets=0, placeholders=0, fail=False):
        self.counts = (snippets, placeholders)
        self.fail = fail
        self.backed_up = False
        self.deleted = False

    def count_encrypted_rows(self):
        if self.fail:
            raise RuntimeError("database unavailable")
        return self.counts

    def backup_before_migration(self):
        self.backed_up = True
        return None, None, None

    def delete_encrypted_rows(self):
        self.deleted = True
        return self.counts


def make_dialog(config, mode="setup", db=None):
    from ui.widgets.vault_setup_dialog import VaultSetupDialog

    return VaultSetupDialog(config, db=db, mode=mode)


@pytest.mark.gui
def test_setup_on_an_existing_vault_refuses(qt_app):
    dialog = make_dialog(CONFIGURED)

    assert dialog.mode == "already_setup", "the setup wizard ran on an existing vault"
    assert not hasattr(dialog, "stack"), "the wizard pages were built anyway"
    assert "Already Set Up" in dialog.windowTitle()

    dialog.deleteLater()


@pytest.mark.gui
def test_the_refusal_explains_itself_and_offers_a_way_out(qt_app):
    from PySide6.QtWidgets import QLabel, QPushButton

    dialog = make_dialog(CONFIGURED)

    text = " ".join(
        label.text() for label in dialog.findChildren(QLabel) if label.text()
    ).lower()
    assert "already set up" in text
    assert "close this dialog" in text

    buttons = [b for b in dialog.findChildren(QPushButton) if b.text()]
    assert len(buttons) == 1, f"expected only a way out, got {[b.text() for b in buttons]}"
    assert buttons[0].text() == "Close"

    dialog.deleteLater()


@pytest.mark.gui
def test_the_refusal_closes_without_the_cancel_prompt(qt_app, monkeypatch):
    """
    The 'are you sure you want to exit setup?' prompt must not appear.

    There is no setup in progress to abandon.
    """
    dialog = make_dialog(CONFIGURED)

    asked = []
    monkeypatch.setattr(
        dialog, "confirm_cancel_setup", lambda: asked.append(True) or True
    )

    dialog.reject()
    qt_app.processEvents()

    assert asked == [], "the refusal page asked to confirm cancelling setup"

    dialog.deleteLater()


@pytest.mark.gui
def test_setup_still_runs_when_there_is_no_vault(qt_app):
    dialog = make_dialog(UNCONFIGURED)

    assert dialog.mode == "setup"
    assert hasattr(dialog, "stack"), "the setup wizard was not built"

    dialog.deleteLater()


@pytest.mark.gui
def test_change_mode_is_untouched_by_the_guard(qt_app):
    """Changing the password on an existing vault is exactly the right move."""
    dialog = make_dialog(CONFIGURED, mode="change")

    assert dialog.mode == "change"

    dialog.deleteLater()


# ----- ORPHANED DATA -----

@pytest.mark.gui
def test_orphaned_data_blocks_a_fresh_setup(qt_app):
    """
    Encrypted rows with no key material must not be set up over.

    A new vault would mint a new key and strand that data permanently.
    """
    db = FakeDb(snippets=2, placeholders=1)
    dialog = make_dialog(BLANKED, db=db)

    assert dialog.mode == "orphaned", "the setup wizard ran over orphaned data"
    assert not hasattr(dialog, "stack")
    assert dialog.orphan_snippets == 2
    assert dialog.orphan_placeholders == 1

    dialog.deleteLater()


@pytest.mark.gui
def test_orphaned_page_counts_what_it_found(qt_app):
    from PySide6.QtWidgets import QLabel

    dialog = make_dialog(BLANKED, db=FakeDb(snippets=2, placeholders=1))

    text = " ".join(l.text() for l in dialog.findChildren(QLabel) if l.text())
    assert "2 snippets" in text
    assert "1 placeholder" in text

    dialog.deleteLater()


@pytest.mark.gui
def test_orphaned_page_offers_recovery_only_when_it_can_work(qt_app):
    from PySide6.QtWidgets import QPushButton

    def labels(dialog):
        return {b.text() for b in dialog.findChildren(QPushButton) if b.text()}

    without = make_dialog(BLANKED, db=FakeDb(snippets=1))
    assert "Use Recovery Code" not in labels(without), \
        "recovery was offered with no recovery material"
    assert "Clear Old Vault Data" in labels(without)
    without.deleteLater()

    with_recovery = make_dialog(RECOVERABLE, db=FakeDb(snippets=1))
    assert "Use Recovery Code" in labels(with_recovery)
    with_recovery.deleteLater()


@pytest.mark.gui
def test_recovery_button_hands_off_and_closes(qt_app):
    dialog = make_dialog(RECOVERABLE, db=FakeDb(snippets=1))
    seen = []
    dialog.recoveryRequested.connect(lambda: seen.append(True))

    dialog.recover_btn.click()
    qt_app.processEvents()

    assert seen == [True]
    assert not dialog.isVisible()

    dialog.deleteLater()


@pytest.mark.gui
def test_clearing_backs_up_first_and_needs_confirmation(qt_app, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    db = FakeDb(snippets=2, placeholders=1)
    dialog = make_dialog(BLANKED, db=db)

    # Refusing the confirmation must delete nothing
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: QMessageBox.No)
    dialog.clear_orphaned_data()
    assert not db.deleted, "data was deleted without confirmation"
    assert not db.backed_up

    restarted = []
    dialog.restartSetupRequested.connect(lambda: restarted.append(True))

    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: QMessageBox.Yes)
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    dialog.clear_orphaned_data()

    assert db.backed_up, "the database was not backed up before deleting"
    assert db.deleted
    assert restarted == [True], "setup was not offered again after clearing"

    dialog.deleteLater()


@pytest.mark.gui
def test_a_broken_database_does_not_block_setup(qt_app):
    """A failed count must not stop someone setting up a vault."""
    dialog = make_dialog(UNCONFIGURED, db=FakeDb(fail=True))

    assert dialog.mode == "setup"
    assert hasattr(dialog, "stack")

    dialog.deleteLater()


@pytest.mark.gui
def test_a_clean_database_goes_straight_to_setup(qt_app):
    dialog = make_dialog(BLANKED, db=FakeDb(snippets=0, placeholders=0))

    assert dialog.mode == "setup"
    assert hasattr(dialog, "stack")

    dialog.deleteLater()

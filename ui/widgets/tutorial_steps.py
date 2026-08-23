"""
Content for the first-run guided tour.

Kept apart from tutorial_overlay.py so the copy and the target lookups can
change without touching the overlay mechanics.

The main tour stays short on purpose. Anything that deserves a closer look
lives in a TutorialBranch behind a "Learn more" button, so a reader in a
hurry can finish in a dozen steps while a reader who wants the detail can
ask for it feature by feature.
"""

import logging

from .tutorial_overlay import TutorialBranch, TutorialStep, TypingDemo

logger = logging.getLogger(__name__)


def toolbar_widget(window, attr: str):
    """
    Return the button widget backing a named toolbar QAction.

    Toolbar entries are QActions, which have no geometry of their own, so
    the spotlight needs the QToolButton the toolbar created for them.

    Args:
        window (QSnippet): The main window.
        attr (str): Attribute name of the action on the toolbar
            (e.g. "vault_action").

    Returns:
        QWidget | None: The button widget, or None when unavailable.
    """
    toolbar = getattr(window, "toolbar", None)
    action = getattr(toolbar, attr, None)
    if toolbar is None or action is None:
        return None

    return toolbar.widgetForAction(action)


def show_form(editor) -> None:
    """
    Put the snippet form on screen for a form step, and keep it there.

    Opening is skipped when the form is already showing so stepping back
    and forth through the form steps doesn't wipe the fields each time.
    The idle timer is stopped outright: it exists to close an abandoned
    form, and while the tour is running it would close the very thing the
    step is pointing at.

    Args:
        editor (SnippetEditor): The editor owning the form.

    Returns:
        None
    """
    if editor.stack.currentWidget() is not editor.form:
        editor.show_new_form()

    editor.stop_inactivity_timer()


def close_dialog(dialog) -> None:
    """
    Close a dialog a branch opened, tolerating one that's already gone.

    Args:
        dialog (QDialog | None): The dialog to close.

    Returns:
        None
    """
    if dialog is None:
        return

    try:
        dialog.close()
    except RuntimeError:
        logger.debug("Tutorial dialog was already destroyed")


class LazyDialog:
    """
    Opens a dialog the first time a branch step actually needs it.

    A branch must not open its dialog when it is built: a branch whose
    early steps point at the main window would then be explaining the
    main window from behind a dialog floating in front of it. Steps that
    live in the dialog open it in their `before`, and the branch cleanup
    closes it.
    """

    def __init__(self, opener):
        """
        Args:
            opener (Callable): Returns the opened dialog.
        """
        self.opener = opener
        self.dialog = None

    def open(self) -> None:
        """Open the dialog, once."""
        if self.dialog is None:
            self.dialog = self.opener()

    def get(self):
        """Return the dialog, or None if it hasn't been opened."""
        return self.dialog

    def widget(self, name: str):
        """
        Return a named widget inside the dialog.

        Args:
            name (str): Attribute name on the dialog.

        Returns:
            QWidget | None: The widget, or None if there's no dialog yet.
        """
        return getattr(self.dialog, name, None) if self.dialog is not None else None

    def close(self) -> None:
        """Close the dialog and forget it, so the branch can reopen later."""
        close_dialog(self.dialog)
        self.dialog = None


# ----- BRANCHES -----

def build_form_branch(window) -> TutorialBranch:
    """
    A field-by-field walk through the snippet form.

    Args:
        window (QSnippet): The main window.

    Returns:
        TutorialBranch: The detour, and the cleanup that returns Home.
    """
    editor = window.editor
    form = editor.form

    def open_form():
        show_form(editor)

    steps = [
        TutorialStep(
            title="Name",
            body=(
                "The name is for you: it's how the snippet appears in the library "
                "list and one of the things search looks at.<br><br>"
                "It has no effect on what gets pasted."
            ),
            target=lambda: form.new_input,
            before=open_form,
        ),
        TutorialStep(
            title="Trigger",
            body=(
                "The trigger is what you type to insert the snippet.<br><br>"
                "It has to start with a special character such as <b>/</b>, <b>!</b> "
                "or <b>;</b> so it never fires during ordinary typing, it can't "
                "contain spaces, and it has to be unique.<br><br>"
                "Short and memorable works best: <b>/addr</b>, <b>/sig</b>, <b>!ty</b>."
            ),
            target=lambda: form.trigger_input,
            before=open_form,
        ),
        TutorialStep(
            title="Folder",
            body=(
                "The folder decides where the snippet sits in the library on the "
                "left.<br><br>"
                "Pick an existing one, or type a name that doesn't exist yet and the "
                "folder is created with the snippet."
            ),
            target=lambda: form.folder_input,
            before=open_form,
        ),
        TutorialStep(
            title="Tags",
            body=(
                "Tags are free-form labels, and a snippet can carry as many as you "
                "like.<br><br>"
                "Unlike folders they aren't exclusive, so they're the way to group "
                "snippets that live in different places."
            ),
            target=lambda: form.tags_input,
            before=open_form,
        ),
        TutorialStep(
            title="The snippet body",
            body=(
                "This is the text that replaces your trigger. It can be a single line "
                "or many paragraphs.<br><br>"
                "The button above the box opens the same text in a larger pop-out "
                "editor when you're writing something long."
            ),
            target=lambda: form.snippet_input,
            before=open_form,
        ),
        TutorialStep(
            title="Turning a snippet off",
            body=(
                "This switch enables or disables the snippet.<br><br>"
                "A disabled snippet keeps everything it has but stops responding to "
                "its trigger, which is how you park a shortcut without deleting it."
            ),
            target=lambda: form.enabled_switch,
            before=open_form,
        ),
        TutorialStep(
            title="How the snippet is pasted",
            body=(
                "The left switch presses <b>Enter</b> for you after the snippet is "
                "inserted, which is handy for chat apps.<br><br>"
                "The right one chooses between <b>pasting from the clipboard</b>, "
                "which is fast, and <b>simulating typing</b>, which is slower but "
                "works in apps that refuse a paste."
            ),
            target=lambda: [form.return_switch, form.style_switch],
            before=open_form,
        ),
        TutorialStep(
            title="Saving your work",
            body=(
                "<b>Save</b> writes the snippet and makes the trigger live "
                "immediately; there is no restart and no reload step.<br><br>"
                "<b>New</b> starts another blank snippet, <b>Delete</b> removes the "
                "one you're editing, and <b>Cancel</b> returns to the home screen."
            ),
            target=lambda: [form.new_btn, form.save_btn, form.delete_btn, form.cancel_btn],
            before=open_form,
        ),
    ]

    return TutorialBranch("Snippet form", steps, cleanup=editor.show_home_widget)


def build_placeholder_branch(window) -> TutorialBranch:
    """
    A closer look at placeholders, ending in the placeholder manager.

    Args:
        window (QSnippet): The main window.

    Returns:
        TutorialBranch: The detour, and the cleanup that closes the manager.
    """
    editor = window.editor
    form = editor.form

    def open_form():
        show_form(editor)

    # Opened only when the branch reaches the steps that live in it, so the
    # two steps before it aren't explained from behind a floating dialog
    manager = LazyDialog(lambda: window.show_placeholder_manager(blocking=False))

    steps = [
        TutorialStep(
            title="Placeholders: {{ }}",
            body=(
                "Type <b>{{</b> in the snippet body and a list of placeholders "
                "appears.<br><br>"
                "These fill themselves in at the moment the snippet is pasted: "
                "<b>{{date}}</b>, <b>{{time}}</b>, <b>{{datetime}}</b>, "
                "<b>{{weekday}}</b>, <b>{{greeting}}</b> and more. So a signature "
                "written once always pastes with today's date.<br><br>"
                "The <b>Tools</b> menu lists them all."
            ),
            target=lambda: form.snippet_input,
            before=open_form,
        ),
        TutorialStep(
            title="Fill-in fields: [[ ]]",
            body=(
                "Type <b>[[</b> instead and you create a fill-in field, for example "
                "<b>[[customer]]</b>.<br><br>"
                "QSnippet stops and asks you for those values every time the snippet "
                "fires, then drops your answers into place. Reuse the same name twice "
                "and it is filled once and pasted in both spots.<br><br>"
                "Settings lets you choose whether the fields are asked all at once or "
                "one screen at a time."
            ),
            target=lambda: form.snippet_input,
            before=open_form,
        ),
        TutorialStep(
            title="Your own placeholders",
            body=(
                "This is the placeholder manager, open now so you can see it. It's "
                "always available from <b>Tools &gt; Custom &gt; Manage Placeholders</b> "
                "or by pressing <b>F6</b>.<br><br>"
                "Anything you define here becomes a <b>{{token}}</b> you can drop into "
                "any snippet: your address, an account number, a standard sign-off."
            ),
            target=lambda: manager.widget("table"),
            host=manager.get,
            before=manager.open,
        ),
        TutorialStep(
            title="Adding one",
            body=(
                "<b>Add Placeholder</b> creates a new token; you give it a name and "
                "the value it should paste.<br><br>"
                "A placeholder can also be marked for the vault, which encrypts its "
                "value the same way vault snippets are encrypted."
            ),
            target=lambda: manager.widget("add_btn"),
            host=manager.get,
            before=manager.open,
        ),
    ]

    return TutorialBranch("Placeholders", steps, cleanup=manager.close)


def build_vault_branch(window) -> TutorialBranch:
    """
    A closer look at the vault.

    Args:
        window (QSnippet): The main window.

    Returns:
        TutorialBranch: The detour.
    """
    return TutorialBranch(
        "Vault",
        [
            TutorialStep(
                title="Vault folders",
                body=(
                    "The vault isn't a separate place; it's a property of a folder.<br><br>"
                    "Mark a folder as a vault folder and everything inside it is "
                    "encrypted on disk. Folders that are locked show a padlock in the "
                    "library, and their snippet text is masked until you unlock."
                ),
                target=lambda: window.editor.table,
            ),
            TutorialStep(
                title="Locking and unlocking",
                body=(
                    "This button unlocks the vault, and locks it again when you're "
                    "done. Triggering a locked snippet prompts you to unlock first, "
                    "then pastes it as normal.<br><br>"
                    "The vault re-locks itself after a period of inactivity that you "
                    "choose, so leaving your desk doesn't leave it open."
                ),
                target=lambda: toolbar_widget(window, "vault_action"),
            ),
            TutorialStep(
                title="Your recovery code",
                body=(
                    "Setting up the vault gives you a one-time <b>recovery code</b>. "
                    "Write it down and keep it somewhere safe.<br><br>"
                    "The encryption is real: without either the password or that code, "
                    "the contents cannot be recovered by anyone, including us."
                ),
                target=lambda: toolbar_widget(window, "vault_action"),
            ),
        ],
    )


def build_settings_branch(window) -> TutorialBranch:
    """
    A closer look at Settings, with the real dialog open to point at.

    Args:
        window (QSnippet): The main window.

    Returns:
        TutorialBranch: The detour, and the cleanup that closes the dialog.
    """
    settings = LazyDialog(lambda: window.show_settings_window(blocking=False))

    steps = [
        TutorialStep(
            title="Categories",
            body=(
                "Settings is open now so you can see your way around it.<br><br>"
                "The sidebar splits everything into categories: appearance, general "
                "behaviour, notices, the vault, your database location and backups. "
                "Clicking one shows its settings on the right."
            ),
            target=lambda: settings.widget("list"),
            host=settings.get,
            before=settings.open,
        ),
        TutorialStep(
            title="Find a setting",
            body=(
                "If you know roughly what you're after but not where it lives, type "
                "it here.<br><br>"
                "Search looks through every setting's name and description and takes "
                "you straight to the match, so you never have to hunt through the "
                "categories."
            ),
            target=lambda: settings.widget("search"),
            host=settings.get,
            before=settings.open,
        ),
        TutorialStep(
            title="Changes apply immediately",
            body=(
                "There is no Save button: changing a setting takes effect as you make "
                "it, so you can see a theme or a font size before you commit to it.<br><br>"
                "<b>Restore Defaults</b> puts everything back if you go too far."
            ),
            target=lambda: settings.widget("restore_defaults_btn"),
            host=settings.get,
            before=settings.open,
        ),
    ]

    return TutorialBranch("Settings", steps, cleanup=settings.close)


# ----- MAIN TOUR -----

def vault_is_configured(window) -> bool:
    """
    Report whether the tour should stay out of the way of the vault.

    True when the vault already has a password, and also when encrypted
    data is sitting in the database without its key material: that case
    needs recovery or a deliberate clear-out, not a cheery setup button.

    Args:
        window (QSnippet): The main window.

    Returns:
        bool: True when setup must not be offered. Treated as True on
            error, so a problem here can never offer setup to someone who
            already has a vault.
    """
    try:
        status = window.vault_manager().describe(
            window.vault_config(), window.vault_db()
        )
        return status.blocks_setup
    except Exception:
        logger.warning("Could not determine vault state for the tour", exc_info=True)
        return True


def build_tutorial_steps(window) -> list[TutorialStep]:
    """
    Build the main tour of the window.

    Steps are wired to the live widgets by callable so nothing is captured
    before it exists, and the deeper material sits in branches the reader
    opts into rather than in steps everyone has to walk through.

    Args:
        window (QSnippet): The main application window.

    Returns:
        list[TutorialStep]: The steps to present, in order.
    """
    editor = window.editor
    home = editor.home_widget

    def open_form():
        show_form(editor)

    # Someone who already has a vault must not be offered setup again: a
    # second run would replace the key and orphan what the first one encrypted
    vault_ready = vault_is_configured(window)

    closing_body = (
        "That's the tour. Create your first snippet with <b>New Snippet</b>, then "
        "try its trigger in any app you like.<br><br>"
    )
    if vault_ready:
        closing_body += (
            "Your vault is already set up, so it's ready whenever you need it; "
            "use the padlock in the toolbar to unlock it.<br><br>"
        )
    else:
        closing_body += (
            "If you already know you want somewhere safe for licence keys and "
            "credentials, you can set the vault up now. Otherwise get started, and "
            "it'll be waiting under the padlock whenever you want it.<br><br>"
        )
    closing_body += (
        "This tour is always available from <b>Help &gt; Tutorial</b> or <b>F1</b>."
    )

    return [
        TutorialStep(
            title="Welcome to QSnippet",
            body="Thanks for installing QSnippet.",
            demo=TypingDemo(
                trigger="/getting-started",
                expansion=(
                    "When using QSnippet, you type a short <b>trigger</b>, and it is "
                    "replaced by whatever text you gave it. It works in any app on "
                    "your computer.<br><br>"
                    "This quick tour walks through the layout and the main features. "
                    "It takes about a minute, and you can leave at any time with "
                    "<b>Skip tour</b> or the <b>Esc</b> key."
                ),
            ),
            before=editor.show_home_widget,
        ),
        TutorialStep(
            title="Your snippet library",
            body=(
                "Every snippet you own lives here, grouped into folders.<br><br>"
                "Click a snippet to open it for editing, or right-click anywhere in "
                "the list to add a folder, add a snippet, rename or delete. Snippets "
                "can be dragged between folders."
            ),
            target=lambda: editor.table,
        ),
        TutorialStep(
            title="Find things fast",
            body=(
                "Search matches snippet names, triggers, tags and snippet text. Press "
                "<b>Ctrl+F</b> from anywhere in the window to jump straight here.<br><br>"
                "The dropdown beside it filters the list down to enabled or disabled "
                "snippets, and the button at the end expands or collapses every folder."
            ),
            target=lambda: editor.search_bar,
        ),
        TutorialStep(
            title="The toolbar and menus",
            body=(
                "The toolbar covers the things you do most: <b>Home</b>, <b>New "
                "Snippet</b>, <b>Save</b>, <b>Delete</b>, and the <b>Vault</b> and "
                "<b>Settings</b> on the right.<br><br>"
                "The menus above hold import and export, the placeholder manager, and "
                "a Help menu with logs, backups and release notes. You can reopen this "
                "tour from <b>Help &gt; Tutorial</b> or by pressing <b>F1</b>."
            ),
            target=lambda: [window.menuBar(), window.toolbar],
        ),
        TutorialStep(
            title="A place to practise",
            body=(
                "This scratch box is a safe place to try your triggers out; nothing "
                "typed here is saved.<br><br>"
                "QSnippet ships with a sample snippet, so type <b>/welcome</b> in the "
                "box once the tour has finished and watch it expand."
            ),
            target=lambda: home.test_entry,
            before=editor.show_home_widget,
        ),
        TutorialStep(
            title="Creating a snippet",
            body=(
                "This is the snippet form, which opens whenever you create a snippet "
                "or click an existing one.<br><br>"
                "At its simplest you fill in three things: a <b>name</b>, the "
                "<b>trigger</b> you'll type, and the <b>text</b> it expands to. Then "
                "press Save and it works everywhere."
            ),
            target=lambda: editor.form,
            before=open_form,
            after=editor.show_home_widget,
            branch=lambda: build_form_branch(window),
        ),
        TutorialStep(
            title="Snippets that fill themselves in",
            body=(
                "Snippets don't have to be fixed text.<br><br>"
                "<b>{{date}}</b> and its siblings fill themselves in when the snippet "
                "pastes, and <b>[[name]]</b> fields stop and ask you for a value "
                "first. Write a signature once and it always pastes with today's date."
            ),
            target=lambda: editor.form.snippet_input,
            before=open_form,
            after=editor.show_home_widget,
            branch=lambda: build_placeholder_branch(window),
        ),
        TutorialStep(
            title="The Vault",
            body=(
                "Some snippets hold things you would rather not keep in plain text: "
                "licence keys, account numbers, credentials.<br><br>"
                "Mark a folder as a <b>Vault</b> folder and everything in it is "
                "encrypted on disk behind a password you choose."
            ),
            target=lambda: toolbar_widget(window, "vault_action"),
            branch=lambda: build_vault_branch(window),
        ),
        TutorialStep(
            title="Settings",
            body=(
                "Settings covers themes and accent colour, UI scale and fonts, whether "
                "QSnippet starts with your system, trigger and clipboard timeouts, "
                "vault behaviour, database location and automatic backups.<br><br>"
                "Changes apply as soon as you make them."
            ),
            target=lambda: toolbar_widget(window, "settings_action"),
            branch=lambda: build_settings_branch(window),
        ),
        TutorialStep(
            title="QSnippet keeps running",
            body=(
                "Closing this window doesn't stop QSnippet; it keeps running in your "
                "system tray so your triggers work everywhere.<br><br>"
                "Use the tray icon to reopen this window, lock the vault, or exit "
                "properly."
            ),
        ),
        TutorialStep(
            title="You're all set",
            body=closing_body,
            before=editor.show_home_widget,
            action=None if vault_ready else window.show_vault_settings,
            action_label="" if vault_ready else "Set up Vault",
        ),
    ]

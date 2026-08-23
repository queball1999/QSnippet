"""
Tests for the first-run guided tour.

The step-model tests run headless with no QApplication. The overlay and
controller tests need real widgets, so they are marked `gui` and run only
with pytest --gui.
"""

import pytest

from ui.widgets.tutorial_overlay import TutorialBranch, TutorialStep
from ui.widgets.tutorial_steps import build_tutorial_steps, toolbar_widget


class FakeToolbar:
    """Stand-in for ToolbarMenu that records widgetForAction lookups."""

    def __init__(self):
        self.vault_action = object()
        self.settings_action = object()
        self.looked_up = []

    def widgetForAction(self, action):
        self.looked_up.append(action)
        return f"widget-for-{id(action)}"


class FakeForm:
    def __init__(self):
        for name in (
            "new_input", "trigger_input", "folder_input", "tags_input",
            "snippet_input", "enabled_switch", "return_switch", "style_switch",
            "new_btn", "save_btn", "delete_btn", "cancel_btn",
        ):
            setattr(self, name, name)


class FakeStack:
    """Mimics the editor's QStackedWidget just enough for show_form()."""

    def __init__(self):
        self.current = None

    def currentWidget(self):
        return self.current


class FakeEditor:
    def __init__(self):
        self.form = FakeForm()
        self.home_widget = type("Home", (), {"test_entry": "test_entry"})()
        self.table = "table"
        self.search_bar = "search_bar"
        self.stack = FakeStack()
        self.calls = []

    def show_home_widget(self, *_):
        self.calls.append("home")
        self.stack.current = self.home_widget

    def show_new_form(self, *_):
        self.calls.append("new_form")
        self.stack.current = self.form

    def stop_inactivity_timer(self):
        self.calls.append("stop_idle")


class FakeDialog:
    """A stand-in for the dialogs the branches open and close."""

    def __init__(self, name, widgets):
        self.name = name
        self.closed = False
        for widget in widgets:
            setattr(self, widget, f"{name}.{widget}")

    def close(self):
        self.closed = True


class FakeVaultManager:
    """Delegates to the real classifier so the fake can't drift from it."""

    def __init__(self, configured):
        self.configured = configured

    def is_setup(self, config):
        return self.configured

    def describe(self, config, db=None):
        from utils.vault_manager import VaultManager

        if self.configured:
            config = {"vault": {"salt": "aaaa", "verifier": "bbbb"}}
        return VaultManager.describe(VaultManager(), config or {"vault": {}}, db)


class FakeDb:
    def __init__(self, encrypted=(0, 0)):
        self.encrypted = encrypted

    def count_encrypted_rows(self):
        return self.encrypted


class FakeWindow:
    def __init__(self, vault_configured=False, encrypted=(0, 0)):
        self.editor = FakeEditor()
        self.toolbar = FakeToolbar()
        self.opened = []
        self.settings_dialog = None
        self.placeholder_dialog = None
        self.vault_setup_calls = 0
        self.vault = FakeVaultManager(vault_configured)
        self.db = FakeDb(encrypted)

    def menuBar(self):
        return "menubar"

    def vault_manager(self):
        return self.vault

    def vault_config(self):
        return {}

    def vault_db(self):
        return self.db

    def show_settings_window(self, page=None, blocking=True):
        self.opened.append(("settings", blocking))
        self.settings_dialog = FakeDialog(
            "settings", ("list", "search", "restore_defaults_btn")
        )
        return self.settings_dialog

    def show_placeholder_manager(self, blocking=True):
        self.opened.append(("placeholders", blocking))
        self.placeholder_dialog = FakeDialog("placeholders", ("table", "add_btn"))
        return self.placeholder_dialog

    def show_vault_settings(self):
        self.vault_setup_calls += 1


@pytest.fixture
def window():
    return FakeWindow()


def walk_steps(window):
    """
    Yield every step in the tour, main and branch alike.

    Branch steps get their `before` run first, which is what opens any
    dialog they point into, so their targets resolve the way they would
    on screen.
    """
    for step in build_tutorial_steps(window):
        yield step, None

        if step.branch is None:
            continue

        branch = step.branch()
        assert isinstance(branch, TutorialBranch), f"'{step.title}' built no branch"
        for sub in branch.steps:
            if sub.before is not None:
                sub.before()
            yield sub, branch

        if branch.cleanup is not None:
            branch.cleanup()


def targets_of(step):
    """Return a step's targets as a flat list."""
    if step.target is None:
        return []

    target = step.target()
    return list(target) if isinstance(target, (list, tuple)) else [target]


# ----- STEP MODEL -----

def test_steps_are_built_without_touching_widgets(window):
    """Building the tour must not resolve targets or run setup actions."""
    steps = build_tutorial_steps(window)

    assert steps, "the tour must have steps"
    assert all(isinstance(step, TutorialStep) for step in steps)
    assert window.editor.calls == []
    assert window.toolbar.looked_up == []


def test_every_step_has_title_and_body(window):
    for step, _ in walk_steps(window):
        assert step.title.strip()
        assert step.body.strip()


def test_the_main_tour_stays_short(window):
    """
    The detail belongs in branches, not in steps everyone must walk.

    A main tour that creeps back up defeats the point of having them.
    """
    steps = build_tutorial_steps(window)

    assert len(steps) <= 12, f"the main tour has grown to {len(steps)} steps"
    assert sum(1 for s in steps if s.branch is not None) >= 3, \
        "the deeper material should sit behind Learn more buttons"


def test_tour_opens_and_closes_on_the_home_screen(window):
    steps = build_tutorial_steps(window)

    steps[0].before()
    steps[-1].before()

    assert window.editor.calls == ["home", "home"]


def test_every_target_resolves(window):
    """No step may point at an attribute the window doesn't have."""
    for step, _ in walk_steps(window):
        if step.target is None:
            continue

        targets = targets_of(step)
        assert targets, f"empty target group on step '{step.title}'"
        assert all(part is not None for part in targets), \
            f"unresolved target on step '{step.title}'"


def test_every_host_resolves(window):
    """A step that points inside a dialog must be able to find it."""
    for step, _ in walk_steps(window):
        if step.host is None:
            continue
        assert step.host() is not None, f"unresolved host on step '{step.title}'"


def test_form_steps_open_the_form_themselves(window):
    """
    Every form step must open the form, not lean on the step before it.

    Stepping back into the middle of the form section would otherwise
    spotlight a form that is no longer on screen.
    """
    form_fields = set(vars(window.editor.form).values())
    checked = 0

    for step, _ in walk_steps(window):
        if not form_fields.intersection(targets_of(step)):
            continue

        checked += 1
        window.editor.stack.current = window.editor.home_widget
        assert step.before is not None, f"form step '{step.title}' has no setup"

        step.before()
        assert window.editor.stack.current is window.editor.form, \
            f"form step '{step.title}' did not open the form"

    assert checked, "no form steps were found to check"


def test_reopening_the_form_keeps_what_is_already_there(window):
    """An already-open form must not be cleared when stepping through it."""
    from ui.widgets.tutorial_steps import show_form

    editor = window.editor
    editor.stack.current = editor.form
    editor.calls.clear()

    show_form(editor)

    assert "new_form" not in editor.calls


def test_form_steps_stop_the_idle_timer(window):
    """The idle timer would close the form the step is pointing at."""
    from ui.widgets.tutorial_steps import show_form

    editor = window.editor
    editor.calls.clear()

    show_form(editor)

    assert "stop_idle" in editor.calls


def test_placeholder_syntax_is_documented(window):
    """Both placeholder forms must be explained, since they behave differently."""
    bodies = " ".join(step.body for step in build_tutorial_steps(window))

    assert "{{date}}" in bodies
    assert "[[" in bodies


def test_the_tour_warns_about_the_recovery_code(window):
    """Losing the vault password without the code is unrecoverable."""
    bodies = " ".join(step.body for step, _ in walk_steps(window))

    assert "recovery code" in bodies


def test_welcome_step_demonstrates_a_trigger(window):
    """Step one shows what the app does rather than only describing it."""
    first = build_tutorial_steps(window)[0]

    assert first.demo is not None, "the welcome step lost its typing demo"
    assert first.demo.trigger.startswith("/")
    assert first.demo.expansion.strip()


def test_branches_open_their_dialogs_without_blocking(window):
    """
    A branch that opens a dialog must open it non-modally.

    exec() would block the tour mid-step, leaving the overlay frozen
    behind a dialog it can never drive.
    """
    for _ in walk_steps(window):
        pass

    assert window.opened, "no branch opened a dialog"
    for name, blocking in window.opened:
        assert blocking is False, \
            f"the {name} branch opened its dialog with a blocking exec()"


def test_building_a_branch_opens_nothing(window):
    """
    A branch must not open its dialog just for being built.

    The placeholders branch starts with two steps about the main window.
    Opening its dialog up front left those steps being explained from
    behind a dialog floating in front of them.
    """
    for step in build_tutorial_steps(window):
        if step.branch is None:
            continue

        step.branch()
        assert window.opened == [], \
            f"'{step.title}' opened {window.opened} just by building its branch"


def test_a_dialog_opens_only_at_the_step_that_lives_in_it(window):
    """Each dialog step opens its own dialog, and not before."""
    for step in build_tutorial_steps(window):
        if step.branch is None:
            continue

        branch = step.branch()
        for sub in branch.steps:
            needs_dialog = sub.host is not None

            if sub.before is not None:
                sub.before()

            if needs_dialog:
                assert sub.host() is not None, \
                    f"'{sub.title}' needs a dialog but none was opened"
            else:
                assert window.opened == [], \
                    f"a dialog was open during '{sub.title}', which is about the main window"

        if branch.cleanup is not None:
            branch.cleanup()
        window.opened.clear()


def test_branches_close_what_they_opened(window):
    """Cleanup has to run whether the branch was finished or cut short."""
    opened = []

    for step in build_tutorial_steps(window):
        if step.branch is None:
            continue

        branch = step.branch()
        for sub in branch.steps:
            if sub.before is not None:
                sub.before()

        dialog = window.settings_dialog or window.placeholder_dialog
        if dialog is not None and dialog not in opened:
            opened.append(dialog)

        if branch.cleanup is not None:
            branch.cleanup()

    assert opened, "no dialogs were opened by the branches"
    for dialog in opened:
        assert dialog.closed, f"the {dialog.name} dialog was left open"


def test_dialog_branches_host_their_steps_on_the_dialog(window):
    """
    Steps pointing into a dialog must say so.

    Without a host the spotlight would be measured against the main
    window and land on empty space.
    """
    for step in build_tutorial_steps(window):
        if step.branch is None:
            continue

        branch = step.branch()
        for sub in branch.steps:
            targets = targets_of(sub)
            points_into_dialog = any(
                isinstance(t, str) and t.startswith(("settings.", "placeholders."))
                for t in targets
            )
            if points_into_dialog:
                assert sub.host is not None, \
                    f"'{sub.title}' points into a dialog but has no host"

        if branch.cleanup is not None:
            branch.cleanup()


def test_closing_step_offers_vault_setup(window):
    """With no vault yet, the tour ends by asking whether to set one up."""
    last = build_tutorial_steps(window)[-1]

    assert last.action is not None, "the closing step offers no vault setup"
    assert "vault" in last.action_label.lower()

    last.action()
    assert window.vault_setup_calls == 1


def test_closing_step_hides_setup_when_the_vault_exists():
    """
    Offering setup to someone who has a vault invites a costly mistake.

    A second run would create a new key and recovery code, orphaning
    everything the first one encrypted.
    """
    window = FakeWindow(vault_configured=True)
    last = build_tutorial_steps(window)[-1]

    assert last.action is None, "setup was offered on top of an existing vault"
    assert last.action_label == ""
    assert "already set up" in last.body


def test_closing_step_says_nothing_is_pending_when_the_vault_exists():
    window = FakeWindow(vault_configured=True)
    last = build_tutorial_steps(window)[-1]

    assert "set the vault up now" not in last.body


def test_closing_step_hides_setup_when_orphaned_vault_data_exists():
    """
    Encrypted rows without key material need recovery, not a fresh setup.

    Setting up again would mint a new key and strand that data for good.
    """
    window = FakeWindow(vault_configured=False, encrypted=(2, 1))
    last = build_tutorial_steps(window)[-1]

    assert last.action is None, "setup was offered over undecryptable data"


def test_vault_state_failure_hides_setup():
    """If the vault state can't be read, don't offer setup on a guess."""
    from ui.widgets.tutorial_steps import vault_is_configured

    class Broken:
        def vault_manager(self):
            raise RuntimeError("no vault manager")

        def vault_config(self):
            return {}

    assert vault_is_configured(Broken()) is True


def test_close_dialog_tolerates_a_destroyed_dialog():
    from ui.widgets.tutorial_steps import close_dialog

    class Gone:
        def close(self):
            raise RuntimeError("wrapped C/C++ object has been deleted")

    close_dialog(None)
    close_dialog(Gone())


def test_toolbar_widget_survives_a_missing_toolbar():
    assert toolbar_widget(object(), "vault_action") is None


def test_toolbar_widget_survives_a_missing_action(window):
    assert toolbar_widget(window, "not_a_real_action") is None


# ----- OVERLAY AND CONTROLLER -----

@pytest.fixture
def qt_app(mock_qt_app):
    """Reuse the session Qt application, which is a QApplication under --gui."""
    from PySide6.QtWidgets import QApplication

    if not isinstance(mock_qt_app, QApplication):
        pytest.skip("GUI tests need a QApplication; run pytest with --gui")

    yield mock_qt_app
    mock_qt_app.processEvents()


@pytest.fixture
def host(qt_app):
    """A window with a small button in it, the way a real target sits."""
    from PySide6.QtWidgets import QMainWindow, QPushButton, QWidget, QVBoxLayout

    win = QMainWindow()
    central = QWidget()
    layout = QVBoxLayout(central)
    button = QPushButton("save")
    button.setFixedSize(120, 30)
    layout.addStretch()
    layout.addWidget(button)
    layout.addStretch()
    win.setCentralWidget(central)
    win.resize(900, 600)
    win.show()
    qt_app.processEvents()

    yield win, button

    win.close()


@pytest.mark.gui
def test_controller_walks_forward_and_reports_completion(qt_app, host):
    from ui.widgets.tutorial_overlay import TutorialController

    win, button = host
    seen = []
    steps = [
        TutorialStep("One", "First", before=lambda: seen.append("before")),
        TutorialStep("Two", "Second", target=lambda: button, after=lambda: seen.append("after")),
    ]

    controller = TutorialController(win, steps)
    outcome = []
    controller.finished.connect(outcome.append)

    controller.start()
    qt_app.processEvents()
    assert controller.active
    assert seen == ["before"]

    controller.go_next()
    qt_app.processEvents()
    assert controller.index == 1

    controller.go_next()
    qt_app.processEvents()

    assert outcome == [True]
    assert not controller.active
    assert controller.overlay is None
    assert seen == ["before", "after"]


@pytest.mark.gui
def test_skipping_reports_an_incomplete_tour(qt_app, host):
    from ui.widgets.tutorial_overlay import TutorialController

    win, button = host
    controller = TutorialController(win, [TutorialStep("One", "First")])
    outcome = []
    controller.finished.connect(outcome.append)

    controller.start()
    qt_app.processEvents()
    controller.skip()
    qt_app.processEvents()

    assert outcome == [False]
    assert controller.overlay is None


@pytest.mark.gui
def test_back_clamps_at_the_first_step(qt_app, host):
    from ui.widgets.tutorial_overlay import TutorialController

    win, button = host
    steps = [TutorialStep(f"Step {i}", "body") for i in range(3)]
    controller = TutorialController(win, steps)

    controller.start()
    qt_app.processEvents()
    controller.go_next()
    qt_app.processEvents()
    controller.go_back()
    qt_app.processEvents()
    controller.go_back()
    qt_app.processEvents()

    assert controller.index == 0
    controller.skip()


@pytest.mark.gui
def test_spotlight_tracks_the_target_widget(qt_app, host):
    from ui.widgets.tutorial_overlay import TutorialController, SPOTLIGHT_PADDING

    win, button = host
    controller = TutorialController(win, [TutorialStep("One", "body", target=lambda: button)])
    controller.start()
    qt_app.processEvents()

    spot = controller.overlay.spotlight
    assert not spot.isEmpty()
    assert spot.width() >= button.width()
    assert spot.height() >= button.height() + SPOTLIGHT_PADDING

    controller.skip()


@pytest.mark.gui
def test_bubble_never_covers_the_spotlight(qt_app, host):
    from ui.widgets.tutorial_overlay import TutorialController

    win, button = host
    controller = TutorialController(win, [TutorialStep("One", "body", target=lambda: button)])
    controller.start()
    qt_app.processEvents()

    overlay = controller.overlay
    assert not overlay.bubble.geometry().intersects(overlay.spotlight)
    assert win.rect().contains(overlay.bubble.geometry())

    controller.skip()


@pytest.fixture
def branching(host):
    """A three-step tour whose middle step offers a two-step branch."""
    from ui.widgets.tutorial_overlay import TutorialController

    win, button = host
    log = []

    branch = TutorialBranch(
        "Detour",
        [
            TutorialStep("Detour one", "body"),
            TutorialStep("Detour two", "body"),
        ],
        cleanup=lambda: log.append("cleanup"),
    )

    steps = [
        TutorialStep("Main one", "body"),
        TutorialStep("Main two", "body",
                     branch=lambda: branch,
                     after=lambda: log.append("origin-after")),
        TutorialStep("Main three", "body"),
    ]

    controller = TutorialController(win, steps)
    return controller, log


@pytest.mark.gui
def test_learn_more_enters_and_returns_to_the_next_step(qt_app, branching):
    controller, log = branching

    controller.start()
    qt_app.processEvents()
    controller.go_next()
    qt_app.processEvents()
    assert controller.current_step().title == "Main two"
    assert controller.branch is None

    controller.run_extra()
    qt_app.processEvents()
    assert controller.branch is not None
    assert controller.current_step().title == "Detour one"

    controller.go_next()
    qt_app.processEvents()
    assert controller.current_step().title == "Detour two"

    # Last branch step returns to the tour, one past the step that offered it
    controller.go_next()
    qt_app.processEvents()
    assert controller.branch is None
    assert controller.current_step().title == "Main three"
    assert log == ["cleanup", "origin-after"]

    controller.skip()


@pytest.mark.gui
def test_skip_inside_a_branch_only_leaves_the_branch(qt_app, branching):
    """Skip means "back to the tour" in a branch, not "end the tour"."""
    controller, log = branching
    outcome = []

    controller.finished.connect(outcome.append)
    controller.start()
    qt_app.processEvents()
    controller.go_next()
    controller.run_extra()
    qt_app.processEvents()

    controller.skip()
    qt_app.processEvents()

    assert controller.active, "skipping a branch ended the whole tour"
    assert controller.branch is None
    assert outcome == []
    assert "cleanup" in log, "leaving early skipped the branch cleanup"
    assert controller.current_step().title == "Main three"

    controller.skip()


@pytest.mark.gui
def test_back_on_the_first_branch_step_returns_to_the_offer(qt_app, branching):
    """Back must not skip the step that offered the branch."""
    controller, log = branching

    controller.start()
    qt_app.processEvents()
    controller.go_next()
    controller.run_extra()
    qt_app.processEvents()

    controller.go_back()
    qt_app.processEvents()

    assert controller.branch is None
    assert controller.current_step().title == "Main two"
    assert "cleanup" in log

    controller.skip()


@pytest.mark.gui
def test_ending_the_tour_inside_a_branch_still_cleans_up(qt_app, branching):
    """A dialog a branch opened must not be left on screen."""
    controller, log = branching

    controller.start()
    qt_app.processEvents()
    controller.go_next()
    controller.run_extra()
    qt_app.processEvents()

    controller.stop(completed=False)
    qt_app.processEvents()

    assert "cleanup" in log
    assert controller.branch is None


@pytest.mark.gui
def test_close_button_ends_the_tour_from_any_step(qt_app, host):
    """The title-row close button is always offered and always ends the tour."""
    from ui.widgets.tutorial_overlay import TutorialController

    win, _ = host
    steps = [TutorialStep("One", "First."), TutorialStep("Two", "Second.")]
    controller = TutorialController(win, steps)
    outcome = []
    controller.finished.connect(outcome.append)
    controller.start()
    qt_app.processEvents()

    bubble = controller.overlay.bubble
    assert bubble.close_btn.isVisible()
    assert not bubble.close_btn.icon().isNull(), "the close button has no icon"

    bubble.close_btn.click()
    qt_app.processEvents()

    assert not controller.active
    assert outcome == [False], "closing the tour reported it as completed"


@pytest.mark.gui
def test_close_button_inside_a_branch_ends_the_whole_tour(qt_app, branching):
    """Unlike Skip, close does not just step back out of the branch."""
    controller, log = branching
    outcome = []

    controller.finished.connect(outcome.append)
    controller.start()
    qt_app.processEvents()
    controller.go_next()
    controller.run_extra()
    qt_app.processEvents()
    assert controller.branch is not None

    controller.overlay.bubble.close_btn.click()
    qt_app.processEvents()

    assert not controller.active
    assert outcome == [False]
    assert "cleanup" in log, "closing from a branch skipped its cleanup"


@pytest.mark.gui
def test_action_ends_the_tour_before_running(qt_app, host):
    """
    Whatever the action opens must not appear behind the overlay.

    The overlay has to be gone by the time the action runs.
    """
    from ui.widgets.tutorial_overlay import TutorialController

    win, _ = host
    seen = {}

    controller = None

    def action():
        seen["active"] = controller.active
        seen["overlay"] = controller.overlay

    steps = [TutorialStep("Last", "body", action=action, action_label="Do it")]
    controller = TutorialController(win, steps)
    outcome = []
    controller.finished.connect(outcome.append)

    controller.start()
    qt_app.processEvents()
    controller.run_extra()
    qt_app.processEvents()

    assert seen["active"] is False, "the action ran while the tour was still up"
    assert seen["overlay"] is None, "the action ran with the overlay still on screen"
    assert outcome == [True]


@pytest.mark.gui
def test_overlay_moves_onto_a_step_host(qt_app, host):
    """A step that names a host gets its spotlight drawn on that window."""
    from PySide6.QtWidgets import QDialog, QPushButton
    from ui.widgets.tutorial_overlay import TutorialController

    win, button = host
    dialog = QDialog(win)
    inner = QPushButton("inside", dialog)
    inner.move(20, 20)
    dialog.resize(400, 300)
    dialog.show()
    qt_app.processEvents()

    steps = [
        TutorialStep("On the window", "body", target=lambda: button),
        TutorialStep("In the dialog", "body",
                     target=lambda: inner, host=lambda: dialog),
        TutorialStep("Back on the window", "body", target=lambda: button),
    ]
    controller = TutorialController(win, steps)

    controller.start()
    qt_app.processEvents()
    assert controller.overlay.parentWidget() is win

    controller.go_next()
    qt_app.processEvents()
    assert controller.overlay.parentWidget() is dialog
    assert not controller.overlay.spotlight.isEmpty()

    controller.go_next()
    qt_app.processEvents()
    assert controller.overlay.parentWidget() is win

    controller.skip()
    dialog.close()


@pytest.mark.gui
def test_bubble_matches_the_plain_geometry_during_a_demo(qt_app, host):
    """
    A typing demo must not change how the bubble is sized or placed.

    Sizing the bubble from the font once made it wider than its own
    maximum, and reserving the expansion's height left a blank gap under
    the trigger for the whole animation.
    """
    from ui.widgets.tutorial_overlay import (
        TutorialController, TypingDemo, BUBBLE_WIDTH,
    )

    win, _ = host
    body = "Thanks for installing QSnippet."
    demo = TypingDemo("/getting-started", "It expands into this longer sentence.")

    steps = [
        TutorialStep("With a demo", body, demo=demo),
        TutorialStep("Plain", body),
    ]
    controller = TutorialController(win, steps)
    controller.start()
    qt_app.processEvents()

    bubble = controller.overlay.bubble
    assert bubble.width() == BUBBLE_WIDTH
    assert win.rect().contains(bubble.geometry())

    sizes = {bubble.size().toTuple()}
    while not bubble.demo_expanded:
        bubble.on_demo_tick()
        qt_app.processEvents()
        sizes.add(bubble.size().toTuple())

    assert len(sizes) == 1, f"the bubble changed size during the demo: {sizes}"
    assert bubble.width() == BUBBLE_WIDTH
    assert win.rect().contains(bubble.geometry()), "bubble left the window on expanding"

    controller.go_next()
    qt_app.processEvents()
    plain = controller.overlay.bubble
    assert plain.width() == BUBBLE_WIDTH
    assert plain.body_label.minimumHeight() == 0, "the held height leaked to the next step"
    assert win.rect().contains(plain.geometry())

    controller.skip()


@pytest.mark.gui
def test_replay_button_appears_only_on_a_demo_step(qt_app, host):
    from ui.widgets.tutorial_overlay import TutorialController, TypingDemo

    win, _ = host
    steps = [
        TutorialStep("Demo", "Intro.", demo=TypingDemo("/x", "Expanded.")),
        TutorialStep("Plain", "No demo."),
    ]
    controller = TutorialController(win, steps)
    controller.start()
    qt_app.processEvents()

    bubble = controller.overlay.bubble
    assert bubble.replay_btn.isVisible()
    assert not bubble.replay_btn.icon().isNull(), "the replay button has no icon"

    controller.go_next()
    qt_app.processEvents()
    assert not controller.overlay.bubble.replay_btn.isVisible()

    controller.skip()


@pytest.mark.gui
def test_replay_button_restarts_the_animation(qt_app, host):
    from ui.widgets.tutorial_overlay import TutorialController, TypingDemo

    win, _ = host
    demo = TypingDemo("/getting-started", "Expanded text.")
    controller = TutorialController(win, [TutorialStep("Demo", "Intro.", demo=demo)])
    controller.start()
    qt_app.processEvents()

    bubble = controller.overlay.bubble
    while not bubble.demo_expanded:
        bubble.on_demo_tick()
    qt_app.processEvents()
    assert demo.expansion in bubble.body_label.text()

    expanded_size = bubble.size().toTuple()

    bubble.replay_btn.click()
    qt_app.processEvents()

    assert not bubble.demo_expanded, "replay did not restart the demo"
    assert bubble.demo_typed == 0
    assert demo.expansion not in bubble.body_label.text()
    assert bubble.demo_timer.isActive()
    assert bubble.size().toTuple() == expanded_size, "replaying resized the bubble"
    assert win.rect().contains(bubble.geometry())

    controller.skip()


@pytest.mark.gui
def test_replay_is_a_no_op_without_a_demo(qt_app, host):
    from ui.widgets.tutorial_overlay import TutorialController

    win, _ = host
    controller = TutorialController(win, [TutorialStep("Plain", "No demo.")])
    controller.start()
    qt_app.processEvents()

    controller.overlay.bubble.replay_demo()
    qt_app.processEvents()

    controller.skip()


@pytest.mark.gui
def test_typed_trigger_uses_the_ordinary_text_colour(qt_app, host):
    """The trigger reads as typing, not as a coloured highlight."""
    from ui.widgets.tutorial_overlay import TutorialController, TypingDemo

    win, _ = host
    demo = TypingDemo("/getting-started", "Expanded.")
    controller = TutorialController(win, [TutorialStep("Demo", "Intro.", demo=demo)])
    controller.start()
    qt_app.processEvents()

    bubble = controller.overlay.bubble
    bubble.on_demo_tick()
    markup = bubble.body_label.text()

    assert "color:" not in markup, f"the trigger is being recoloured: {markup}"
    assert "/" in markup

    controller.skip()


@pytest.mark.gui
def test_an_oversized_bubble_stays_anchored_on_screen(qt_app, host):
    """A bubble bigger than its host must not clamp itself off the top-left."""
    from PySide6.QtCore import QRect
    from ui.widgets.tutorial_overlay import TutorialController

    win, button = host
    controller = TutorialController(win, [TutorialStep("Big", "body", target=lambda: button)])
    controller.start()
    qt_app.processEvents()

    overlay = controller.overlay
    huge = QRect(0, 0, overlay.width() + 400, overlay.height() + 400)
    clamped = overlay.clamp_to_area(huge, overlay.rect())

    assert clamped.left() >= overlay.rect().left()
    assert clamped.top() >= overlay.rect().top()

    controller.skip()


@pytest.mark.gui
def test_a_group_of_targets_gets_one_spotlight_covering_them_all(qt_app, host):
    from PySide6.QtWidgets import QPushButton, QWidget, QHBoxLayout
    from ui.widgets.tutorial_overlay import TutorialController

    win, _ = host
    row = QWidget()
    layout = QHBoxLayout(row)
    left, right = QPushButton("new"), QPushButton("cancel")
    layout.addWidget(left)
    layout.addWidget(right)
    win.setCentralWidget(row)
    qt_app.processEvents()

    controller = TutorialController(
        win, [TutorialStep("Row", "body", target=lambda: [left, right])]
    )
    controller.start()
    qt_app.processEvents()

    spot = controller.overlay.spotlight
    overlay = controller.overlay
    assert spot.contains(overlay.widget_rect(left))
    assert spot.contains(overlay.widget_rect(right))

    controller.skip()


@pytest.mark.gui
def test_a_group_ignores_targets_that_are_gone(qt_app, host):
    """One missing widget in a group must not lose the whole spotlight."""
    from ui.widgets.tutorial_overlay import TutorialController

    win, button = host
    controller = TutorialController(
        win, [TutorialStep("Row", "body", target=lambda: [None, button])]
    )
    controller.start()
    qt_app.processEvents()

    assert not controller.overlay.spotlight.isEmpty()
    controller.skip()


@pytest.mark.gui
def test_bubble_minimises_overlap_when_the_target_fills_the_window(qt_app, host):
    """A target with nowhere beside it must not be covered dead centre."""
    from PySide6.QtWidgets import QWidget
    from ui.widgets.tutorial_overlay import TutorialController

    win, _ = host
    hog = QWidget()
    win.setCentralWidget(hog)
    qt_app.processEvents()

    controller = TutorialController(win, [TutorialStep("One", "body", target=lambda: hog)])
    controller.start()
    qt_app.processEvents()

    overlay = controller.overlay
    bubble = overlay.bubble.geometry()

    assert win.rect().contains(bubble)
    # Centring would leave the bubble in the middle of the target; the
    # chosen spot has to hug an edge instead.
    assert bubble.top() <= overlay.spotlight.top() + bubble.height() or \
        bubble.bottom() >= overlay.spotlight.bottom() - bubble.height()

    controller.skip()


@pytest.mark.gui
def test_a_broken_target_falls_back_to_a_centered_step(qt_app, host):
    from ui.widgets.tutorial_overlay import TutorialController

    win, _ = host

    def explode():
        raise RuntimeError("target is gone")

    steps = [
        TutorialStep("Raises", "body", target=explode),
        TutorialStep("None", "body", target=lambda: None),
    ]
    controller = TutorialController(win, steps)

    controller.start()
    qt_app.processEvents()
    assert controller.overlay.spotlight.isEmpty()

    controller.go_next()
    qt_app.processEvents()
    assert controller.overlay.spotlight.isEmpty()

    controller.skip()


@pytest.mark.gui
def test_overlay_follows_a_window_resize(qt_app, host):
    from ui.widgets.tutorial_overlay import TutorialController

    win, button = host
    controller = TutorialController(win, [TutorialStep("One", "body", target=lambda: button)])
    controller.start()
    qt_app.processEvents()

    win.resize(640, 480)
    qt_app.processEvents()

    assert controller.overlay.geometry() == win.rect()
    controller.skip()


@pytest.mark.gui
def test_starting_twice_does_not_stack_overlays(qt_app, host):
    from ui.widgets.tutorial_overlay import TutorialController

    win, _ = host
    controller = TutorialController(win, [TutorialStep("One", "body")])

    controller.start()
    qt_app.processEvents()
    first = controller.overlay

    controller.start()
    qt_app.processEvents()

    assert controller.overlay is first
    controller.skip()

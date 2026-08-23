"""
Tests that menu bar entries keep their geometry when hovered.

Styling only QMenuBar::item:selected left the normal state on Qt's own
metrics and the hovered state on the stylesheet box model, so entries grew
as the mouse crossed them.
"""

import pytest


@pytest.fixture
def qt_app(mock_qt_app):
    from PySide6.QtWidgets import QApplication

    if not isinstance(mock_qt_app, QApplication):
        pytest.skip("GUI tests need a QApplication; run pytest with --gui")

    return mock_qt_app


@pytest.fixture
def themed_window(qt_app):
    from PySide6.QtWidgets import QMainWindow
    from ui.theme_manager import ThemeManager

    previous = ThemeManager.get_instance()
    previous_qss = qt_app.styleSheet()

    tm = ThemeManager(qt_app)
    tm.apply("dark", scale_pct=100)

    win = QMainWindow()
    menubar = win.menuBar()
    for name in ("File", "Edit", "Tools", "Help"):
        menubar.addMenu(name).addAction("An action")
    win.resize(900, 600)
    win.show()
    qt_app.processEvents()

    yield win, menubar

    win.close()
    ThemeManager.instance = previous
    qt_app.setStyleSheet(previous_qss)


@pytest.mark.gui
def test_menu_bar_items_do_not_move_when_hovered(qt_app, themed_window):
    """Hovering must change colour only, never geometry."""
    from PySide6.QtCore import QEvent, QPoint
    from PySide6.QtGui import QAction

    win, menubar = themed_window
    actions = [a for a in menubar.actions() if not a.isSeparator()]
    before = [menubar.actionGeometry(a) for a in actions]

    for action in actions:
        rect = menubar.actionGeometry(action)
        menubar.setActiveAction(action)
        enter = QEvent(QEvent.Enter)
        qt_app.sendEvent(menubar, enter)
        qt_app.processEvents()

        after = [menubar.actionGeometry(a) for a in actions]
        assert after == before, (
            f"hovering '{action.text()}' moved the menu bar entries:\n"
            f"  before={before}\n  after={after}"
        )

    menubar.setActiveAction(None)
    qt_app.processEvents()
    assert [menubar.actionGeometry(a) for a in actions] == before


@pytest.mark.gui
def test_menu_bar_height_is_stable_when_hovered(qt_app, themed_window):
    win, menubar = themed_window
    actions = [a for a in menubar.actions() if not a.isSeparator()]

    height = menubar.height()
    hint = menubar.sizeHint().height()

    for action in actions:
        menubar.setActiveAction(action)
        qt_app.processEvents()
        assert menubar.height() == height, "the menu bar changed height on hover"
        assert menubar.sizeHint().height() == hint

    menubar.setActiveAction(None)


@pytest.mark.gui
def test_menu_bar_item_rule_is_styled(qt_app, themed_window):
    """
    The base rule must exist alongside the hovered one.

    Without it the two states are drawn by different box models, which is
    what made entries grow.
    """
    from ui.theme_manager import ThemeManager

    tm = ThemeManager.get_instance()
    qss = tm.build_qss(tm.get_colors(), 100)

    assert "QMenuBar::item {" in qss, "QMenuBar::item has no base rule"
    assert "QMenuBar::item:selected {" in qss

"""
Tests for the application font, which is what the widgets outside
ThemeManager.apply_fonts' reach inherit: QMenuBar, the popup QMenus,
QToolBar and the tray menu.

These need real widgets, so they are marked `gui` and run only with
pytest --gui.
"""

import pytest


@pytest.fixture
def qt_app(mock_qt_app):
    from PySide6.QtWidgets import QApplication

    if not isinstance(mock_qt_app, QApplication):
        pytest.skip("GUI tests need a QApplication; run pytest with --gui")

    return mock_qt_app


class FakeMain:
    """
    Stands in for the main() app object that owns the scaled QFont roles.

    scale() mimics scale_ui_cfg: it recomputes every role from the
    unscaled base sizes, so the roles are always derived, never compounded.
    """

    BASE = {"small": 10, "medium": 12, "large": 14, "extra_large": 18, "humongous": 28}

    def __init__(self, family="Arial"):
        self.family = family
        self.scale(100)

    def scale(self, pct):
        from PySide6.QtGui import QFont

        self.scale_pct = pct
        for role, base in self.BASE.items():
            size = max(6, round(base * pct / 100))
            setattr(self, f"{role}_font_size", QFont(self.family, size))
            setattr(self, f"{role}_font_size_bold", QFont(self.family, size, QFont.Bold))

    def apply_fonts_to_all_widgets(self):
        """
        Mirror the real blanket sweep, including its own app.setFont call.

        ThemeManager.force_repaint calls into this, so the sweep sets the
        application font a second time in every apply(). Reproducing that
        here is the point: the two app fonts disagreeing is what left the
        menu bar and toolbar adrift.
        """
        from PySide6.QtWidgets import QApplication
        from ui.theme_manager import ThemeManager

        app = QApplication.instance()
        app.setFont(self.medium_font_size)
        for top in app.topLevelWidgets():
            ThemeManager.apply_fonts(top)


@pytest.fixture
def themed(qt_app):
    """A ThemeManager wired to a fake main, restored afterwards."""
    from ui.theme_manager import ThemeManager

    previous_instance = ThemeManager.get_instance()
    previous_font = qt_app.font()
    previous_qss = qt_app.styleSheet()

    main = FakeMain()
    tm = ThemeManager(qt_app, main=main)

    yield tm, main

    ThemeManager.instance = previous_instance
    qt_app.setFont(previous_font)
    qt_app.setStyleSheet(previous_qss)


def apply_scale(tm, main, pct):
    main.scale(pct)
    tm.apply("dark", scale_pct=pct)


@pytest.mark.gui
def test_app_font_matches_the_medium_role(qt_app, themed):
    """
    The application font has to be the app's own medium role.

    Deriving a second size here is what once left the menu bar and
    toolbar a size adrift from everything else.
    """
    tm, main = themed

    for pct in (100, 150, 75):
        apply_scale(tm, main, pct)
        assert qt_app.font().pointSize() == main.medium_font_size.pointSize(), \
            f"app font disagrees with the medium role at {pct}%"


@pytest.mark.gui
def test_menu_bar_and_toolbar_return_to_their_original_size(qt_app, themed):
    """Raising the UI scale and putting it back must be a round trip."""
    from PySide6.QtWidgets import QMainWindow, QToolBar

    tm, main = themed
    win = QMainWindow()
    menubar = win.menuBar()
    menu = menubar.addMenu("File")
    menu.addAction("New")
    toolbar = QToolBar("Main", win)
    win.addToolBar(toolbar)
    toolbar.addAction("Home")
    win.show()
    qt_app.processEvents()

    def sizes():
        return {
            "menubar": menubar.font().pointSize(),
            "menu": menu.font().pointSize(),
            "toolbar": toolbar.font().pointSize(),
        }

    def check_against_medium(pct):
        expected = main.medium_font_size.pointSize()
        for name, size in sizes().items():
            assert size == expected, \
                f"{name} is {size}pt at {pct}% but the medium role is {expected}pt"

    apply_scale(tm, main, 100)
    qt_app.processEvents()
    check_against_medium(100)
    before = sizes()

    apply_scale(tm, main, 150)
    qt_app.processEvents()
    during = sizes()
    check_against_medium(150)
    assert all(during[k] > before[k] for k in before), \
        f"menus ignored the scale increase: {before} -> {during}"

    apply_scale(tm, main, 100)
    qt_app.processEvents()
    check_against_medium(100)

    assert sizes() == before, f"menus did not come back: {before} -> {during} -> {sizes()}"

    win.close()


@pytest.mark.gui
def test_repeated_scale_changes_do_not_drift(qt_app, themed):
    """Wandering through several scales must still land back exactly."""
    from PySide6.QtWidgets import QMainWindow

    tm, main = themed
    win = QMainWindow()
    menubar = win.menuBar()
    menubar.addMenu("File").addAction("New")
    win.show()
    qt_app.processEvents()

    apply_scale(tm, main, 100)
    qt_app.processEvents()
    before = menubar.font().pointSize()

    for pct in (150, 75, 125, 90, 150, 100):
        apply_scale(tm, main, pct)
        qt_app.processEvents()

    assert menubar.font().pointSize() == before

    win.close()


@pytest.mark.gui
def test_font_family_change_reaches_the_menus(qt_app, themed):
    """A new font family has to reach inherit-only widgets too."""
    from PySide6.QtWidgets import QMainWindow

    tm, main = themed
    win = QMainWindow()
    menubar = win.menuBar()
    win.show()
    qt_app.processEvents()

    apply_scale(tm, main, 100)
    qt_app.processEvents()

    main.family = "Courier New"
    apply_scale(tm, main, 100)
    qt_app.processEvents()

    assert menubar.font().family() == "Courier New"

    win.close()


@pytest.mark.gui
def test_font_scale_falls_back_when_no_main_app_is_reachable(qt_app, themed):
    """Isolated widget tests have no main() object; this must not raise."""
    tm, _ = themed
    tm.main = None

    tm.apply_font_scale(150)

    assert qt_app.font().pointSize() == 15

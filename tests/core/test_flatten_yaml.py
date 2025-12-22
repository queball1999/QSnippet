import pytest

from QSnippet import main


class DummyMain(main):
    """
    Create main without running __init__.
    """
    def __init__(self):
        pass


def test_flatten_yaml_basic():
    app = DummyMain()

    config = {
        "program_name": "QSnippet",
        "version": "1.0",
        "images": {
            "icon": "icon.png",
            "logo": "logo.png",
        },
        "colors": {
            "primary": "#fff",
            "secondary": "#000",
        },
    }

    result = app.flatten_yaml(config)

    assert result is True

    # top level
    assert app.program_name == "QSnippet"
    assert app.version == "1.0"

    # flattened nested
    assert app.images_icon == "icon.png"
    assert app.images_logo == "logo.png"
    assert app.colors_primary == "#fff"
    assert app.colors_secondary == "#000"


def test_flatten_yaml_handles_empty_dict():
    app = DummyMain()
    assert app.flatten_yaml({}) is True


def test_flatten_yaml_failure_returns_false():
    app = DummyMain()

    # items.items() will raise AttributeError
    bad_input = None

    assert app.flatten_yaml(bad_input) is False

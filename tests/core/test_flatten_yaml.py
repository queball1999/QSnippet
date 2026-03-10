import pytest

from QSnippet import main


class DummyMain(main):
    """
    Create main without running __init__.
    """
    def __init__(self):
        pass


def test_flatten_yaml_basic():
    """
    Test basic YAML flattening with nested dictionaries.

    Verifies that nested keys are flattened with underscores as separators
    and that all values are correctly accessible as attributes.
    """
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
    """
    Test that flattening an empty dictionary returns True.

    Verifies that the flatten_yaml method handles edge case of empty input.
    """
    app = DummyMain()
    assert app.flatten_yaml({}) is True


def test_flatten_yaml_failure_returns_false():
    """
    Test that flatten_yaml returns False when given invalid input.

    Verifies error handling when the input is not a valid dictionary.
    """
    app = DummyMain()

    # items.items() will raise AttributeError
    bad_input = None

    assert app.flatten_yaml(bad_input) is False

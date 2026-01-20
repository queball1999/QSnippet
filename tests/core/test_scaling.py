import pytest

from QSnippet import main


class FakeScreen:
    def __init__(self, w, h):
        self._w = w
        self._h = h

    def width(self):
        return self._w

    def height(self):
        return self._h


class DummyMain(main):
    def __init__(self):
        self.REFERENCE_WIDTH = 1920
        self.REFERENCE_HEIGHT = 1080


def test_scale_width_and_height():
    app = DummyMain()
    screen = FakeScreen(3840, 2160)  # 2x scale

    assert app.scale_width(100, screen) == 200
    assert app.scale_height(50, screen) == 100


def test_scale_dict_sizes():
    app = DummyMain()
    screen = FakeScreen(2560, 1440)  # ~1.33x

    sizes = {
        "btn": {"width": 150, "height": 50, "radius": 10},
        "card": {"width": 300, "height": 200, "radius": 20},
    }

    scaled = app.scale_dict_sizes(sizes, screen)

    assert scaled["btn"]["width"] > sizes["btn"]["width"]
    assert scaled["btn"]["height"] > sizes["btn"]["height"]
    assert scaled["btn"]["radius"] > 0

    assert scaled["card"]["width"] > sizes["card"]["width"]
    assert scaled["card"]["height"] > sizes["card"]["height"]


def test_scale_font_sizes():
    app = DummyMain()
    screen = FakeScreen(1920, 2160)  # 2x height

    fonts = {
        "small": 12,
        "medium": 16,
        "large": 24,
    }

    scaled = app.scale_font_sizes(fonts, screen)

    assert scaled["small"] == 24
    assert scaled["medium"] == 32
    assert scaled["large"] == 48

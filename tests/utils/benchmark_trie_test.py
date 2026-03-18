import random
import string
import sys
import time
import types
from contextlib import nullcontext
from unittest.mock import MagicMock

import pytest

from tests.db.benchmark_test import record
from utils.keyboard_utils import SnippetExpander

BENCHMARK_TRIGGER_SIZES = [10, 100, 1_000, 5_000, 10_000, 25_000]


class DummyListener:
    def __init__(self, on_press=None):
        self.on_press = on_press

    def start(self) -> None:
        return None

    def stop(self) -> None:
        return None


class DummyController:
    def pressed(self, _key):
        return nullcontext()

    def press(self, _key) -> None:
        return None

    def release(self, _key) -> None:
        return None


class DummyKeyboardModule:
    class Key:
        space = object()
        shift = object()
        enter = object()
        ctrl = object()
        ctrl_l = object()
        ctrl_r = object()
        cmd = object()

    Listener = DummyListener
    Controller = DummyController


@pytest.fixture
def dummy_pynput(monkeypatch):
    module = types.SimpleNamespace(keyboard=DummyKeyboardModule)
    monkeypatch.setitem(sys.modules, "pynput", module)
    return module


def build_trigger_index(count: int, seed: int = 1337) -> list[dict]:
    rng = random.Random(seed)
    rows = []
    for i in range(count):
        suffix = "".join(rng.choices(string.ascii_lowercase + string.digits, k=8))
        rows.append(
            {
                "id": i,
                "trigger": f"/tr-{i}-{suffix}",
                "paste_style": "Clipboard",
                "return_press": False,
                "enabled": True,
            }
        )
    return rows


def create_expander(trigger_count: int) -> SnippetExpander:
    db = MagicMock()
    db.get_all_custom_placeholders.return_value = []
    db.get_enabled_trigger_index.return_value = build_trigger_index(trigger_count)
    db.get_snippet_by_trigger.return_value = {}
    return SnippetExpander(snippets_db=db, parent=MagicMock())


def make_buffers(triggers: list[str], count: int, seed: int = 1337) -> list[str]:
    rng = random.Random(seed)
    buffers = []
    half = count // 2
    for _ in range(half):
        trigger = triggers[rng.randrange(0, len(triggers))]
        buffers.append(f"prefix-{rng.randrange(1000)}{trigger}")
    for i in range(count - half):
        buffers.append(f"prefix-{i}-/missing-{rng.randrange(100000)}")
    rng.shuffle(buffers)
    return buffers


def naive_match_suffix(buffer: str, triggers: list[str], max_trigger_len: int) -> str | None:
    suffix = buffer[-max_trigger_len:]
    best_match = None
    for trigger in triggers:
        if suffix.endswith(trigger):
            if best_match is None or len(trigger) > len(best_match):
                best_match = trigger
    return best_match


@pytest.mark.benchmark
@pytest.mark.parametrize("count", BENCHMARK_TRIGGER_SIZES)
def test_benchmark_trie_match_vs_naive(dummy_pynput, count):
    """Benchmark trie suffix matching against a naive linear scan baseline.

    Args:
        count (int): Number of enabled triggers generated for the benchmark.
    Returns:
        None
    """
    expander = create_expander(count)
    triggers = list(expander.trigger_map.keys())
    buffers = make_buffers(triggers, count=2_000)

    iterations = min(40_000, max(8_000, count * 2))

    trie_hits = 0
    start = time.perf_counter()
    for i in range(iterations):
        expander.buffer = buffers[i % len(buffers)]
        if expander.match_trigger_suffix() is not None:
            trie_hits += 1
    trie_elapsed = time.perf_counter() - start
    record(count, "trie_match", trie_elapsed)

    naive_hits = 0
    start = time.perf_counter()
    for i in range(iterations):
        if naive_match_suffix(buffers[i % len(buffers)], triggers, expander.max_trigger_len) is not None:
            naive_hits += 1
    naive_elapsed = time.perf_counter() - start
    record(count, "naive_match", naive_elapsed)

    assert trie_hits == naive_hits


@pytest.mark.benchmark
@pytest.mark.parametrize("count", BENCHMARK_TRIGGER_SIZES)
def test_benchmark_trie_build(dummy_pynput, count):
    """Benchmark trigger map and trie rebuild time at larger trigger counts.

    Args:
        count (int): Number of enabled triggers generated for the benchmark.
    Returns:
        None
    """
    expander = create_expander(count)

    start = time.perf_counter()
    expander.build_trigger_map()
    elapsed = time.perf_counter() - start

    record(count, "trie_build", elapsed)
    assert expander.max_trigger_len > 0

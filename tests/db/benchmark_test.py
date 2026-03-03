import time
import random
import string
import pytest

from utils.snippet_db import SnippetDB


BENCHMARK_SIZES = [10, 100, 1_000, 5_000, 10_000, 100_000, 1_000_000]

_results: list = []


def random_string(length=10):
    """Generate a random lowercase ASCII string.

    Args:
        length (int): Number of characters to generate. Defaults to 10.

    Returns:
        str: A random string of lowercase ASCII letters.
    """
    return "".join(random.choices(string.ascii_lowercase, k=length))


def seed_large_db(db, count):
    """Bulk-insert randomly generated snippets into a database.

    Args:
        db (SnippetDB): The database instance to populate.
        count (int): Number of snippet rows to insert.
    """
    rows = [
        (
            True,
            f"Label {i}",
            f"/trigger-{i}-{random_string(5)}",
            f"Snippet content {random_string(20)} for entry {i}",
            random.choice(["clipboard", "typing"]),
            random.choice([True, False]),
            random.choice(["Folder A", "Folder B", "Folder C", ""]),
            f"{random_string(4)},{random_string(4)}",
        )
        for i in range(count)
    ]
    with db.conn:
        db.conn.executemany(
            "INSERT OR IGNORE INTO snippets "
            "(enabled, label, trigger, snippet, paste_style, return_press, folder, tags) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )


def record(count, op, elapsed):
    """Record a benchmark result into the global results list.

    Args:
        count (int): Number of rows in the database for this run.
        op (str): Name of the operation being benchmarked (e.g. ``"search"``).
        elapsed (float): Wall-clock time in seconds for the operation.
    """
    per_item = (elapsed / count) * 1000 if count else 0
    _results.append({
        "qty": count,
        "type": op,
        "per_item_ms": per_item,
        "total_ms": elapsed * 1000,
    })


@pytest.mark.benchmark
@pytest.mark.parametrize("count", BENCHMARK_SIZES)
def test_benchmark_search_snippets(tmp_path, count):
    """Benchmark search_snippets across varying database sizes.

    Args:
        tmp_path (Path): Pytest-provided temporary directory.
        count (int): Number of rows seeded before timing the search.
    """
    db = SnippetDB(tmp_path / f"bench_search_{count}.db")
    seed_large_db(db, count)
    start = time.perf_counter()
    results = db.search_snippets("content")
    record(count, "search", time.perf_counter() - start)
    assert results is not None


@pytest.mark.benchmark
@pytest.mark.parametrize("count", BENCHMARK_SIZES)
def test_benchmark_get_all_snippets(tmp_path, count):
    """Benchmark get_all_snippets across varying database sizes.

    Args:
        tmp_path (Path): Pytest-provided temporary directory.
        count (int): Number of rows seeded before timing the full fetch.
    """
    db = SnippetDB(tmp_path / f"bench_getall_{count}.db")
    seed_large_db(db, count)
    start = time.perf_counter()
    results = db.get_all_snippets()
    record(count, "get_all", time.perf_counter() - start)
    assert results is not None


@pytest.mark.benchmark
@pytest.mark.parametrize("count", BENCHMARK_SIZES)
def test_benchmark_get_random_snippet(tmp_path, count):
    """Benchmark get_random_snippet across varying database sizes.

    Args:
        tmp_path (Path): Pytest-provided temporary directory.
        count (int): Number of rows seeded before timing the random fetch.
    """
    db = SnippetDB(tmp_path / f"bench_random_{count}.db")
    seed_large_db(db, count)
    start = time.perf_counter()
    result = db.get_random_snippet()
    record(count, "get_random", time.perf_counter() - start)
    assert result is not None


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    """Print a formatted benchmark results table after the test session.

    Skips output when no benchmark results were recorded. Results are grouped
    by row count and sorted by operation name within each group.

    Args:
        terminalreporter: Pytest terminal reporter plugin instance.
        exitstatus (int): The exit status code of the test session.
        config: Pytest config object.
    """
    if not _results:
        return

    _results.sort(key=lambda r: (r["qty"], r["type"]))

    header = f"{'Qty':>12}  {'Type':<12}  {'Per Item':>15}  {'Total':>12}"
    divider = "-" * len(header)

    terminalreporter.write_sep("=", "Benchmark Results")
    terminalreporter.write_line(header)
    terminalreporter.write_line(divider)

    prev_qty = None
    for r in _results:
        if prev_qty is not None and r["qty"] != prev_qty:
            terminalreporter.write_line("")
        prev_qty = r["qty"]
        terminalreporter.write_line(
            f"{r['qty']:>12,}  "
            f"{r['type']:<12}  "
            f"{r['per_item_ms']:>12.4f} ms  "
            f"{r['total_ms']:>9.2f} ms"
        )

    terminalreporter.write_line(divider)

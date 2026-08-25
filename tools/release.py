#!/usr/bin/env python3
"""
Cut a release tag after checking everything the pipeline will check.

The build pipeline enforces its own rules (build_manager.yaml refuses a
release tag that is not reachable from main), but it only finds out after a
tag is pushed, which means a bad tag has to be deleted from the remote to
retry. This script runs the same checks locally, before the tag exists.

    python tools/release.py v0.0.8-release
    python tools/release.py v0.0.8-dev
    python tools/release.py v0.0.8-release --dry-run

Or through make:

    make release v0.0.8-release
    make release TAG=v0.0.8-dev

Checks, in order:
  1. The tag is well formed and uses a suffix the pipeline recognises.
  2. config/config.yaml carries the matching version.
  3. A release notice exists for the version (fatal for -release,
     a warning for -dev).
  4. The working tree is clean.
  5. The tag does not already exist locally or on the remote.
  6. For -release: HEAD is on main and reachable from the remote's main,
     the same rule the guard job applies.

The remote is detected, not assumed: this repo is cloned as "github" in
places and "origin" in others. Override it with --remote.

Anything fatal exits non-zero and nothing is tagged.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent

# Mirrors the tag globs in .github/workflows/build_manager.yaml and the
# platform workflows. A suffix outside this set triggers no workflow at all.
TAG_PATTERN = re.compile(r"^v(\d+)\.(\d+)\.(\d+)-(release|dev|windows|linux)$")

SUFFIX_HELP = {
    "release": "stable release, must be cut from main",
    "dev": "Dev-channel prerelease, any branch",
    "windows": "Windows standalone build, no release published",
    "linux": "Linux standalone build, no release published",
}

problems: list[str] = []
warnings: list[str] = []


def fail(message: str) -> None:
    problems.append(message)


def warn(message: str) -> None:
    warnings.append(message)


def git(*args: str, check: bool = True) -> str:
    """Run a git command in the repo and return its stripped stdout."""
    result = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if check and result.returncode != 0:
        raise SystemExit(
            f"git {' '.join(args)} failed:\n{result.stderr.strip()}"
        )
    return (result.stdout or "").strip()


def detect_remote() -> str:
    """
    Find the remote to tag against.

    This repo is not always cloned as "origin" (the primary clone calls it
    "github"), and CI is, so nothing can assume either name. Prefer the
    current branch's upstream, then origin, then the only remote there is.
    """
    upstream = git("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}",
                   check=False)
    if upstream and "/" in upstream:
        return upstream.split("/", 1)[0]

    remotes = git("remote").splitlines()
    if "origin" in remotes:
        return "origin"
    if len(remotes) == 1:
        return remotes[0]

    raise SystemExit(
        "cannot tell which remote to use; pass --remote explicitly "
        f"(found: {', '.join(remotes) or 'none'})"
    )


def config_version() -> str:
    """Return the version string from config/config.yaml."""
    path = REPO_ROOT / "config" / "config.yaml"
    with open(path, encoding="utf-8") as handle:
        return str((yaml.safe_load(handle) or {}).get("version", "")).strip()


def check_version(base: str, suffix: str) -> None:
    """
    Compare config/config.yaml against the tag.

    A release tag must match exactly and carry no prerelease suffix; shipping
    0.0.8-dev as a stable release would leave every install reporting a
    version the updater never offers. A dev tag only has to share the base
    version, so 0.0.8-dev2 can be tagged v0.0.8-dev for a second test build.
    """
    actual = config_version()

    if not actual:
        fail("config/config.yaml has no version set")
        return

    if suffix == "release":
        if actual != base:
            fail(
                f"config/config.yaml says version {actual!r}, but tag "
                f"v{base}-release expects {base!r}.\n"
                f"    Set it to \"{base}\" (a stable release must not carry a "
                f"prerelease suffix) and commit the change."
            )
        return

    if actual == base:
        # 0.0.8 tagged as -dev is legal but usually means a forgotten bump.
        warn(
            f"config/config.yaml says {actual!r}, which reads like a stable "
            f"version for a {suffix} build"
        )
    elif not actual.startswith(base):
        fail(
            f"config/config.yaml says version {actual!r}, which does not "
            f"match tag version {base}"
        )


def check_notice(base: str, suffix: str) -> None:
    """
    Require a release notice for the version.

    QSnippet shows notices/<tag>-notice.yaml after an update installs, and
    the updater reads that directory directly. Releasing without one means a
    silent update for every user.
    """
    notice = REPO_ROOT / "notices" / f"v{base}-notice.yaml"

    if notice.is_file():
        return

    archived = REPO_ROOT / "notices" / "history" / f"v{base}-notice.yaml"
    hint = ""
    if archived.is_file():
        hint = (
            f"\n    Found one in notices/history/; move it back to notices/ "
            f"if this is a re-release."
        )

    message = (
        f"no release notice at notices/v{base}-notice.yaml.{hint}\n"
        f"    Copy the previous notice as a template and describe what "
        f"changed for users."
    )

    if suffix == "release":
        fail(message)
    else:
        warn(message)


def check_clean_tree() -> None:
    """A tag points at a commit, not at your working directory."""
    dirty = git("status", "--porcelain")
    if dirty:
        fail(
            "the working tree has uncommitted changes; commit or stash them "
            "first:\n        " + dirty.replace("\n", "\n        ")
        )


def check_tag_is_new(tag: str, remote: str) -> None:
    if git("tag", "--list", tag):
        fail(
            f"tag {tag} already exists locally. Delete it first:\n"
            f"        git tag -d {tag}"
        )

    published = git("ls-remote", "--tags", remote, f"refs/tags/{tag}",
                    check=False)
    if published:
        fail(
            f"tag {tag} already exists on {remote}. Delete it first:\n"
            f"        git push {remote} :refs/tags/{tag}"
        )


def check_on_main(remote: str) -> None:
    """
    The same rule build_manager.yaml's guard job applies to release tags,
    checked here so a rejected tag never reaches the remote.
    """
    git("fetch", remote, "main", "--quiet", check=False)

    head = git("rev-parse", "HEAD")
    branch = git("rev-parse", "--abbrev-ref", "HEAD")

    if branch != "main":
        warn(f"you are on branch {branch!r}, not main")

    ancestor = subprocess.run(
        ["git", "merge-base", "--is-ancestor", head, f"{remote}/main"],
        cwd=REPO_ROOT,
        capture_output=True,
        check=False,
    )
    if ancestor.returncode != 0:
        fail(
            f"HEAD ({head[:9]}) is not reachable from {remote}/main, so the "
            f"guard job would reject this tag.\n"
            f"    Merge the work into main through a pull request first, or "
            f"publish it as a -dev tag instead."
        )
        return

    if git("rev-parse", f"{remote}/main", check=False) != head:
        warn(
            f"HEAD is behind {remote}/main; the release will be cut from an "
            f"older commit than the branch tip"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check and push a QSnippet release tag",
    )
    parser.add_argument("tag", help="Tag to create, e.g. v0.0.8-release")
    parser.add_argument("--dry-run", action="store_true",
                        help="Run the checks and stop; create no tag")
    parser.add_argument("--yes", "-y", action="store_true",
                        help="Skip the confirmation prompt")
    parser.add_argument("--no-push", action="store_true",
                        help="Create the tag locally but do not push it")
    parser.add_argument("--remote", default="",
                        help="Remote to tag against (default: the branch's "
                             "upstream, else origin, else the only remote)")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    tag = args.tag.strip()

    match = TAG_PATTERN.match(tag)
    if not match:
        print(f"error: {tag!r} is not a tag this pipeline recognises.\n")
        print("Expected v<major>.<minor>.<patch>-<suffix>, one of:")
        for suffix, description in SUFFIX_HELP.items():
            print(f"  v0.0.8-{suffix:<8} {description}")
        return 2

    major, minor, patch, suffix = match.groups()
    base = f"{major}.{minor}.{patch}"

    remote = args.remote or detect_remote()

    print(f"Preparing {tag}  ({SUFFIX_HELP[suffix]})")
    print(f"Version in config/config.yaml: {config_version() or '(unset)'}")
    print(f"Remote: {remote}\n")

    check_version(base, suffix)
    check_notice(base, suffix)
    check_clean_tree()
    check_tag_is_new(tag, remote)
    if suffix == "release":
        check_on_main(remote)

    for message in warnings:
        print(f"warning: {message}")
    if warnings:
        print()

    if problems:
        for message in problems:
            print(f"error: {message}")
        print(f"\n{len(problems)} problem(s) found; nothing was tagged.")
        return 1

    print("All checks passed.")

    if args.dry_run:
        print(f"Dry run: would tag {git('rev-parse', '--short', 'HEAD')} "
              f"as {tag} and push it to {remote}.")
        return 0

    if not args.yes:
        head = git("rev-parse", "--short", "HEAD")
        target = ("create the tag locally" if args.no_push
                  else f"push it to {remote}")
        answer = input(f"Tag {head} as {tag} and {target}? [y/N] ").strip().lower()
        if answer not in ("y", "yes"):
            print("Aborted; nothing was tagged.")
            return 1

    git("tag", tag)
    print(f"Created tag {tag}")

    if args.no_push:
        print(f"Not pushed. When ready: git push {remote} {tag}")
        return 0

    git("push", remote, tag)
    print(f"Pushed {tag}. Watch the run under Actions, \"Build Manager\".")
    return 0


if __name__ == "__main__":
    sys.exit(main())

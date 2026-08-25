"""
Update checking and installation, delegated to the bundled updater binary.

QSnippet ships `updater` (built from QUpdateTool) and shells out to it,
keeping download, signature verification, and elevation out of this process
so the updater can stop and replace QSnippet while it isn't running.

Two entry points:

    UpdateChecker   background check for the startup preflight and the
                    Help menu; runs "updater --check-only --json"
    launch_update   hands off to the updater to install, ending with it
                    stopping this process

## Integrity

Before launching the updater, its SHA-256 is checked against the value
recorded in config/build_info.py at release time, since a binary can't
verify its own integrity. See QUpdateTool2.0/docs/SECURITY.md. The check is
skipped, with a warning, when no hash was recorded (a dev/source build).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from utils.logging_utils import logging

logger = logging.getLogger(__name__)

# Exit codes defined by QUpdateTool. Part of the contract between the two.
EXIT_SUCCESS = 0
EXIT_ERROR = 1
EXIT_USAGE = 2
EXIT_NETWORK = 3
EXIT_VERIFICATION = 4
EXIT_INSTALL = 5
EXIT_CANCELLED = 6
EXIT_PROCESS = 7
EXIT_NO_RELEASE = 8
EXIT_UPDATE_AVAILABLE = 10
EXIT_UP_TO_DATE = 11

# How long to let a check run before giving up. A check is two HTTP calls;
# anything beyond this means the network is not usable right now.
CHECK_TIMEOUT_SECONDS = 45

# One message per code. Each says only what that code actually means, so a
# failure is never described as something it was not: an unclassified error
# does not claim the install broke, and a project with no published release
# does not read as a broken network connection.
EXIT_MESSAGES = {
    EXIT_ERROR: "The updater ran into an unexpected problem.",
    EXIT_USAGE: "The updater was misconfigured.",
    EXIT_NETWORK: "Could not reach the update server.",
    EXIT_VERIFICATION: "The update failed its signature check and was discarded.",
    EXIT_INSTALL: "The update could not be installed.",
    EXIT_CANCELLED: "The update was cancelled.",
    EXIT_PROCESS: "QSnippet could not be stopped or restarted for the update.",
    EXIT_NO_RELEASE: "No update is published for this platform yet.",
}


@dataclass
class UpdateInfo:
    """The parsed result of an update check."""

    available: bool = False
    current_version: str = ""
    latest_version: str = ""
    tag: str = ""
    url: str = ""
    notes_title: str = ""
    notes: str = ""
    notes_source: str = ""
    asset: str = ""
    asset_size: int = 0
    published_at: str = ""
    error: str = ""
    raw: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.error

    @classmethod
    def from_payload(cls, payload: dict) -> "UpdateInfo":
        return cls(
            available=bool(payload.get("update_available")),
            current_version=payload.get("current_version", ""),
            latest_version=payload.get("latest_version", ""),
            tag=payload.get("tag", ""),
            url=payload.get("url", ""),
            notes_title=payload.get("notes_title", ""),
            notes=payload.get("notes", ""),
            notes_source=payload.get("notes_source", ""),
            asset=payload.get("asset", ""),
            asset_size=int(payload.get("asset_size") or 0),
            published_at=payload.get("published_at", ""),
            raw=payload,
        )


def updater_filename() -> str:
    """Return the platform-specific name of the bundled updater binary."""
    return "updater.exe" if sys.platform == "win32" else "updater"


def find_updater(main) -> Path | None:
    """
    Locate the bundled updater binary.

    Searched next to the running application first (where the installer
    and .deb place it); a source checkout falls back to the sibling
    QUpdateTool2.0 working copy.
    """
    name = updater_filename()

    candidates = []

    working_dir = getattr(main, "working_dir", None)
    if working_dir:
        candidates.append(Path(working_dir) / name)

    if getattr(sys, "frozen", False):
        candidates.append(Path(sys.executable).parent / name)

    candidates.append(Path(__file__).resolve().parent.parent / name)

    for candidate in candidates:
        if candidate.is_file():
            # Absolute: Windows resolves a relative exe name against PATH,
            # not the working directory, and would fail to find it here.
            return candidate.resolve()

    return None


def is_portable_install(main) -> bool:
    """
    Detect a portable (unzipped) QSnippet rather than an installed one.

    The portable build doesn't ship the updater: running the installer over
    it would leave the portable folder stale instead. An installed build
    always has a build_info stamp from CI; portable packaging strips it.
    """
    if not getattr(sys, "frozen", False):
        return False

    try:
        from config import build_info

        return not getattr(build_info, "BUILD_VERSION", "")
    except ImportError:
        return True


def find_updater_source() -> Path | None:
    """
    Locate a QUpdateTool source checkout, for running from source.

    Returns the directory containing updater_main.py, or None. Only used in
    development; a released build always has the binary.
    """
    checkout = Path(__file__).resolve().parent.parent.parent / "QUpdateTool2.0"

    if (checkout / "updater_main.py").is_file():
        return checkout

    return None


def expected_updater_hash() -> str:
    """
    Read the updater hash recorded at build time.

    Lives in config/build_info.py alongside the other build stamps, written by
    CI when the updater is built into the release.
    """
    try:
        from config import build_info

        return getattr(build_info, "UPDATER_SHA256", "") or ""
    except ImportError:
        return ""


def verify_updater(path: Path) -> tuple:
    """
    Check the updater binary against its recorded hash.

    Returns (is_trusted, reason). A missing recorded hash returns True with a
    warning reason, so development builds still work; a recorded hash that
    does not match returns False and the caller must refuse to run it.
    """
    import hashlib
    import hmac

    expected = expected_updater_hash()

    if not expected:
        return True, "No updater hash recorded in this build; skipping the integrity check"

    try:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        return False, f"Could not read the updater binary: {exc}"

    if not hmac.compare_digest(digest.lower(), expected.strip().lower()):
        return False, (
            f"The updater binary does not match the version shipped with "
            f"QSnippet (expected {expected[:16]}..., found {digest[:16]}...)"
        )

    return True, "Updater integrity verified"


def build_command(main, extra_args: list) -> list | None:
    """
    Build the command line used to invoke the updater.

    Most settings come from config/updater.yaml. Only the values QSnippet
    knows at runtime are passed as flags: the running version, this process
    ID, the executable path, and the log directory, so updater.log lands
    beside QSnippet.log rather than in a separate location the user has to
    hunt for.
    """
    updater = find_updater(main)

    if updater is not None:
        trusted, reason = verify_updater(updater)

        if not trusted:
            logger.error("Refusing to run the updater: %s", reason)
            return None

        logger.debug(reason)
        command = [str(updater)]
    else:
        checkout = find_updater_source()
        if checkout is None:
            logger.warning("No updater binary or source checkout found")
            return None

        logger.debug("Running the updater from source at %s", checkout)
        command = [sys.executable, str(checkout / "updater_main.py")]

    config_file = updater_config_path(main)
    if config_file:
        command += ["--config", str(config_file)]

    version = current_version(main)
    if version:
        command += ["--current-version", version]

    executable = application_executable(main)
    if executable:
        command += ["--executable", str(executable)]
    else:
        command += relaunch_flags(main)

    log_dir = getattr(main, "logs_dir", "")
    if log_dir:
        command += ["--log-file", str(log_dir)]

    log_level = getattr(main, "log_level", "")
    if log_level:
        command += ["--log-level", str(log_level)]

    command += channel_flags(main)

    return command + list(extra_args)


def update_channel(main) -> str:
    """
    Read the user's chosen update channel from Settings.

    Falls back to "main" for any value that is not exactly "dev" - a missing
    settings entry, a stale value, or a typo in a hand-edited settings.yaml
    all resolve to the safe default rather than accidentally opting someone
    into pre-release builds.
    """
    settings = getattr(main, "settings", None) or {}
    updates = settings.get("updates", {}) or {}
    value = updates.get("channel", {}).get("value", "main")

    return "dev" if str(value).strip().lower() == "dev" else "main"


def channel_flags(main) -> list:
    """
    Build the --channel / --tag-pattern flags for the selected update channel.

    Default is Main (channel=stable, tag_pattern="-release$" from
    updater.yaml). Dev clears the tag filter to consider any release, stable
    or pre-release. Both channels resolve to the same trusted repo and
    signing key, so this is a visibility choice, not a trust change.
    """
    if update_channel(main) != "dev":
        return []

    return ["--channel", "any", "--tag-pattern", ""]


def updater_config_path(main) -> Path | None:
    """Locate config/updater.yaml, in the install directory or the source tree."""
    candidates = []

    config_dir = getattr(main, "config_dir", None)
    if config_dir:
        candidates.append(Path(config_dir) / "updater.yaml")

    candidates.append(Path(__file__).resolve().parent.parent / "config" / "updater.yaml")

    for candidate in candidates:
        if candidate.is_file():
            return candidate

    return None


def current_version(main) -> str:
    """
    Return the version QSnippet is currently running.

    The build stamp written by CI is authoritative for a released build,
    because config.yaml can be replaced by an installer while build_info is
    compiled in. The config value is the fallback for a source run.
    """
    try:
        from config import build_info

        stamped = getattr(build_info, "BUILD_VERSION", "")
        if stamped:
            return str(stamped)
    except ImportError:
        pass

    config = getattr(main, "config", {}) or {}
    return str(config.get("version", "") or "")


def application_executable(main) -> Path | None:
    """Return the path of the running QSnippet binary, if it is a frozen build."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable)

    app_exe = getattr(main, "app_exe", None)
    if app_exe and Path(app_exe).is_file():
        return Path(app_exe)

    return None


def relaunch_flags(main) -> list:
    """
    Build the flags that let the updater restart QSnippet from a source checkout.

    --executable covers a frozen build only; a source checkout's app_exe
    points at a QSnippet.exe that doesn't exist under `python QSnippet.py`,
    so without this the updater silently has nothing to relaunch. Builds the
    equivalent of "python QSnippet.py" with the matching working directory.
    Only called when application_executable() found nothing.
    """
    script = Path(__file__).resolve().parent.parent / "QSnippet.py"
    if not script.is_file():
        return []

    flags = ["--relaunch-command", sys.executable, "--relaunch-arg", str(script)]

    working_dir = getattr(main, "working_dir", None)
    if working_dir:
        flags += ["--install-dir", str(working_dir)]

    return flags


class UpdateChecker(QThread):
    """
    Runs "updater --check-only --json" on a background thread.

    Kept off the GUI thread because it makes network calls; the result arrives
    through the `finished_check` signal.
    """

    finished_check = Signal(object)

    def __init__(self, main, parent=None):
        super().__init__(parent)
        self.main = main

    def run(self) -> None:
        """Execute the check and emit an UpdateInfo describing the outcome."""
        try:
            info = self.check()
        except Exception as exc:
            logger.exception("Update check failed unexpectedly")
            info = UpdateInfo(error=f"The update check failed: {exc}")

        self.finished_check.emit(info)

    def check(self) -> UpdateInfo:
        """Run the updater in check-only mode and parse its JSON output."""
        # --no-gui is explicit: this call captures output and must never
        # open a window, even if a brand's ui.gui default were ever true.
        command = build_command(
            self.main, ["--check-only", "--json", "--quiet", "--no-gui"]
        )

        if command is None:
            if is_portable_install(self.main):
                return UpdateInfo(
                    error="Automatic updates are not available in the portable build. "
                          "Download the latest portable zip to update."
                )
            return UpdateInfo(
                error="The updater is unavailable or failed its integrity check."
            )

        logger.info("Checking for updates")
        logger.debug("Update check command: %s", " ".join(command))

        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=CHECK_TIMEOUT_SECONDS,
                creationflags=creation_flags(),
                check=False,
            )
        except subprocess.TimeoutExpired:
            return UpdateInfo(error="The update check timed out")
        except OSError as exc:
            return UpdateInfo(error=f"Could not run the updater: {exc}")

        if result.returncode in (EXIT_UPDATE_AVAILABLE, EXIT_UP_TO_DATE, EXIT_SUCCESS):
            payload = parse_json(result.stdout)

            if payload is None:
                return UpdateInfo(
                    available=result.returncode == EXIT_UPDATE_AVAILABLE,
                    error="The updater returned output that could not be read",
                )

            info = UpdateInfo.from_payload(payload)
            logger.info(
                "Update check complete: %s",
                f"{info.latest_version} available" if info.available else "up to date",
            )
            return info

        message = EXIT_MESSAGES.get(
            result.returncode, f"The updater exited with code {result.returncode}"
        )
        detail = (result.stderr or "").strip().splitlines()
        if detail:
            message = f"{message} {detail[-1]}"

        logger.warning("Update check failed: %s", message)
        return UpdateInfo(error=message)


def parse_json(text: str) -> dict | None:
    """
    Parse the updater JSON payload from its stdout.

    A frozen build can emit stray runtime warnings alongside the JSON, so
    the first JSON object is located rather than parsing the whole stream.
    """
    if not text:
        return None

    try:
        return json.loads(text)
    except ValueError:
        pass

    start = text.find("{")
    end = text.rfind("}")

    if start == -1 or end <= start:
        return None

    try:
        return json.loads(text[start:end + 1])
    except ValueError:
        return None


def creation_flags() -> int:
    """Return process creation flags that keep a console window from flashing."""
    if sys.platform == "win32":
        return subprocess.CREATE_NO_WINDOW
    return 0


def launch_update(main, use_gui: bool = True) -> tuple:
    """
    Hand control to the updater to download and install the update.

    Returns (started, message). On success the updater stops QSnippet,
    installs, and restarts it, so this process should expect to be
    terminated shortly. Launched fully detached: as a child process it
    would be killed along with QSnippet, leaving the install half-finished.
    """
    extra = ["--calling-pid", str(os.getpid())]

    if use_gui:
        extra.append("--gui")

    command = build_command(main, extra)

    if command is None:
        if is_portable_install(main):
            return False, (
                "Automatic updates are not available in the portable build. "
                "Download the latest portable zip from qsnippet.com to update."
            )
        return False, (
            "The updater is unavailable or failed its integrity check. "
            "Reinstall QSnippet to restore it."
        )

    logger.info("Launching the updater to install an update")
    logger.debug("Update command: %s", " ".join(command))

    kwargs = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }

    if sys.platform == "win32":
        kwargs["creationflags"] = (
            subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        )
    else:
        kwargs["start_new_session"] = True

    try:
        subprocess.Popen(command, **kwargs)
    except OSError as exc:
        logger.exception("Could not launch the updater")
        return False, f"Could not start the updater: {exc}"

    return True, "The updater has started. QSnippet will restart when it finishes."

from pathlib import Path
import logging
import shutil

logger = logging.getLogger(__name__)



class LinuxUtils:
    APPLICATION_FILE = Path("/usr/share/applications/qsnippet.desktop")
    AUTOSTART_FILE = Path.home() / ".config/autostart/QSnippet.desktop"

    @staticmethod
    def ensure_autostart_file() -> None:
        """
        Ensure the autostart desktop file exists for the current user.

        Creates the autostart directory if necessary and copies the system
        desktop file into the user's autostart directory if it is missing.

        Returns:
            bool: True if the autostart file exists or was successfully created,
                otherwise False.
        """
        autostart_dir = LinuxUtils.AUTOSTART_FILE.parent
        autostart_dir.mkdir(parents=True, exist_ok=True)

        if LinuxUtils.AUTOSTART_FILE.exists():
            return True

        if not LinuxUtils.APPLICATION_FILE.exists():
            logger.error(
                "System desktop file not found at %s",
                LinuxUtils.APPLICATION_FILE,
            )
            return False

        try:
            shutil.copy(
                LinuxUtils.APPLICATION_FILE,
                LinuxUtils.AUTOSTART_FILE,
            )
            logger.info(
                "Copied desktop file to autostart: %s",
                LinuxUtils.AUTOSTART_FILE,
            )
            return True

        except Exception as e:
            logger.error(
                "Failed to copy autostart desktop file: %s",
                e,
            )
            return False

    @staticmethod
    def enable_autostart() -> None:
        """
        Enable application autostart for the current user on Linux.

        Ensures the autostart desktop file exists and updates or inserts
        the X-GNOME-Autostart-enabled key to true. Also ensures the
        Hidden key is set to false if present.

        Returns:
            None
        """
        if not LinuxUtils.ensure_autostart_file():
            return

        lines = LinuxUtils.AUTOSTART_FILE.read_text(
            encoding="utf-8"
        ).splitlines()

        found = False
        for i, line in enumerate(lines):
            if line.startswith("X-GNOME-Autostart-enabled"):
                lines[i] = "X-GNOME-Autostart-enabled=true"
                found = True

            if line.startswith("Hidden"):
                lines[i] = "Hidden=false"

        if not found:
            lines.append("X-GNOME-Autostart-enabled=true")

        LinuxUtils.AUTOSTART_FILE.write_text(
            "\n".join(lines) + "\n",
            encoding="utf-8",
        )

        logger.info("Enabled Linux autostart for QSnippet")

    @staticmethod
    def disable_autostart() -> None:
        """
        Disable application autostart for the current user on Linux.

        Updates the autostart desktop file to set the
        X-GNOME-Autostart-enabled key to false if the file exists.

        Returns:
            None
        """
        if not LinuxUtils.AUTOSTART_FILE.exists():
            return

        lines = LinuxUtils.AUTOSTART_FILE.read_text(
            encoding="utf-8"
        ).splitlines()

        for i, line in enumerate(lines):
            if line.startswith("X-GNOME-Autostart-enabled"):
                lines[i] = "X-GNOME-Autostart-enabled=false"

        LinuxUtils.AUTOSTART_FILE.write_text(
            "\n".join(lines) + "\n",
            encoding="utf-8",
        )

        logger.info("Disabled Linux autostart for QSnippet")

    @staticmethod
    def is_autostart_enabled() -> bool:
        """
        Check whether Linux autostart is enabled for the application.

        Returns:
            bool: True if the autostart file exists and contains
                X-GNOME-Autostart-enabled=true, otherwise False.
        """
        if not LinuxUtils.AUTOSTART_FILE.exists():
            return False

        content = LinuxUtils.AUTOSTART_FILE.read_text(
            encoding="utf-8"
        )

        return "X-GNOME-Autostart-enabled=true" in content

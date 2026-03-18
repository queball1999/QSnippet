import sys
import os
import logging
from pathlib import Path

# Import utility modules (UI imports moved to __init__ to avoid import errors in test environments)
from utils import FileUtils, SnippetDB, ConfigLoader, SettingsLoader, AppLogger, sys_utils
from utils.lock_utils import LockFile

# Import build info
try:
    from config.build_info import BUILD_VERSION, BUILD_DATE, BUILD_COMMIT
except ImportError:
    BUILD_VERSION = "unknown"
    BUILD_DATE = "unknown"
    BUILD_COMMIT = "unknown"

# Setup logging
logger = logging.getLogger(__name__)

"""
Name: QSnippet

Description: Snippet manager tool.

Author: Written by Quynn Bell
"""

class main():
    def __init__(self) -> None:
        """
        Initialize the main application.

        Performs startup initialization including creating global variables,
        loading configuration and settings, initializing logging, verifying
        system requirements, checking for existing instances, scaling UI
        configuration, optionally displaying notices, and launching the program.

        NOTE: logging is NOT fully initialized until after init_logger

        Returns:
            None
        """
        # Import PySide6 here to avoid import errors in test environments without display
        from PySide6.QtWidgets import QApplication, QMessageBox
        from PySide6.QtCore import QSize, QTimer
        from PySide6.QtGui import QFont, QIcon

        # Import UI modules here (after PySide6 to avoid import errors in test environments)
        from ui.window import QSnippet
        from ui.widgets import AppMessageBox
        from ui.widgets.notice_carousel import NoticeCarouselDialog

        # Store as instance variables for access in other methods
        self.QApplication = QApplication
        self.QMessageBox = QMessageBox
        self.QSize = QSize
        self.QTimer = QTimer
        self.QFont = QFont
        self.QIcon = QIcon
        self.QSnippet = QSnippet
        self.AppMessageBox = AppMessageBox
        self.NoticeCarouselDialog = NoticeCarouselDialog

        self.create_global_variables()
        self.load_config()      # config.yaml
        self.load_settings()    # settings.yaml
        self.init_logger()
        self.fix_image_paths()

        logger.info("Application bootstrap complete")

        self.message_box = self.AppMessageBox(icon_path=self.images["icon"])

        self.check_sys_requirements()  # Check system requirements
        self.check_if_already_running(self.program_name) # Check if application is already running
        self.scale_ui_cfg()

        # Check if we need to show notices
        # Default to True if setting missing
        if self.settings["general"]["startup_behavior"]["show_ui_at_start"].get("value", True):
            # Use time to avoid interfering with main thread
            self.QTimer.singleShot(1000, self.check_notices)

        self.start_program()    # start program
        
    def create_global_variables(self) -> None:
        """
        Initialize global variables and application paths.

        Sets up process metadata, screen geometry references, directory paths,
        file paths, and loads the merged configuration from default and user YAML files.

        Returns:
            None
        """
        self.REQUIRED_IMAGE_FILES = [
            "QSnippet.ico",
            "QSnippet.icns",
        ]

        # Global Configuration Variables
        self.pid = os.getpid()  # Store Process ID of application
        self.app = self.QApplication.instance()  # Use the existing QApplication instance
        self.clipboard = self.app.clipboard()
        self.screen_geometry = self.app.primaryScreen().geometry()
        self.screen_width = self.screen_geometry.width()
        self.screen_height = self.screen_geometry.height()
        self.REFERENCE_WIDTH = 1920
        self.REFERENCE_HEIGHT = 1080
        # Flag to skip loading reg key
        self.skip_reg = False

        # Define Directories
        default_paths = FileUtils.get_default_paths()
        self.working_dir = default_paths["working_dir"]
        self.resource_dir = default_paths["resource_dir"]
        self.default_os_paths = default_paths

        self.config_dir = self.working_dir / "config"
        self.logs_dir = self.default_os_paths["log_dir"]
        self.app_data_dir = self.default_os_paths["app_data"]
        self.images_path = FileUtils.resolve_images_path(self)  # dynamically fetch images directory

        # Ensure directories exist
        sys_utils.ensure_directories_exist([
            self.logs_dir,
            self.app_data_dir,
            self.images_path
        ])

        # Define Files
        self.app_exe = self.working_dir / "QSnippet.exe"
        self.snippet_db_file = self.app_data_dir / "snippets.db"
        self.program_icon = os.path.join(self.images_path, "QSnippet_Icon_v1.png")
        self.log_path = os.path.join(self.logs_dir, "QSnippet.log")

        # Ensure log directory exists before logger tries to write to it
        Path(self.logs_dir).mkdir(parents=True, exist_ok=True)

        # Config and Settings files

        # These are the default config files
        self.default_config_file   = self.config_dir / "config.yaml"
        self.default_settings_file = self.config_dir / "settings.yaml"

        # These are the user config files
        self.config_file   = self.app_data_dir / "config.yaml"
        self.settings_file = self.app_data_dir / "settings.yaml"
        self.license_file  = self.working_dir / "LICENSE"

        # Use this to ensure files exist
        # Define files in a list of dicts with "file" and "function" keys
        sys_utils.ensure_files_exist([
            {
                "file": self.snippet_db_file,
                "function": lambda p=self.snippet_db_file:
                    FileUtils.create_snippets_db_file(p)
            },
            {
                "file": self.config_file,
                "function": lambda p=self.config_file:
                    FileUtils.create_config_file(
                        default_dir=self.config_dir,
                        user_path=p,
                        parent=self
                    )
            },
            {
                "file": self.settings_file,
                "function": lambda p=self.settings_file:
                    FileUtils.create_settings_file(
                        default_dir=self.config_dir,
                        user_path=p,
                        parent=self
                    )
            },
        ])

        # Load and Merge
        self.config = FileUtils.load_and_merge_yaml(
            default_path=self.default_config_file,
            user_path=self.config_file,
        )

        self.settings = FileUtils.load_and_merge_yaml(
            default_path=self.default_settings_file,
            user_path=self.settings_file,
        )
        
        # Initialize Snippet DB instance
        self.snippet_db = SnippetDB(self.snippet_db_file)

        logger.info("Global variables created")
    
    def init_logger(self) -> None:
        """
        Initialize the application logger.

        Creates an AppLogger instance using the configured log file path and
        log level.

        Returns:
            None

        Raises:
            ValueError: If the logger cannot be initialized.
        """
        try:
            logging.info("Setting up Logger")
            self.logger = AppLogger(log_filepath=self.log_path, log_level=self.log_level)
            logging.info("Logger initialized!")
        except Exception as e:
            raise ValueError(f"Could not initialize logger class! Please try running as root and if the issue persists, contact the application vendor.\nError: {e}")

    def flatten_yaml(self, items: dict) -> bool:
        """
        Flatten a nested YAML dictionary into instance attributes.

        Assigns each top-level key in the provided dictionary as an attribute
        on the instance. For nested dictionaries, creates flattened attributes
        by prefixing keys with their parent section name.

        Args:
            items (dict): The dictionary to flatten and assign to attributes.

        Returns:
            bool: True if flattening succeeds, False otherwise.
        """
        try:
            # Assign every top-level config key as an attribute on self
            # e.g. config['program_name'] → self.program_name
            for key, val in items.items():
                setattr(self, key, val)

            # For each nested dict (like colors, images, sizing), flatten its entries
            # by prefixing with the section name:
            # e.g. config['images']['icon'] → self.images_icon
            #      config['colors']['primary_accent_active'] → self.colors_primary_accent_active`
            for section, subdict in items.items():
                if isinstance(subdict, dict):
                    for subkey, subval in subdict.items():
                        attr_name = f"{section}_{subkey}"
                        setattr(self, attr_name, subval)

            return True
        except:
            logger.error("Failed to flatten config")
            return False

    def load_config(self) -> None:
        """
        Load and monitor the configuration YAML file.

        Ensures the configuration file exists, initializes a ConfigLoader to
        watch for changes, and flattens the loaded configuration into instance
        attributes.

        Returns:
            None

        Raises:
            SystemExit: If the configuration file is missing.
        """
        # Check for config
        if not self.config_file.exists():
            self.QMessageBox.critical(None, "Error", f"Missing config: {self.config_file}")
            sys.exit(1)

        # Setup Config file watcher
        self.loader = ConfigLoader(self.config_file, parent=self)
        self.loader.configChanged.connect(self.on_config_updated)
        self.cfg = self.loader.config
        self.flatten_yaml(items=self.cfg)

    def on_config_updated(self, config) -> None:
        """
        Handle updates to the configuration file.

        Refreshes the stored configuration, re-flattens attributes, rescales
        UI configuration, and reapplies styles to the editor when changes are detected.

        Args:
            config (dict): The updated configuration dictionary.

        Returns:
            None
        """
        logger.info("Config reloaded.")

        if config:
            self.cfg = config
            self.flatten_yaml()  # Flatten config again to refresh attributes.
            self.scale_ui_cfg(items=self.cfg) # Refresh UI config and scale
            self.qsnippet.editor.applyStyles()    # Trigger UI update
            self.app.processEvents()
        # Should also fire off UI refresh, etc to ensure the UI matches the config

    def load_settings(self) -> None:
        """
        Load and monitor the settings YAML file.

        Ensures the settings file exists, initializes a SettingsLoader to
        watch for changes, flattens the loaded settings into instance
        attributes, and applies startup registration behavior.

        Returns:
            None

        Raises:
            SystemExit: If the settings file is missing.
        """
        # Check for config
        if not self.settings_file.exists():
            self.QMessageBox.critical(None, "Error", f"Missing settings: {self.settings_file}")
            sys.exit(1)

        # Setup Config file watcher
        self.loader = SettingsLoader(self.settings_file, parent=self)
        self.loader.settingsChanged.connect(self.on_settings_updated)
        self.settings = self.loader.settings
        self.flatten_yaml(items=self.settings)
        self.handle_start_up_reg()

    def on_settings_updated(self, config) -> None:
        """
        Handle updates to the settings file.

        Refreshes the stored settings, re-flattens attributes, and updates
        startup registration behavior when changes are detected.

        Args:
            config (dict): The updated settings dictionary.

        Returns:
            None
        """
        logger.info("Settings reloaded.")

        if config:
            self.settings = config
            self.flatten_yaml(items=self.settings)  # Flatten config again to refresh attributes.
            self.handle_start_up_reg()

    def scale_ui_cfg(self):
        """ 
        Reassigns the size attributes with scaled versions. 
        Needs more work but this will do for now 05/07/25
        """
        # Scale Accordingly
        self.fonts_sizes = self.scale_font_sizes(font_dict=self.fonts_sizes, screen_geometry=self.screen_geometry)
        self.dimensions_buttons = self.scale_dict_sizes(size_dict=self.dimensions_buttons, screen_geometry=self.screen_geometry)
        self.dimensions_windows = self.scale_dict_sizes(size_dict=self.dimensions_windows, screen_geometry=self.screen_geometry)
        
        # Buttons
        self.mini_button_size = self.QSize(self.dimensions_buttons["mini"]["width"], self.dimensions_buttons["mini"]["height"])
        self.small_button_size = self.QSize(self.dimensions_buttons["small"]["width"], self.dimensions_buttons["small"]["height"])
        self.medium_button_size = self.QSize(self.dimensions_buttons["medium"]["width"], self.dimensions_buttons["medium"]["height"])
        self.large_button_size = self.QSize(self.dimensions_buttons["large"]["width"], self.dimensions_buttons["large"]["height"])
        
        # Font Sizes
        self.small_font_size = self.QFont(self.fonts["primary_font"], self.fonts_sizes["small"])
        self.small_font_size_bold = self.QFont(self.fonts["primary_font"], self.fonts_sizes["small"], self.QFont.Bold)
        self.medium_font_size = self.QFont(self.fonts["primary_font"], self.fonts_sizes["medium"])
        self.medium_font_size_bold = self.QFont(self.fonts["primary_font"], self.fonts_sizes["medium"], self.QFont.Bold)
        self.large_font_size = self.QFont(self.fonts["primary_font"], self.fonts_sizes["large"])
        self.large_font_size_bold = self.QFont(self.fonts["primary_font"], self.fonts_sizes["large"], self.QFont.Bold)
        self.extra_large_font_size = self.QFont(self.fonts["primary_font"], self.fonts_sizes["extra_large"])
        self.extra_large_font_size_bold = self.QFont(self.fonts["primary_font"], self.fonts_sizes["extra_large"], self.QFont.Bold)
        self.humongous_font_size = self.QFont(self.fonts["primary_font"], self.fonts_sizes["humongous"])
        self.humongous_font_size_bold = self.QFont(self.fonts["primary_font"], self.fonts_sizes["humongous"], self.QFont.Bold)

        # Widget Sizes
        self.small_toggle_size = self.QSize(self.dimensions_toggles["small"]["width"], self.dimensions_toggles["small"]["height"])        

    def fix_image_paths(self) -> None:
        """
        Update image paths to use the resolved images directory.

        Prefixes configured image filenames with the absolute images path.

        Returns:
            None
        """
        for image in self.images:
            old_val = self.images[image]
            self.images[image] = os.path.join(self.images_path, old_val)
            
        logger.debug(f"Images Path: {self.images_path}")

    def scale_width(self, original_width, screen_geometry) -> int:
        """
        Scale a width value relative to the reference screen width.

        Args:
            original_width (int): The original width based on the reference resolution.
            screen_geometry (Any): The current screen geometry object.

        Returns:
            int: The scaled width value.
        """
        ratio = screen_geometry.width() / self.REFERENCE_WIDTH
        return int(original_width * ratio)

    def scale_height(self, original_height, screen_geometry):
        """
        Scale a height value relative to the reference screen height.

        Args:
            original_height (int): The original height based on the reference resolution.
            screen_geometry (Any): The current screen geometry object.

        Returns:
            int: The scaled height value.
        """
        ratio = screen_geometry.height() / self.REFERENCE_HEIGHT
        return int(original_height * ratio)
    
    def scale_dict_sizes(self, size_dict: dict, screen_geometry):
        """
        Scale a dictionary of size specifications to the current screen.

        Each entry containing width, height, and optional radius values
        is proportionally scaled according to the screen geometry.

        Args:
            size_dict (dict): Dictionary of size specifications.
            screen_geometry (Any): The current screen geometry object.

        Returns:
            dict: A new dictionary with scaled size values.
        """
        w_ratio = screen_geometry.width() / self.REFERENCE_WIDTH
        h_ratio = screen_geometry.height() / self.REFERENCE_HEIGHT
        r_ratio = min(w_ratio, h_ratio)
        
        scaled_size_dict = {}
        for name, dims in size_dict.items():
            scaled_size_dict[name] = {
                "width":  self.scale_width(dims["width"],  screen_geometry),
                "height": self.scale_height(dims["height"], screen_geometry),
                "radius": int(dims.get("radius", 0) * r_ratio)
            }
        return scaled_size_dict
    
    def scale_font_sizes(self, font_dict: dict, screen_geometry):
        """
        Scale font sizes relative to the current screen height.

        Args:
            font_dict (dict): Dictionary mapping font size labels to integer values.
            screen_geometry (Any): The current screen geometry object.

        Returns:
            dict: A new dictionary with scaled font sizes.
        """
        # scale fonts by the ratio of current screen height to reference height
        ratio = screen_geometry.height() / self.REFERENCE_HEIGHT

        return {
            name: int(size * ratio)
            for name, size in font_dict.items()
        }

    def handle_start_up_reg(self):
        """ Based on settings, set the correct registry key for startup """
        if sys.platform == "win32":
            from utils.reg_utils import RegUtils

            if (
                not RegUtils.is_in_run_key("QSnippet") and 
                self.settings["general"]["startup_behavior"]["start_at_boot"]["value"]
                ):  # If auto-start missing and setting is true, enable auto-start
                RegUtils.add_to_run_key(app_exe_path=self.app_exe, entry_name="QSnippet")
            elif (
                RegUtils.is_in_run_key("QSnippet") and 
                not self.settings["general"]["startup_behavior"]["start_at_boot"]["value"]
                ):  # If auto-start exists and setting is false, disable auto-start
                RegUtils.remove_from_run_key(entry_name="QSnippet")

        elif sys.platform.startswith("linux"):
            from utils.linux_utils import LinuxUtils

            if (
                not LinuxUtils.is_autostart_enabled() and 
                self.settings["general"]["startup_behavior"]["start_at_boot"]["value"]
                ):  # If auto-start missing and setting is true, enable auto-start
                LinuxUtils.enable_autostart()
            elif (
                LinuxUtils.is_autostart_enabled() and 
                not self.settings["general"]["startup_behavior"]["start_at_boot"]["value"]
                ):  # If auto-start exists and setting is false, disable auto-start
                LinuxUtils.disable_autostart()
                
    def check_if_already_running(self, app_name="QSnippet") -> bool:
        """
        Check whether another instance of the application is already running.

        Uses kernel-enforced locking for atomic, cross-platform single instance detection:
        - Windows: Named mutex via CreateMutex (kernel-enforced, atomic)
        - Linux/macOS: fcntl.flock() (kernel-enforced, atomic, auto-released on crash)

        Args:
            app_name (str): Name of the application used for single instance detection.

        Returns:
            bool: True if startup can continue, otherwise exits the process.

        Raises:
            SystemExit: If another running instance is detected.
        """
        if sys.platform == "win32":
            lock_id = f"Local\\{app_name}.Lock"
        else:
            lock_id = str(self.app_data_dir / f".{app_name}.lock")

        logger.debug("Checking single-instance lock: %s", lock_id)

        try:
            # Moving to new lock_utils with better cross-platform support and automatic cleanup on crashes
            self.lock_file = LockFile(lock_id)
            if self.lock_file.try_acquire():
                self.app.aboutToQuit.connect(self.lock_file.release)
                logger.debug("Single-instance lock acquired successfully")
                return True

            logger.warning("Another instance detected. Exiting.")
            self.message_box.info(
                f"Another instance of '{app_name}' is already running.\nPlease check the task tray for the app icon.",
                title="Already Running"
            )
            sys.exit(1)
        except Exception as e:
            logger.exception("Single-instance check failed: %s", e)
            raise RuntimeError(f"Failed to initialize single-instance lock: {e}") from e
    
    def check_sys_requirements(self):
        """
        Validate system compatibility and required dependencies.

        Checks the operating system and verifies required packages on
        supported platforms. Displays an error message and exits if
        requirements are not satisfied or the OS is unsupported.

        Returns:
            None

        Raises:
            SystemExit: If system requirements are not met or the OS is unsupported.
        """
        package_manager = sys_utils.detect_package_manager()
        requirements = {
            "libxcb-cursor": {
                "library": "libxcb-cursor",
                "install_hint": f"sudo {package_manager} install libxcb-cursor0"
            },
            "xclip": {
                "library": "xclip",
                "install_hint": f"sudo {package_manager} install xclip"
            }
        }
        
        logger.info("Checking system requirements")

        if sys.platform == "win32":
            sys_details = f"Windows OS detected: {sys.platform}, Python {sys.version}"
            logger.info(sys_details)
            logger.debug("No additional system requirements for Windows.")

        elif sys.platform.startswith("linux"):
            sys_details = f"Linux OS detected: {sys.platform}, Python {sys.version}"
            logger.info(sys_details)

            try:
                missing_packages = sys_utils.check_required_packages(requirements)
                logger.debug(f"Missing packages: {missing_packages}")

                # If anything missing, show user friendly error
                if missing_packages:
                    install_lines = "\n".join(
                        f"• {pkg}: {hint}" for pkg, hint in missing_packages
                    )

                    message = (
                        "The following required dependencies are missing:\n\n"
                        f"{install_lines}\n\n"
                        "Please install them using your package manager and restart the application."
                    )

                    self.message_box.error(
                        message,
                        title="System Requirement Error"
                    )

                    sys.exit(1)
            except OSError:
                self.message_box.error(
                    "An error occured while performing system check. If the issue persists, please contact the application vendor.",
                    title="Application Error"
                )
                sys.exit(1)
            
        elif sys.platform == "darwin":
            sys_details = f"macOS detected: {sys.platform}, Python {sys.version}"
            logger.warning(sys_details)
            self.message_box.error(
                "macOS is not currently supported. This application supports Windows and Linux only.",
                title="System Requirement Error"
            )
            sys.exit(1)

        else:
            sys_details = f"Unsupported OS detected: {sys.platform}, Python {sys.version}"
            logger.warning(sys_details)
            self.message_box.critical(
                f"Unsupported operating system: {sys.platform}. This application supports Windows and Linux only.",
                title="System Requirement Error"
            )
            sys.exit(1)

        logger.info("System requirements check complete")

    def check_notices(self):
        """
        Load and display unread application notices.

        Reads notice settings, determines unread notices, displays them
        in a dialog, and persists any dismissals or user preferences.

        Returns:
            None
        """
        logger.debug("Checking for unread notices")

        notices = self.settings.setdefault("notices", {})

        # Read values safely
        disable_notices = (
            notices.get("disable_notices", {}).get("value", False)
        )
        dismissed = set(
            notices.get("dismissed_notices", {}).get("value", [])
        )

        if disable_notices:
            logger.info("Notices disabled by user")
            return

        notices_dir = Path(self.working_dir) / "notices"
        notices_dir.mkdir(exist_ok=True)

        unread = self.NoticeCarouselDialog.load_notices(
            notices_dir,
            dismissed
        )

        # Exit if no unread notices to display
        if not unread:
            logger.debug("No unread notices found")
            return

        logger.info("Displaying %d notices", len(unread))

        dialog = self.NoticeCarouselDialog(
            unread,
            icon_path=self.QIcon(self.images["icon"]),
            parent=self,
        )
        dialog.exec()

        # Persist dismissals
        for notice in unread:
            dismissed.add(notice["id"])

        # Update dismissed_notices.value
        if "dismissed_notices" in notices:
            notices["dismissed_notices"]["value"] = list(dismissed)
        else:
            notices["dismissed_notices"] = {
                "type": "list",
                "value": list(dismissed),
                "description": "List of notices that have been dismissed by the user.",
            }

        # Update disable_notices.value if user opted out
        if dialog.disable_future:
            if "disable_notices" in notices:
                notices["disable_notices"]["value"] = True
            else:
                notices["disable_notices"] = {
                    "type": "bool",
                    "value": True,
                    "description": "Disable all in-app notices and notifications.",
                }

            logger.info("User disabled future notices")

        FileUtils.write_yaml(self.settings_file, self.settings)
        logger.debug("Finished checking notices")

    def start_program(self):
        """
        Create and launch the main application window.

        Initializes the QSnippet UI, logs build information, and starts
        the main application interface.

        Returns:
            None
        """
        program_name = self.program_name if hasattr(self, "program_name") else "QSnippet"
        logger.info(f"Starting {program_name} UI")
        logger.info(
            "%s %s built %s (commit %s)",
            program_name,
            BUILD_VERSION,
            BUILD_DATE,
            BUILD_COMMIT,
        )
        self.qsnippet = self.QSnippet(parent=self)
        self.qsnippet.run()


if __name__ == '__main__':
    from PySide6.QtWidgets import QApplication, QMessageBox
    from PySide6.QtGui import QIcon

    app = QApplication(sys.argv)
    try:
        ex = main()
        sys.exit(ex.app.exec())
    except Exception as e:
        # Leaving as built-in QMessageBox to ensure it shows
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Critical)
        msg.setWindowIcon(QIcon("images/QSnippet.ico")) # fallback location
        msg.setWindowTitle("Fatal Error")
        msg.setText(f"A fatal error was encountered. Please contact the app administrator.\nError: {str(e)}")
        msg.exec()
        sys.exit(1)

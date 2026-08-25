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

# Delay before the quiet startup update check's network call, so it does not
# race notices/tutorial/theme settling in the same startup batch.
STARTUP_UPDATE_CHECK_DELAY_MS = 5000

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
        self.start_accent_color_monitor()

        # Startup dialogs (notices, then the first-run tutorial) only make
        # sense when the window is actually on screen.
        # Default to True if setting missing
        if self.settings["general"]["startup_behavior"]["show_ui_at_start"].get("value", True):
            # Use time to avoid interfering with main thread
            self.QTimer.singleShot(1000, self.run_startup_dialogs)

        self.start_program()    # start program
        
    def create_global_variables(self) -> None:
        """
        Initialize global variables and application paths.

        Sets up process metadata, screen geometry references, directory paths,
        file paths, and loads the merged configuration from default and user YAML files.

        Returns:
            None
        """
        self.REQUIRED_IMAGE_FILES = []

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

        # Is this a dev build?
        self.is_dev_build = "dev" in BUILD_VERSION

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

        # Ensure config and settings files exist first (DB deferred until settings are loaded)
        sys_utils.ensure_files_exist([
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

        # Resolve the snippet DB path: use custom directory from settings if set,
        # otherwise fall back to the default app data directory.
        custom_db_dir = (
            self.settings.get("saving", {})
            .get("db_path", {})
            .get("value", "")
            or ""
        ).strip()
        
        if custom_db_dir:
            self.snippet_db_file = Path(custom_db_dir) / "snippets.db"
            Path(custom_db_dir).mkdir(parents=True, exist_ok=True)
        else:
            self.snippet_db_file = self.app_data_dir / "snippets.db"

        # Ensure the DB file exists at the resolved path
        sys_utils.ensure_files_exist([
            {
                "file": self.snippet_db_file,
                "function": lambda p=self.snippet_db_file:
                    FileUtils.create_snippets_db_file(p)
            },
        ])

        # Initialize Snippet DB instance
        self.snippet_db = SnippetDB(self.snippet_db_file)

        if self.snippet_db.was_freshly_created:
            self.clear_vault_crypto_from_config()

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
        self.populate_available_fonts()
        self.handle_start_up_reg()

    def populate_available_fonts(self) -> None:
        """
        Populate the available system fonts in the font_family setting.

        Detects all available system fonts and adds them as options to the
        font_family setting in appearance.advanced.
        """
        try:
            available_fonts = FileUtils.get_system_fonts()

            # Add options to the font_family setting
            if "appearance" in self.settings and "advanced" in self.settings["appearance"]:
                if "font_family" in self.settings["appearance"]["advanced"]:
                    self.settings["appearance"]["advanced"]["font_family"]["options"] = available_fonts
                    logger.debug(f"Populated {len(available_fonts)} system fonts")
        except Exception as e:
            logger.warning(f"Could not populate system fonts: {e}")

    def on_settings_updated(self, config) -> None:
        """
        Handle updates to the settings file.

        Refreshes the stored settings, re-flattens attributes, updates
        startup registration behavior, and reapplies the current theme and
        UI scale.

        Args:
            config (dict): The updated settings dictionary.

        Returns:
            None
        """
        logger.info("Settings reloaded.")

        if config:
            self.settings = config
            self.flatten_yaml(items=self.settings)
            self.handle_start_up_reg()
            self.scale_ui_cfg()  # recomputes fonts and reapplies theme/scale

    def scale_ui_cfg(self):
        """
        Recompute all scaled UI attributes from the original settings values.

        Safe to call multiple times - always reads from the unscaled originals
        stored in settings so that repeated calls (e.g. after a settings change)
        do not compound the scaling.
        """
        # --- resolve user-configured scale (default 100 %) ---
        appearance = self.settings.get("appearance", {})
        ui_scale_val = appearance.get("ui_scale", {})
        if isinstance(ui_scale_val, dict):
            ui_scale_val = ui_scale_val.get("value", "100")
        user_scale = max(0.5, int(ui_scale_val) / 100.0)

        # --- screen ratio (height vs reference 1080 p) ---
        screen_ratio = self.screen_geometry.height() / self.REFERENCE_HEIGHT
        total_font_scale = screen_ratio * user_scale

        # --- read fonts and button sizes from settings (advanced appearance) ---
        advanced = appearance.get("advanced", {})

        # Font family
        pf = advanced.get("font_family", {})
        if isinstance(pf, dict):
            pf = pf.get("value", "Inter")

        # Font sizes - always from original settings, never from a previous call
        font_sizes_setting = advanced.get("font_sizes", {})
        orig_font_sizes = {}
        for size_name in ["small", "medium", "large", "extra_large", "humongous"]:
            size_dict = font_sizes_setting.get(size_name, {})
            if isinstance(size_dict, dict):
                orig_font_sizes[size_name] = size_dict.get("value", 12)
            else:
                orig_font_sizes[size_name] = 12

        self.fonts_sizes = {
            name: max(6, round(size * total_font_scale))
            for name, size in orig_font_sizes.items()
        }

        # Button padding from settings (raw, unscaled - theme manager scales via QSS)
        button_padding_setting = advanced.get("button_padding", {})
        bpx_dict = button_padding_setting.get("x", {})
        bpy_dict = button_padding_setting.get("y", {})
        self.button_padding_x_raw = bpx_dict.get("value", 8) if isinstance(bpx_dict, dict) else 8
        self.button_padding_y_raw = bpy_dict.get("value", 6) if isinstance(bpy_dict, dict) else 6

        # Toggle sizes - always from original settings
        toggle_sizes_setting = advanced.get("toggle_sizes", {})
        orig_toggle_sizes = {}
        for toggle_type in ["small"]:
            toggle_dict = toggle_sizes_setting.get(toggle_type, {})
            if isinstance(toggle_dict, dict):
                orig_toggle_sizes[toggle_type] = {
                    "width": toggle_dict.get("width", {}).get("value", 60) if isinstance(toggle_dict.get("width"), dict) else 60,
                    "height": toggle_dict.get("height", {}).get("value", 45) if isinstance(toggle_dict.get("height"), dict) else 45,
                }
            else:
                orig_toggle_sizes[toggle_type] = {"width": 60, "height": 45}

        # Scale toggle sizes
        self.dimensions_toggles = self.scale_dict_sizes(
            size_dict=orig_toggle_sizes, screen_geometry=self.screen_geometry
        )

        # Window dimensions (from settings.advanced, scaled by screen ratio)
        window_sizes_setting = advanced.get("window_sizes", {})
        orig_window_sizes = {}
        for window_type in ["main"]:
            window_dict = window_sizes_setting.get(window_type, {})
            if isinstance(window_dict, dict):
                orig_window_sizes[window_type] = {
                    "width": window_dict.get("width", {}).get("value", 1200) if isinstance(window_dict.get("width"), dict) else 1200,
                    "height": window_dict.get("height", {}).get("value", 800) if isinstance(window_dict.get("height"), dict) else 800,
                }
            else:
                orig_window_sizes[window_type] = {"width": 1200, "height": 800}

        self.dimensions_windows = self.scale_dict_sizes(
            size_dict=orig_window_sizes, screen_geometry=self.screen_geometry
        )

        # QSize object for toggle
        self.small_toggle_size  = self.QSize(self.dimensions_toggles["small"]["width"],  self.dimensions_toggles["small"]["height"])

        # QFont objects (user-scale applied on top of screen scale)
        self.small_font_size           = self.QFont(pf, self.fonts_sizes["small"])
        self.small_font_size_bold      = self.QFont(pf, self.fonts_sizes["small"],       self.QFont.Bold)
        self.medium_font_size          = self.QFont(pf, self.fonts_sizes["medium"])
        self.medium_font_size_bold     = self.QFont(pf, self.fonts_sizes["medium"],      self.QFont.Bold)
        self.large_font_size           = self.QFont(pf, self.fonts_sizes["large"])
        self.large_font_size_bold      = self.QFont(pf, self.fonts_sizes["large"],       self.QFont.Bold)
        self.extra_large_font_size     = self.QFont(pf, self.fonts_sizes["extra_large"])
        self.extra_large_font_size_bold= self.QFont(pf, self.fonts_sizes["extra_large"], self.QFont.Bold)
        self.humongous_font_size       = self.QFont(pf, self.fonts_sizes["humongous"])
        self.humongous_font_size_bold  = self.QFont(pf, self.fonts_sizes["humongous"],   self.QFont.Bold)

        # Apply theme + scale to QApplication stylesheet
        self.apply_theme()

    def apply_fonts_to_all_widgets(self) -> None:
        """
        Blanket font sweep across every top-level widget tree.

        Sizing is role-aware: ThemeManager.apply_fonts picks each widget's
        font from OBJECT_NAME_FONTS, falling back to the medium font. This is
        phase 2 of ThemeManager.force_repaint and must run before the
        per-widget applyStyles() hooks (phase 3), which layer on the remaining
        overrides that object names alone cannot express.
        """
        try:
            from ui.theme_manager import ThemeManager

            # Set the app-level font so widgets that rely on inheritance
            # (status bar, group box titles, tab bars, etc.) also pick up
            # the new font family even though we don't walk their trees explicitly.
            self.app.setFont(self.medium_font_size)

            for top in self.app.topLevelWidgets():
                ThemeManager.apply_fonts(top)

        except Exception as e:
            logger.debug(f"Error applying fonts to all widgets: {e}")

    def start_accent_color_monitor(self) -> None:
        """Start a timer to monitor system accent color changes."""
        # Only monitor if theme is "system" or accent is "system"
        appearance = self.settings.get("appearance", {})
        theme_val = appearance.get("theme", {})
        if isinstance(theme_val, dict):
            theme_val = theme_val.get("value", "system")

        accent_val = appearance.get("accent_color", {})
        if isinstance(accent_val, dict):
            accent_val = accent_val.get("value", "system")

        # Only monitor if using system theme/accent
        if theme_val == "system" or accent_val == "system":
            self.last_accent_color = None
            timer = self.QTimer()
            timer.timeout.connect(self.check_accent_color_changed)
            timer.start(2000)  # Check every 2 seconds
            self.accent_color_monitor = timer
            logger.debug("System accent color monitor started")

    def check_accent_color_changed(self) -> None:
        """Check if system accent color has changed and reapply theme if it has."""
        from ui.theme_manager import ThemeManager

        # Only check if we have a theme manager
        if not hasattr(self, "theme_manager") or self.theme_manager is None:
            return

        # Get current system accent color
        tm = self.theme_manager
        is_dark = tm.is_dark
        current_accent = tm.get_system_accent(is_dark)

        # If color changed, reapply theme
        if self.last_accent_color is not None and current_accent != self.last_accent_color:
            logger.info(f"System accent color changed from {self.last_accent_color} to {current_accent}")
            self.apply_theme()

        self.last_accent_color = current_accent

    def apply_theme(self) -> None:
        """Create (or reuse) the ThemeManager and apply the current theme + scale."""
        from ui.theme_manager import ThemeManager

        appearance = self.settings.get("appearance", {})

        def val(key, default):
            v = appearance.get(key, {})
            return v.get("value", default) if isinstance(v, dict) else default

        theme_val  = val("theme",        "system")
        scale_pct  = max(50, int(val("ui_scale",     100)))
        accent_col = val("accent_color", "system")

        if not hasattr(self, "theme_manager") or self.theme_manager is None:
            # `main=self` is what every widget uses to reach the scaled QFont
            # attributes (see ThemeManager.app_instance / ThemeManager.font).
            self.theme_manager = ThemeManager(self.app, main=self)
        else:
            self.theme_manager.main = self

        resolved  = self.theme_manager.resolve_theme(theme_val)
        prev_theme = self.theme_manager.theme_name  # theme from the last apply()

        if resolved not in ("dark", "light"):
            # Pink / Nord: always use their own built-in accent
            accent_col = "system"
        elif theme_val == "system" or (prev_theme not in ("dark", "light") and prev_theme):
            # "System" theme explicitly selected, or switching back from pink/nord:
            # revert accent to system color and persist the change.
            accent_col = "system"
            acc_node = appearance.get("accent_color")
            if isinstance(acc_node, dict) and acc_node.get("value") != "system":
                acc_node["value"] = "system"
                from utils import FileUtils
                FileUtils.write_yaml(self.settings_file, self.settings)

        btn_pad_x = getattr(self, 'button_padding_x_raw', 8)
        btn_pad_y = getattr(self, 'button_padding_y_raw', 6)
        self.theme_manager.apply(theme_val, scale_pct, accent_col, btn_pad_x, btn_pad_y)

    def fix_image_paths(self) -> None:
        """
        Resolve all image/icon asset paths with intelligent fallback.

        Resolution strategy for icons (assets/icons/):
        1. External assets/icons/ folder (development priority)
        2. Bundled resources (PyInstaller) - only if external missing AND in PyInstaller

        Resolution strategy for images (assets/images/):
        1. External assets/images/ folder (development priority)
        2. Bundled resources (PyInstaller) - only if external missing AND in PyInstaller

        For development mode (not in PyInstaller): raises error if critical assets missing
        to prevent runaway app with missing tray icon.

        Uses OS-specific icon format (*.ico on Windows, *.icns on macOS/Linux).

        Returns:
            None

        Raises:
            SystemExit: If in development and required assets cannot be resolved.
        """
        icon_names = {"QSnippet.ico", "QSnippet.icns"}
        icon_prefixes = ("icon_",)
        critical_assets = {"icon"}

        logger.info("Resolving image/icon asset paths")

        # Work on a private copy. self.images started out as the *same* dict
        # object as self.cfg["images"], and self.cfg gets written back to
        # config.yaml verbatim elsewhere (e.g. handle_log_level, vault settings
        # saves). Resolving in place would leak absolute, run-specific paths
        # (including PyInstaller's ephemeral _MEI* temp dir) into the persisted
        # config, permanently overwriting the real filenames on disk.
        self.images = dict(self.images)

        # Get the resolved images path (already determined during init)
        images_path = self.images_path
        icons_path = images_path.parent / "icons"  # assets/icons/

        missing_critical = []

        for image_key in self.images:
            old_val = self.images[image_key]

            # Nothing configured (or already-corrupted empty value) - treat as missing
            # rather than resolving os.path.join(dir, "") down to the bare directory.
            if not old_val:
                logger.warning(f"Asset '{image_key}' has no configured filename; treating as missing")
                if image_key in critical_assets:
                    missing_critical.append((image_key, old_val, "assets/icons"))
                self.images[image_key] = ""
                continue

            # Handle generic "QSnippet" icon name with OS-specific resolution
            if old_val == "QSnippet":
                old_val = FileUtils.get_os_specific_icon()
                logger.debug(f"Resolved generic 'QSnippet' icon to OS-specific: {old_val}")

            # Determine if this is an icon file
            is_icon = (old_val in icon_names or
                      any(old_val.startswith(prefix) for prefix in icon_prefixes))

            # Build the primary path based on asset type
            if is_icon:
                primary_path = os.path.join(str(icons_path), old_val)
            else:
                primary_path = os.path.join(str(images_path), old_val)

            # Try primary path first (external development assets).
            # isfile (not exists) so a bare directory is never mistaken for a resolved asset.
            if os.path.isfile(primary_path):
                logger.info(f"Asset '{image_key}' ({old_val}) resolved to: {primary_path}")
                self.images[image_key] = primary_path
            else:
                # Only try fallback if in PyInstaller environment
                if FileUtils.is_running_in_pyinstaller():
                    asset_dir = "icons" if is_icon else "images"
                    fallback_path = FileUtils.resolve_asset_with_fallback(old_val, asset_dir=asset_dir)
                    if fallback_path:
                        logger.info(f"Asset '{image_key}' ({old_val}) resolved to bundled: {fallback_path}")
                        self.images[image_key] = fallback_path
                    else:
                        logger.warning(f"Asset '{image_key}' ({old_val}) not found in primary or bundled")
                        self.images[image_key] = ""
                else:
                    # In development, fail loudly on missing critical assets
                    asset_type = "icon" if is_icon else "image"
                    asset_dir = "assets/icons" if is_icon else "assets/images"
                    logger.warning(f"Asset '{image_key}' ({old_val}) not found at: {primary_path}")
                    if image_key in critical_assets:
                        logger.error(f"Critical {asset_type} '{image_key}' missing in development mode")
                        missing_critical.append((image_key, old_val, asset_dir))
                    self.images[image_key] = ""

        # In development mode, fail loudly if critical assets are missing
        # (prevents runaway app with no tray icon in taskbar)
        if missing_critical:
            msg = (
                "Critical application assets are missing.\n\n"
                "The following required files could not be found:\n"
            )
            for key, filename, asset_dir in missing_critical:
                msg += f"  • {key}: {asset_dir}/{filename}\n"
            msg += (
                "\nMake sure the assets/ directory structure exists in the project root "
                "with all required files."
            )
            logger.critical(msg)
            self.QMessageBox.critical(None, "Missing Assets Error", msg)
            sys.exit(1)

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

    def run_startup_dialogs(self):
        """
        Run the post-launch dialogs in order.

        Unread notices are modal, so the first-run tutorial only starts
        once they have been dismissed; otherwise the tour would spotlight
        a window sitting behind a dialog.

        Returns:
            None
        """
        try:
            self.check_notices()
        except Exception:
            logger.exception("Failed while checking notices")

        try:
            self.qsnippet.maybe_show_tutorial()
        except Exception:
            logger.exception("Failed while starting the first-run tutorial")

        try:
            self.check_for_updates_preflight()
        except Exception:
            logger.exception("Failed while checking for updates on startup")

    def check_for_updates_preflight(self):
        """
        Decide whether a startup update check should run, and schedule it.

        Eligibility (opted out, checked too recently) is checked immediately;
        the network call itself is deferred by STARTUP_UPDATE_CHECK_DELAY_MS.

        Returns:
            None
        """
        updates = self.settings.setdefault("updates", {})

        enabled = updates.get("check_on_startup", {}).get("value", True)
        if not enabled:
            logger.debug("Startup update check disabled by user")
            return

        interval_hours = updates.get("check_interval_hours", {}).get("value", 24)
        if not self.update_check_is_due(updates, interval_hours):
            logger.debug("Startup update check skipped; checked recently")
            return

        logger.debug(
            "Startup update check eligible; starting it in %d ms",
            STARTUP_UPDATE_CHECK_DELAY_MS,
        )
        self.QTimer.singleShot(
            STARTUP_UPDATE_CHECK_DELAY_MS, self.start_startup_update_check
        )

    def start_startup_update_check(self):
        """
        Actually start the background update check and show status feedback.

        Split out so the network call runs after STARTUP_UPDATE_CHECK_DELAY_MS,
        not in the same startup batch as notices and the tutorial.

        Returns:
            None
        """
        from utils.update_utils import UpdateChecker

        logger.debug("Running startup update check")

        # self is the plain "main" bootstrap object, not a QObject, so it
        # can't be the Qt parent; self.qsnippet (the QMainWindow) is used
        # instead and always exists by this point.
        self.startup_update_checker = UpdateChecker(self, parent=self.qsnippet)
        self.startup_update_checker.finished_check.connect(
            self.handle_startup_update_result
        )
        self.startup_update_checker.start()

        try:
            self.qsnippet.statusBar().showMessage("Checking for updates...", 15000)
        except Exception:
            logger.debug("Could not show the startup update-check status message")

    def update_check_is_due(self, updates, interval_hours):
        """
        Decide whether enough time has passed since the last update check.

        Args:
            updates (dict): The "updates" settings section.
            interval_hours (int): Minimum hours between checks.

        Returns:
            bool: True when a check should run now.
        """
        from datetime import datetime, timedelta, timezone

        if interval_hours <= 0:
            return True

        last = updates.get("last_check", {}).get("value", "")
        if not last:
            return True

        try:
            previous = datetime.fromisoformat(str(last))
        except ValueError:
            return True

        if previous.tzinfo is None:
            previous = previous.replace(tzinfo=timezone.utc)

        return datetime.now(timezone.utc) - previous >= timedelta(hours=interval_hours)

    def handle_startup_update_result(self, info):
        """
        Handle the result of the quiet startup update check.

        A failed check is logged and otherwise ignored: the user did not ask
        for this, so an error dialog on launch because the network was down
        would be pure noise.

        Args:
            info (UpdateInfo): The parsed result of the check.

        Returns:
            None
        """
        self.record_update_check_time()

        try:
            status_bar = self.qsnippet.statusBar()
        except Exception:
            status_bar = None

        if not info.ok:
            logger.info("Startup update check did not complete: %s", info.error)
            if status_bar:
                status_bar.clearMessage()
            return

        if not info.available:
            logger.debug("Startup update check: already up to date")
            if status_bar:
                status_bar.showMessage("QSnippet is up to date", 4000)
            return

        logger.info("Update available: %s", info.latest_version)

        if status_bar:
            status_bar.showMessage(f"QSnippet {info.latest_version} is available", 8000)

        try:
            self.qsnippet.prompt_for_update(info)
        except Exception:
            logger.exception("Failed to show the update notice")

    def record_update_check_time(self):
        """
        Persist the time of the most recent update check.

        Returns:
            None
        """
        from datetime import datetime, timezone

        updates = self.settings.setdefault("updates", {})

        stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")

        if "last_check" in updates:
            updates["last_check"]["value"] = stamp
        else:
            updates["last_check"] = {
                "type": "string",
                "value": stamp,
                "description": "Timestamp of the last check for application updates.",
            }

        try:
            FileUtils.write_yaml(self.settings_file, self.settings)
        except Exception:
            logger.exception("Could not record the update check time")

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

    def show_release_history(self) -> None:
        """
        Help menu action: browse every past release notice.

        Unlike check_notices, this ignores dismissed state and never
        marks anything as read - it's a read-only viewer over the full
        notice archive (active and history/ alike).

        Returns:
            None
        """
        notices_dir = Path(self.working_dir) / "notices"
        notices_dir.mkdir(exist_ok=True)

        history = self.NoticeCarouselDialog.load_release_history(notices_dir)

        if not history:
            logger.debug("No release history to display")
            return

        dialog = self.NoticeCarouselDialog(
            history,
            icon_path=self.QIcon(self.images["icon"]),
            parent=self,
            window_title="Release History",
            header_text="QSnippet release history",
            dismissible=False,
        )
        dialog.exec()

    def clear_vault_crypto_from_config(self) -> None:
        """Clear vault cryptographic material after a fresh DB creation.

        When the snippets database is recreated from scratch, any vault secrets
        stored in config.yaml (salt, HMAC, wrapped recovery key) are orphaned -
        they reference data that no longer exists.  This method removes those
        keys so the vault is treated as unconfigured while preserving user
        preferences (auto_lock_minutes, unlock_on_launch).
        """
        try:
            vault_cfg = self.config.get("vault", {})
            # These must match the keys VaultManager.setup actually writes.
            # They previously named "hmac" and "rec_wrapped_key", which do not
            # exist, so a fresh database dropped the salt but left the verifier
            # and recovery material behind as orphaned crypto.
            crypto_keys = (
                "configured", "salt", "verifier",
                "rec_salt", "rec_verifier", "rec_key_blob",
            )
            if any(vault_cfg.get(k) for k in crypto_keys):
                for k in crypto_keys:
                    vault_cfg.pop(k, None)
                self.config["vault"] = vault_cfg
                FileUtils.write_yaml(self.config_file, self.config)
                logger.warning("Fresh DB detected. Cleared orphaned vault crypto material from config")
        except Exception:
            logger.exception("Failed to clear vault crypto from config after fresh DB creation")

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
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Critical)
        try:
            from utils.file_utils import FileUtils
            icon_name = FileUtils.get_os_specific_icon()
            icon_path = FileUtils.resolve_asset_with_fallback(icon_name, asset_dir="images")
            if icon_path:
                msg.setWindowIcon(QIcon(icon_path))
        except Exception:
            pass
        msg.setWindowTitle("Fatal Error")
        msg.setText(f"A fatal error was encountered. Please contact the app administrator.\nError: {str(e)}")
        msg.exec()
        sys.exit(1)

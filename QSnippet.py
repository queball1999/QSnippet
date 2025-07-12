import sys
import os
import logging
from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import QSize
from PySide6.QtGui import QFont
# Load custom modules
from utils import *
from ui import QSnippet

logger = logging.getLogger(__name__)


class main():
    def __init__(self):
        # Main Program Execution
        self.create_global_variables()
        self.load_config()
        self.load_settings()
        self.init_logger()
        # self.ensure_snippets_file_exists()
        self.scale_ui_cfg()
        self.fix_image_paths()
        self.start_program()

    def create_global_variables(self):
        # Global Configuration Variables
        self.pid = os.getpid()  # Store Process ID of application
        self.app = QApplication.instance()  # Use the existing QApplication instance
        self.clipboard = self.app.clipboard()
        self.screen_geometry = self.app.primaryScreen().geometry()
        self.screen_width = self.screen_geometry.width()
        self.screen_height = self.screen_geometry.height()
        self.REFERENCE_WIDTH = 1920
        self.REFERENCE_HEIGHT = 1080
        # Flag to skip loading reg key
        self.skip_reg = False

        # Define Directories
        self.working_dir = FileUtils.get_default_paths()["working_dir"]
        self.default_os_paths = self.get_default_paths()

        self.logs_dir = self.default_os_paths["log_dir"]
        self.documents_dir = self.default_os_paths["documents"]
        self.images_path = os.path.join(self.working_dir, "images")
        # Ensure directories exist
        self.ensure_directories_exist([
            self.logs_dir,
            self.documents_dir,
            self.images_path
        ])

        # Define Files
        self.app_exe = self.working_dir / "QSnippet.exe"
        self.config_file = self.documents_dir / "config.yaml"
        self.settings_file = self.documents_dir / "settings.yaml"   # updated to documents dir 062825
        self.snippets_file = self.working_dir / "snippets.yaml"
        self.snippet_db_file = self.documents_dir / "snippets.db"     # updated to documents dir 062825
        # Ensure files exist
        self.ensure_files_exist([
            {"file": self.config_file, "function": FileUtils.create_config_file(self.config_file)},
            {"file": self.settings_file, "function": FileUtils.create_settings_file(self.settings_file)},
            {"file": self.snippet_db_file, "function": FileUtils.create_snippets_db_file(self.snippet_db_file)}
        ])
        self.snippet_db = SnippetDB(self.snippet_db_file)
        # Comment out to run migration
        # self.migrate_yaml_to_sqlite(self.snippets_file, self.snippet_db)

        self.program_icon = os.path.join(self.images_path, "QSnippet_Icon_v1.png")
        self.log_path = os.path.join(self.logs_dir, "QSnippet.log")

    def migrate_yaml_to_sqlite(self, yaml_path, db: SnippetDB):
        import yaml
        with open(yaml_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        for entry in data.get("snippets", []):
            entry["tags"] = ""
            entry["return_press"] = False
            db.insert_snippet(entry)
        
    def get_default_paths(self):
        """ Retrieve and return the default directories based on OS """
        try:
            system = platform.system()
            user_home = Path.home()

            # Generate Default Directories Based on OS
            if system == "Windows": # Windows
                documents = Path(os.path.join(os.environ["USERPROFILE"], "Documents", "QSnippet"))
                log_dir = Path(os.getenv("ProgramData", "C:/ProgramData")) / "QSnippet" / "logs"
            elif system == "Darwin":    # MacOS
                documents = user_home / "Documents" / "QSnippet"
                log_dir = user_home / "Library" / "Logs" / "QSnippet"
            else:  # Linux and others
                documents = user_home / "Documents" / "QSnippet"
                log_dir = Path("/var/log/QSnippet")

            return {
                "documents": documents,
                "ads_dir": documents / "ads",   # not used; 04/06/25
                "export_dir": documents / "exports",
                "recordings_dir": documents / "recordings", # not used; 04/06/25
                "log_dir": log_dir
            }
        except Exception as e:
            logging.critical("Could not retrieve OS specific directories!")
            raise ValueError("Could not retrieve OS specific directories! Please contact application vendor.")
        
    def ensure_directories_exist(self, directories: list = []):
        """
        Ensures that all directories in the given list exist.
        If a directory does not exist, it is created.

        :param directories: List of directory paths to check/create
        """
        for directory in directories:
            try:
                os.makedirs(directory, exist_ok=True)
            except Exception as e:
                logging.critical(f"Failed to make directory {directory}! Error: {e}")
                raise ValueError("Failed to make directory {directory}! "
                                 f"Please contact application vendor. Error: {e}")
            
    def ensure_files_exist(self, files: list = []):
        """
        Ensures all specified files exist. If a file is missing,
        its corresponding creation function is called.
        
        :param files: List of dicts like { "file": Path, "function": callable }
        """
        for entry in files:
            path = entry.get("file")
            create_fn = entry.get("function")

            if not path.exists():
                logger.warning(f"Missing file: {path}. Creating default...")
                try:
                    create_fn(path)
                    logger.info(f"Created default file: {path}")
                except Exception as e:
                    logger.critical(f"Failed to create {path}: {e}")
                    raise ValueError(f"Failed to create required file: {path}\n\n{e}")
    
    def init_logger(self):
        """ Initialize the logger class """
        try:
            print("Setting up Logger")
            self.logger = AppLogger(log_filepath=self.log_path, log_level=self.log_level)
            logging.info("Logger initialized!")
        except Exception as e:
            #logging.critical("Could not initialize logger class!")
            raise ValueError(f"Could not initialize logger class! Please try running as root and if the issue persists, contact the application vendor.\nError: {e}")

    def ensure_snippets_file_exists(self):
        """
        Ensure that the main config file exists, otherwise write defaults.
        """
        if not self.snippets_file.exists():
            default = {
                'snippets': {"enabled": True,
                             "folder": None,
                             "label": "Welcome",
                             "paste_style": "Clipboard",
                             "snippet": "Welcome to QSnippets",
                             "trigger": "/welcome"}
            }
            FileUtils.write_yaml(path=self.snippets_file, data=default)

    def flatten_yaml(self, items: dict) -> bool:
        """ Flatten yaml to dict and assign to attributes. """
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
        
    def load_config(self):
        """ This function loads a yaml config file and flattens its entries into attributes. """
        # Check for config
        if not self.config_file.exists():
            QMessageBox.critical(None, "Error", f"Missing config: {self.config_file}")
            sys.exit(1)

        # Setup Config file watcher
        self.loader = ConfigLoader(self.config_file, parent=self)
        self.loader.configChanged.connect(self._on_config_updated)
        self.cfg = self.loader.config
        self.flatten_yaml(items=self.cfg)

    def _on_config_updated(self, config):
        """ When config update is detected, refresh config variable and UI elements. """
        logger.info("Config reloaded.")
        if config:
            self.cfg = config
            self.flatten_yaml()  # Flatten config again to refresh attributes.
            self.scale_ui_cfg(items=self.cfg) # Refresh UI config and scale
            self.qsnippet.editor.applyStyles()    # Trigger UI update
            self.app.processEvents()
        # Should also fire off UI refresh, etc to ensure the UI matches the config

    def load_settings(self):
        """ This function loads a yaml settings file and flattens its entries into attributes. """
        # Check for config
        if not self.settings_file.exists():
            QMessageBox.critical(None, "Error", f"Missing settings: {self.settings_file}")
            sys.exit(1)

        # Setup Config file watcher
        self.loader = SettingsLoader(self.settings_file, parent=self)
        self.loader.settingsChanged.connect(self._on_settings_updated)
        self.settings = self.loader.settings
        self.flatten_yaml(items=self.settings)
        self.handle_start_up_reg()

    def _on_settings_updated(self, config):
        """ When config update is detected, refresh config variable and UI elements. """
        logger.info("Settings reloaded.")
        if config:
            self.settings = config
            self.flatten_yaml(items=self.settings)  # Flatten config again to refresh attributes.
            self.handle_start_up_reg()

    def handle_start_up_reg(self):
        """ Based on settings, set the correct registry key for startup """
        if self.skip_reg:
            return
        elif not RegUtils.is_in_run_key("QSnippet") and self.settings["general"]["start_at_boot"] == True:
            RegUtils.add_to_run_key(app_exe_path=self.app_exe, entry_name="QSnippet")
        elif RegUtils.is_in_run_key("QSnippet") and self.settings["general"]["start_at_boot"] == False:
            RegUtils.remove_from_run_key(entry_name="QSnippet")

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
        self.mini_button_size = QSize(self.dimensions_buttons["mini"]["width"], self.dimensions_buttons["mini"]["height"])
        self.small_button_size = QSize(self.dimensions_buttons["small"]["width"], self.dimensions_buttons["small"]["height"])
        self.medium_button_size = QSize(self.dimensions_buttons["medium"]["width"], self.dimensions_buttons["medium"]["height"])
        self.large_button_size = QSize(self.dimensions_buttons["large"]["width"], self.dimensions_buttons["large"]["height"])
        
        # Font Sizes
        self.small_font_size = QFont(self.fonts["primary_font"], self.fonts_sizes["small"])
        self.small_font_size_bold = QFont(self.fonts["primary_font"], self.fonts_sizes["small"], QFont.Bold)
        self.medium_font_size = QFont(self.fonts["primary_font"], self.fonts_sizes["medium"])
        self.medium_font_size_bold = QFont(self.fonts["primary_font"], self.fonts_sizes["medium"], QFont.Bold)
        self.large_font_size = QFont(self.fonts["primary_font"], self.fonts_sizes["large"])
        self.large_font_size_bold = QFont(self.fonts["primary_font"], self.fonts_sizes["large"], QFont.Bold)
        self.extra_large_font_size = QFont(self.fonts["primary_font"], self.fonts_sizes["extra_large"])
        self.extra_large_font_size_bold = QFont(self.fonts["primary_font"], self.fonts_sizes["extra_large"], QFont.Bold)
        self.humongous_font_size = QFont(self.fonts["primary_font"], self.fonts_sizes["humongous"])
        self.humongous_font_size_bold = QFont(self.fonts["primary_font"], self.fonts_sizes["humongous"], QFont.Bold)

        # Widget Sizes
        self.small_toggle_size = QSize(self.dimensions_toggles["small"]["width"], self.dimensions_toggles["small"]["height"])        

    def fix_image_paths(self):
        """ This loops through images and appends the right path. """
        for image in self.images:
            old_val = self.images[image]
            self.images[image] = os.path.join(self.images_path, old_val)

    def scale_width(self, original_width, screen_geometry):
        """Scale a width value from the 1920 reference to the current screen."""
        ratio = screen_geometry.width() / self.REFERENCE_WIDTH
        return int(original_width * ratio)

    def scale_height(self, original_height, screen_geometry):
        """Scale a height value from the 1080 reference to the current screen."""
        ratio = screen_geometry.height() / self.REFERENCE_HEIGHT
        return int(original_height * ratio)
    
    def scale_dict_sizes(self, size_dict: dict, screen_geometry):
        """
        Given a dict of widget specs:
        {
            "name": {"width": W, "height": H, "radius": R},
            ...
        }
        returns a new dict with each dimension scaled to the current screen.
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
        Given a dict of font sizes:
          { "small": 14, "medium": 18, … }
        returns a new dict with each size scaled to the screen height.
        """
        # scale fonts by the ratio of current screen height to reference height
        ratio = screen_geometry.height() / self.REFERENCE_HEIGHT

        # if you want integer point sizes, wrap with int(...)
        return {
            name: int(size * ratio)
            for name, size in font_dict.items()
        }

    def start_program(self):
        """ Create and show the main window/tray"""
        self.qsnippet = QSnippet(parent=self)
        self.qsnippet.run()

if __name__ == '__main__':
    app = QApplication(sys.argv)    # Initialize QApplication
    # Commented out for testing. Need to restore.
    """try:
        ex = main()
        sys.exit(ex.app.exec())
    except Exception as e:
        QMessageBox.critical(None, "Fatal Error", str(e))
        sys.exit(1)"""
    
    ex = main()
    sys.exit(ex.app.exec())
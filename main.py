import sys
import os
import logging
from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import QSize
from PySide6.QtGui import QFont
# Load custom modules
from utils.file_utils import FileUtils
from utils.config_utils import ConfigLoader
from ui import QSnippet

logger = logging.getLogger(__name__)

class main():
    def __init__(self):
        # Main Program Execution
        self.create_global_variables()
        self.load_config()
        self.ensure_snippets_file_exists()
        self.scale_ui_cfg()
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

        # Define Directories
        self.working_dir = FileUtils.get_default_paths()["working_dir"]
        self.images_path = os.path.join(self.working_dir, "images")

        # Define Files
        self.config_file = self.working_dir / "config.yaml"
        self.snippets_file = self.working_dir / "snippets.yaml"
        self.program_icon = os.path.join(self.images_path, "QSnippet_Icon_v1.png")

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

    def load_config(self):
        """ This function loads a yaml config file and flattens its entries into attributes. """
        # Check for config
        if not self.config_file.exists():
            QMessageBox.critical(None, "Error", f"Missing config: {self.config_file}")
            sys.exit(1)

        # Load YAML settings
        self.loader = ConfigLoader(self.config_file, parent=self)
        self.loader.configChanged.connect(self._on_config_updated)
        self.cfg = self.loader.config
        self.flatten_cfg()

    def flatten_cfg(self):
        """ Flatten configuration dict and assign to attributes. """
        try:
            # Assign every top-level config key as an attribute on self
            # e.g. config['program_name'] → self.program_name
            for key, val in self.cfg.items():
                setattr(self, key, val)

            # For each nested dict (like colors, images, sizing), flatten its entries
            # by prefixing with the section name:
            # e.g. config['images']['icon'] → self.images_icon
            #      config['colors']['primary_accent_active'] → self.colors_primary_accent_active`
            for section, subdict in self.cfg.items():
                if isinstance(subdict, dict):
                    for subkey, subval in subdict.items():
                        attr_name = f"{section}_{subkey}"
                        setattr(self, attr_name, subval)

            return True
        except:
            logger.error("Failed to flatten config")
            return False

    def _on_config_updated(self, config):
        """ When config update is detected, refresh config variable and UI elements. """
        logger.info("Config reloaded.")
        if config:
            self.cfg = config
            self.flatten_cfg()  # Flatten config again to refresh attributes.
            self.scale_ui_cfg() # Refresh UI config and scale
            self.qsnippet.editor.updateUI()    # Trigger UI update
            self.app.processEvents()
        # Should also fire off UI refresh, etc to ensure the UI matches the config

    def scale_ui_cfg(self):
        """ 
        Reassigns the size attributes with scaled versions. 
        Needs more work but this will do for now 05/07/25
        """
        print("Scaling UI elements")
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

        print(self.fonts)

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
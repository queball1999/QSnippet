import os
import platform
import logging
import yaml
from datetime import datetime
from pathlib import Path
from PySide6.QtWidgets import QFileDialog, QMessageBox


class FileUtils:
    """
    Utility class for common file and directory operations.
    """
    @staticmethod
    def ensure_dir(path: Path):
        """Create directory if it doesn"t exist."""
        try:
            path.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logging.critical(f"Could not create directory {path}: {e}")
            raise

    @staticmethod
    def read_yaml(path: Path) -> dict:
        """Read a YAML file and return its contents as a dict."""
        try:
            with path.open("r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            logging.error(f"Failed to read YAML file {path}: {e}")
            return {}

    @staticmethod
    def write_yaml(path: Path, data: dict):
        """Write a dict to a YAML file atomically."""
        temp_path = path.with_suffix(path.suffix + ".tmp")
        try:
            with temp_path.open("w", encoding="utf-8") as f:
                yaml.safe_dump(data, f)
            temp_path.replace(path)
        except Exception as e:
            logging.error(f"Failed to write YAML file {path}: {e}")
            raise

    @staticmethod
    def export_snippets_yaml(path: Path, snippets: list[dict]):
        """Export snippets to a YAML file."""
        try:
            data = {"snippets": snippets}
            FileUtils.write_yaml(path, data)
            logging.info(f"Exported {len(snippets)} snippets to {path}")
        except Exception as e:
            logging.error(f"Failed to export snippets to YAML: {e}")
            raise

    @staticmethod
    def import_snippets_yaml(path: Path) -> list[dict]:
        """Import snippets from a YAML file and return as a list of dicts."""
        try:
            data = FileUtils.read_yaml(path)
            snippets = data.get("snippets", [])
            if not isinstance(snippets, list):
                raise ValueError("Invalid YAML format: 'snippets' must be a list.")
            logging.info(f"Imported {len(snippets)} snippets from {path}")
            return snippets
        except Exception as e:
            logging.error(f"Failed to import snippets from YAML: {e}")
            raise

    @staticmethod
    def import_snippets_with_dialog(parent, db):
        path, _ = QFileDialog.getOpenFileName(
            parent,
            "Import Snippets from YAML",
            str(Path.home()),
            "YAML Files (*.yaml *.yml)"
        )
        if not path:
            return 0

        snippets = FileUtils.import_snippets_yaml(Path(path))
        new_count = 0
        updated_count = 0

        for entry in snippets:
            is_new = db.insert_snippet(entry)
            if is_new:
                new_count += 1
            else:
                updated_count += 1

        QMessageBox.information(
            parent,
            "Import Complete",
            f"Imported {new_count} new snippets.\nUpdated {updated_count} existing snippets."
        )
        return new_count + updated_count


    @staticmethod
    def export_snippets_with_dialog(parent, db):
        date = datetime.now().date()
        path, _ = QFileDialog.getSaveFileName(
            parent,
            "Export Snippets to YAML",
            str(Path.home() / f"qsnippets-export-{date}.yaml"),
            "YAML Files (*.yaml *.yml)"
        )
        if not path:
            return 0
        snippets = db.get_all_snippets()
        FileUtils.export_snippets_yaml(Path(path), snippets)
        QMessageBox.information(parent, "Export Complete", f"Exported {len(snippets)} snippets.")
        return len(snippets)

    @staticmethod
    def file_exists(path: Path) -> bool:
        """Check whether a file exists."""
        return path.is_file()
    
    @staticmethod
    def get_default_paths():
        """
        Retrieve default directories based on the operating system.
        """
        try:
            system = platform.system()
            user_home = Path.home()

            if system == "Windows":
                app_data = Path(os.path.join(os.environ["LOCALAPPDATA"], "QSnippet"))
                documents = Path(os.path.join(os.environ["USERPROFILE"], "Documents", "QSnippet"))
                log_dir = Path(os.getenv("ProgramData", "C:/ProgramData")) / "QSnippet" / "logs"
            elif system == "Darwin":
                app_data = user_home / "Library" / "Application Support" / "QSnippet"
                documents = user_home / "Documents" / "QSnippet"
                log_dir = user_home / "Library" / "Logs" / "QSnippet"
            else:
                app_data = Path(os.getenv("XDG_DATA_HOME", user_home / ".local" / "share")) / "QSnippet"
                documents = user_home / "Documents" / "QSnippet"
                log_dir = Path("/var/log/QSnippet")

            # Ensure directories exist
            FileUtils.ensure_dir(documents)
            FileUtils.ensure_dir(log_dir)

            # Get current working directory
            cwd = Path.cwd()

            return {
                "app_data": app_data,
                "documents": documents,
                "log_dir": log_dir,
                "working_dir": cwd
            }
        except Exception as e:
            logging.critical("Could not retrieve OS specific directories!")
            raise ValueError("Could not retrieve OS specific directories! Please contact application vendor.")
    
    def create_config_file(path):
        default_config = {
        "program_name": "QSnippet",
        "version": "0.0.0",
        "log_level": "DEBUG",
        "support_info": {
            "email": "support@quynnsoftware.com"
        },
        "colors": {
            "primary_background_active": "#FFFFFF",
            "primary_background_disabled": "#e1e1e1",
            "secondary_background_active": "#e1e1e1",
            "secondary_background_disabled": "#7f7f7f",
            "primary_accent_active": "#0a51cf",
            "primary_accent_pressed": "#4895f6",
            "primary_accent_disabled": "#cee9fe",
            "secondary_accent_active": "#5c5e70",
            "secondary_accent_pressed": "#abadba",
            "secondary_accent_disabled": "#e3e4e8",
            "tertiary_accent_active": "#0a8dcf",
            "tertiary_accent_pressed": "#48d4f6",
            "tertiary_accent_disabled": "#cefefd",
            "success_color": "#00cc6a",
            "fail_color": "#e81123",
            "overlay_color": "#2a4252",
            "dark_text_color_active": "#151a30",
            "dark_text_color_disabled": "#7580ae",
            "light_text_color_active": "#FFFFFF",
            "light_text_color_disabled": "#FFFFFF"
        },
        "images": {
            "icon_256": "QSnippet_256x256.png",
            "icon_128": "QSnippet_128x128.png",
            "icon_64": "QSnippet_64x64.png",
            "icon_32": "QSnippet_32x32.png",
            "icon_16": "QSnippet_16x16.png"
        },
        "fonts": {
            "primary_font": "Inter",
            "secondary_font": "DM Sans",
            "sizes": {
            "small": 12,
            "medium": 14,
            "large": 20,
            "extra_large": 26,
            "humongous": 32
            }
        },
        "dimensions": {
            "windows": {
            "main": {
                "width": 1200,
                "height": 800
            }
            },
            "buttons": {
            "mini_slim": {
                "width": 75,
                "height": 25,
                "radius": 4
            },
            "mini": {
                "width": 100,
                "height": 25,
                "radius": 8
            },
            "small": {
                "width": 125,
                "height": 35,
                "radius": 8
            },
            "medium": {
                "width": 200,
                "height": 45,
                "radius": 8
            },
            "large": {
                "width": 250,
                "height": 65,
                "radius": 8
            }
            },
            "toggles": {
            "small": {
                "width": 60,
                "height": 45,
                "radius": 10
            }
            }
        }
        }

        FileUtils.write_yaml(path, default_config)

    def create_settings_file(path):
        default_settings = {
            "general": {
                "start_at_boot": False,
                "show_ui_at_start": True
            },
            "appearance": {
                "theme": "dark"
            }
        }
        FileUtils.write_yaml(path, default_settings)

    def create_snippets_db_file(path):
        from .snippet_db import SnippetDB
        db = SnippetDB(path)
        db._create_table()

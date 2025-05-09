import logging
import time
import argparse
import sys
from PySide6.QtWidgets import QApplication, QMessageBox
from utils.config_utils import ConfigLoader
from utils.keyboard_utils import SnippetExpander
from utils.file_utils import FileUtils

class main():
    def __init__(self):
        self.app = QApplication.instance()

        paths = FileUtils.get_default_paths()
        log_file = paths['log_dir'] / 'qsnippet_service.log'
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s %(levelname)s: %(message)s',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler()
            ]
        )

        parser = argparse.ArgumentParser(description="Snippet expansion service")
        parser.add_argument(
            "--config",
            type=str,
            default=paths['working_dir'] / 'snippets.yaml',
            help="Path to snippet YAML config file",
        )
        args = parser.parse_args()

        logging.info(f"Using config file: {args.config}")
        loader = ConfigLoader(args.config)
        expander = SnippetExpander(config_loader=loader, parent=self)

        try:
            expander.start()
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logging.info("Shutting down...")
        finally:
            expander.stop()
            loader.stop()

if __name__ == '__main__':
    app = QApplication(sys.argv)    # Initialize QApplication
    try:
        ex = main()
        sys.exit(ex.app.exec())
    except Exception as e:
        # Display GUI error box
        error_dialog = QMessageBox()
        error_dialog.setIcon(QMessageBox.Critical)
        error_dialog.setWindowTitle("Application Error")
        error_dialog.setText("An error occurred while starting the application.")
        error_dialog.setInformativeText(str(e))
        error_dialog.exec()
        sys.exit(1)

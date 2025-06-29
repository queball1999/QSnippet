import os
import logging
import zipfile
from logging.handlers import RotatingFileHandler

class CompressedRotatingFileHandler(RotatingFileHandler):
    def doRollover(self):
        """
        Overrides the default rollover behavior to compress the rotated log file
        and enforce the backup count limit.
        """
        if self.stream:
            self.stream.close()
            self.stream = None

        # Remove the oldest compressed log if it exists
        if self.backupCount > 0:
            oldest = f"{self.baseFilename}.{self.backupCount}.zip"
            if os.path.exists(oldest):
                os.remove(oldest)

            # Rename/compress existing backup files (rotate their names)
            for i in range(self.backupCount - 1, 0, -1):
                sfn = f"{self.baseFilename}.{i}.zip"
                dfn = f"{self.baseFilename}.{i+1}.zip"
                if os.path.exists(sfn):
                    os.rename(sfn, dfn)

            # Compress the current log file and rename it as .1.zip
            dfn = f"{self.baseFilename}.1.zip"
            self.compress_log_file(self.baseFilename, dfn)

        # Reopen the stream in write mode to start a new log file.
        self.mode = 'w'
        self.stream = self._open()

    def compress_log_file(self, source, dest_zip):
        """
        Compress the source log file into a zip archive named dest_zip,
        then remove the original source file.
        """
        with zipfile.ZipFile(dest_zip, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
            # Write the file into the zip archive using its basename.
            zf.write(source, arcname=os.path.basename(source))
        os.remove(source)

"""
This class is responsible for setting up and handling logging

Example Usage: logging.info("This is a log message")
"""
class AppLogger:
    def __init__(self, log_filepath, log_level, max_bytes=25 * 1024 * 1024, backup_count=5):
        print("Init Logger")
        self.log_filepath = log_filepath
        self.log_level = log_level
        self.max_bytes = max_bytes
        self.backup_count = backup_count
        self.configure_logger()

    def configure_logger(self):
        handler = CompressedRotatingFileHandler(
            self.log_filepath,
            maxBytes=self.max_bytes,
            backupCount=self.backup_count
        )
        formatter = logging.Formatter('[%(levelname)s] %(asctime)s [%(name)s]: %(message)s')
        handler.setFormatter(formatter)
        
        logger = logging.getLogger()
        logger.setLevel(self.log_level)
        # Remove any existing handlers if reconfiguring.
        if logger.hasHandlers():
            logger.handlers.clear()
        logger.addHandler(handler)

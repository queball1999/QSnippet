from pathlib import Path
import os, sys
import logging

# Setup logging
logger = logging.getLogger(__name__)


# ----- System Utilities -----
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
                
def detect_package_manager():
    """Detect the package manager on a Linux system."""
    if sys.platform != "linux":
        return None
    
    if Path("/usr/bin/apt").exists():
        return "apt"
    if Path("/usr/bin/dnf").exists():
        return "dnf"
    if Path("/usr/bin/pacman").exists():
        return "pacman"
    return None

def check_binary(binary_name):
    """Check if a binary is available in the system PATH."""
    import shutil
    return shutil.which(binary_name) is not None

def check_required_packages(requirements):
    """Check for required packages and return a list of missing ones."""
    missing_packages = []

    # Check for required packages
    for package, info in requirements.items():
        lib_name = info["library"]

        try:
            check_binary(lib_name)
        except OSError:
            missing_packages.append((package, info["install_hint"]))

    return missing_packages
from pathlib import Path
import os, sys
import logging

# Setup logging
logger = logging.getLogger(__name__)


# ----- System Utilities -----
def ensure_directories_exist(self, directories: list = []) -> None:
    """
    Ensure that all specified directories exist.

    Creates each directory in the provided list if it does not already
    exist.

    Args:
        directories (list): A list of directory paths to verify or create.

    Returns:
        None

    Raises:
        ValueError: If a directory cannot be created.
    """
    for directory in directories:
        try:
            os.makedirs(directory, exist_ok=True)
        except Exception as e:
            logging.critical(f"Failed to make directory {directory}! Error: {e}")
            raise ValueError("Failed to make directory {directory}! "
                                f"Please contact application vendor. Error: {e}")

def ensure_files_exist(self, files: list = []) -> None:
    """
    Ensure that all specified files exist.

    For each entry in the provided list, checks whether the file exists.
    If missing, calls the associated creation function.

    Args:
        files (list): A list of dictionaries containing:
            - "file" (Path): The file path to verify.
            - "function" (callable): The function to call to create the file.

    Returns:
        None

    Raises:
        ValueError: If a required file cannot be created.
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
                
def detect_package_manager() -> str:
    """
    Detect the Linux package manager.

    Checks for common package manager binaries on Linux systems.

    Returns:
        str | None: The name of the detected package manager, or None
            if not running on Linux or no known manager is found.
    """

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
    """
    Check whether a binary is available in the system PATH.

    Args:
        binary_name (str): The name of the binary to check.

    Returns:
        bool: True if the binary is found in PATH, otherwise False.
    """
    import shutil
    return shutil.which(binary_name) is not None

def check_required_packages(requirements):
    """
    Check for required system packages.

    Verifies the presence of required binaries and collects any
    missing packages along with their installation hints.

    Args:
        requirements (dict): A dictionary mapping package names to
            metadata containing "library" and "install_hint" keys.

    Returns:
        list: A list of tuples containing the missing package name
            and its installation hint.
    """
    missing_packages = []

    # Check for required packages
    for package, info in requirements.items():
        lib_name = info["library"]

        try:
            check_binary(lib_name)
        except OSError:
            missing_packages.append((package, info["install_hint"]))

    return missing_packages
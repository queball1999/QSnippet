import logging
import time
from utils.config_utils import ConfigLoader
from utils.keyboard_utils import SnippetExpander
from utils.file_utils import FileUtils

def main():
    import argparse

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
    expander = SnippetExpander(loader)

    try:
        expander.start()
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logging.info("Shutting down...")
    finally:
        expander.stop()
        loader.stop()


if __name__ == "__main__":
    main()

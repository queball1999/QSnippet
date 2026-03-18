#!/usr/bin/env python3
import yaml
import os
import sys

# updating dir 12/22/25 to reflect new config path
with open("config/config.yaml") as f:
    cfg = yaml.safe_load(f)

version = cfg.get("version")
name = cfg.get("program_name")

# Always output to GitHub Actions environment
if os.environ.get("GITHUB_ACTIONS"):
    github_env = os.environ.get("GITHUB_ENV")
    if github_env:
        with open(github_env, "a") as f:
            f.write(f"APP_VERSION={version}\n")
            f.write(f"PROGRAM_NAME={name}\n")
        print(f"✓ Set APP_VERSION={version}")
        print(f"✓ Set PROGRAM_NAME={name}")
    else:
        print("Warning: GITHUB_ENV not set", file=sys.stderr)
else:
    print(f"APP_VERSION={version}")
    print(f"PROGRAM_NAME={name}")

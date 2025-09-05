#!/usr/bin/env python3
import yaml, os, sys

with open("config.yaml") as f:
    cfg = yaml.safe_load(f)

version = cfg.get("version")
name = cfg.get("program_name")

print(f"APP_VERSION={version}")
print(f"PROGRAM_NAME={name}")

# Write to GITEA_ENV if available
gitea_env = os.environ.get("GITEA_ENV")
if gitea_env:
    with open(gitea_env, "a") as envfile:
        envfile.write(f"APP_VERSION={version}\n")
        envfile.write(f"PROGRAM_NAME={name}\n")

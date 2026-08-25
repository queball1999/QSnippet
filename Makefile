.PHONY: run build build-deb updater test benchmark lint release clean help create-venv recreate-venv activate-venv

MAIN := QSnippet.py
VENV_DIR := .venv

# Lets `make release v0.0.8-release` work: the tag is a second goal, which
# make would otherwise try to build. Absorb it into TAG and give it a no-op
# rule, but only when release is what was actually asked for, so a typo in
# any other target still errors instead of silently succeeding.
ifeq (release,$(firstword $(MAKECMDGOALS)))
TAG ?= $(word 2,$(MAKECMDGOALS))
ifneq ($(TAG),)
$(eval $(TAG):;@:)
endif
endif

ifeq ($(OS),Windows_NT)
PYTHON := "c:\Python314\python.exe"
VENV_PYTHON := $(VENV_DIR)\Scripts\python.exe
else
PYTHON := python3
VENV_PYTHON := $(VENV_DIR)/bin/python3
endif

help:
ifeq ($(OS),Windows_NT)
	@echo Available targets:
	@echo   make run            - Run the application
	@echo   make build          - Build the updater, binary and installer
	@echo   make updater        - Build the branded updater into output\windows
	@echo   make test           - Run the unit tests
	@echo   make lint           - Run flake8 the way CI does
	@echo   make release TAG    - Check and push a release tag, e.g. make release v0.0.8-release
	@echo   make clean          - Clean build artifacts
	@echo   make create-venv    - Create .venv if missing and install dependencies
	@echo   make recreate-venv  - Delete and rebuild .venv from scratch
	@echo   make activate-venv  - Print the command to activate .venv
else
	@echo "Available targets:"
	@echo "  make run            - Run the application"
	@echo "  make build          - Build the application (updater + PyInstaller binary + portable archive)"
	@echo "  make updater        - Build the branded updater into output/linux"
	@echo "  make test           - Run the unit tests"
	@echo "  make lint           - Run flake8 the way CI does"
	@echo "  make release TAG    - Check and push a release tag, e.g. make release v0.0.8-release"
	@echo "  make build-deb      - Package a .deb from the build output (run after 'make build')"
	@echo "  make clean          - Clean build artifacts"
	@echo "  make create-venv    - Create .venv (if missing) and install dependencies"
	@echo "  make recreate-venv  - Delete and rebuild .venv from scratch"
	@echo "  make activate-venv  - Print the command to activate .venv"
endif

run:
	$(PYTHON) $(MAIN)

test:
	$(PYTHON) -m pytest

benchmark:
	$(PYTHON) -m pytest --benchmark

# The same two passes CI runs in pr_checks.yaml: blocking on real errors,
# advisory on style.
lint:
	$(PYTHON) -m flake8 . --select=E9,F63,F7,F82 --show-source
	$(PYTHON) -m flake8 . --exit-zero

# Cut a release tag, after checking locally everything the pipeline checks
# after the fact. See tools/release.py.
#
#   make release v0.0.8-release
#   make release TAG=v0.0.8-dev
#   make release v0.0.8-release DRY_RUN=1
release:
ifeq ($(TAG),)
	@echo "Usage: make release v0.0.8-release   (suffix: release, dev, windows, linux)"
	@exit 1
else
	@$(PYTHON) tools/release.py $(TAG) $(if $(DRY_RUN),--dry-run,)
endif

# The installer and the .deb both expect a branded updater binary beside the
# app; CI gets it from the build_updater workflow, so a local build has to
# make its own. See tools/build_updater.ps1 and tools/build_updater.sh.
updater:
ifeq ($(OS),Windows_NT)
	powershell -NoProfile -ExecutionPolicy Bypass -Command "& .\tools\build_updater.ps1"
else
	bash tools/build_updater.sh
endif

# On Windows local_build.ps1 builds the updater and stamps its hash itself;
# on Linux build.sh only reads UPDATER_SHA256, so build the updater first.
build:
ifeq ($(OS),Windows_NT)
	powershell -NoProfile -ExecutionPolicy Bypass -Command "& .\tools\local_build.ps1"
else
	bash tools/build_updater.sh
	UPDATER_SHA256=$$(sha256sum output/linux/updater | cut -d' ' -f1) bash tools/build.sh
endif

build-deb:
ifeq ($(OS),Windows_NT)
	@echo build-deb is only available on Linux
else
	bash tools/package-deb.sh
endif

clean:
ifeq ($(OS),Windows_NT)
	@powershell -NoProfile -Command "& { \
		if (Test-Path build) { Remove-Item build -Recurse -Force; Write-Host 'Removed build/' }; \
		Get-ChildItem -Path . -Include '__pycache__' -Recurse -Force | Remove-Item -Recurse -Force; \
		Write-Host 'Cleaned build artifacts' \
	}"
else
	@rm -rf build
	@find . -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true
	@echo "Cleaned build artifacts"
endif

create-venv:
ifeq ($(OS),Windows_NT)
	@powershell -NoProfile -ExecutionPolicy Bypass -Command "& { \
		if (-not (Test-Path '$(VENV_DIR)')) { \
			Write-Host 'Creating virtual environment at $(VENV_DIR)...'; \
			& $(PYTHON) -m venv '$(VENV_DIR)'; \
		} else { \
			Write-Host 'Virtual environment already exists at $(VENV_DIR)'; \
		} \
	}"
	@"$(VENV_PYTHON)" -m pip install --upgrade pip
	@"$(VENV_PYTHON)" -m pip install -r requirements.txt
else
	@if [ ! -d "$(VENV_DIR)" ]; then \
		echo "Creating virtual environment at $(VENV_DIR)..."; \
		$(PYTHON) -m venv "$(VENV_DIR)"; \
	else \
		echo "Virtual environment already exists at $(VENV_DIR)"; \
	fi
	@"$(VENV_PYTHON)" -m pip install --upgrade pip
	@"$(VENV_PYTHON)" -m pip install -r requirements.txt
endif

recreate-venv:
ifeq ($(OS),Windows_NT)
	@powershell -NoProfile -ExecutionPolicy Bypass -Command "& { \
		if (Test-Path '$(VENV_DIR)') { \
			Write-Host 'Removing existing virtual environment at $(VENV_DIR)...'; \
			Remove-Item '$(VENV_DIR)' -Recurse -Force; \
		} \
	}"
else
	@rm -rf "$(VENV_DIR)"
endif
	@$(MAKE) create-venv

activate-venv:
ifeq ($(OS),Windows_NT)
	@echo make cannot activate a venv in your current shell; run one of the following yourself:
	@echo   PowerShell: .\$(VENV_DIR)\Scripts\Activate.ps1
	@echo   cmd.exe:    $(VENV_DIR)\Scripts\activate.bat
else
	@echo "make cannot activate a venv in your current shell; run this yourself:"
	@echo "  source $(VENV_DIR)/bin/activate"
endif

.PHONY: run build build-deb clean help create-venv recreate-venv activate-venv

MAIN := QSnippet.py
VENV_DIR := .venv

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
	@echo   make build          - Build the application
	@echo   make clean          - Clean build artifacts
	@echo   make create-venv    - Create .venv (if missing) and install dependencies
	@echo   make recreate-venv  - Delete and rebuild .venv from scratch
	@echo   make activate-venv  - Print the command to activate .venv
else
	@echo "Available targets:"
	@echo "  make run            - Run the application"
	@echo "  make build          - Build the application (PyInstaller binary + portable archive)"
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

build:
ifeq ($(OS),Windows_NT)
	powershell -NoProfile -ExecutionPolicy Bypass -Command "& .\tools\local_build.ps1"
else
	bash tools/build.sh
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

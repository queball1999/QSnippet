.PHONY: run build build-deb clean help

MAIN := QSnippet.py

ifeq ($(OS),Windows_NT)
PYTHON := "c:\Python314\python.exe"
else
PYTHON := python3
endif

help:
ifeq ($(OS),Windows_NT)
	@echo Available targets:
	@echo   make run       - Run the application
	@echo   make build     - Build the application
	@echo   make clean     - Clean build artifacts
else
	@echo "Available targets:"
	@echo "  make run       - Run the application"
	@echo "  make build     - Build the application (PyInstaller binary + portable archive)"
	@echo "  make build-deb - Package a .deb from the build output (run after 'make build')"
	@echo "  make clean     - Clean build artifacts"
endif

run:
	$(PYTHON) $(MAIN)

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

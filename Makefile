.PHONY: run build clean help

PYTHON := "c:\Python314\python.exe"
MAIN := "p:\Coding\Github Repos\QSnippet\QSnippet.py"
BUILD_SCRIPT := ".\tools\local_build.ps1"

help:
	@echo.
	@echo Available targets:
	@echo   make run      - Run the application
	@echo   make build    - Build the application
	@echo   make clean    - Clean build artifacts
	@echo.

run:
	$(PYTHON) $(MAIN)

build:
	powershell -NoProfile -ExecutionPolicy Bypass -Command "& $(BUILD_SCRIPT)"

clean:
	@powershell -NoProfile -Command "& { \
		if (Test-Path build) { Remove-Item build -Recurse -Force; Write-Host 'Removed build/' }; \
		Get-ChildItem -Path . -Include '__pycache__' -Recurse -Force | Remove-Item -Recurse -Force; \
		Write-Host 'Cleaned build artifacts' \
	}"

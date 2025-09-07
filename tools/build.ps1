param()

$ErrorActionPreference = "Stop"

# Ensure script runs from repo root
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location (Join-Path $ScriptDir "..")

# Extract version from config.yaml using Python
$VERSION = python -c "import yaml; print(yaml.safe_load(open('config.yaml'))['version'])"

$APP_NAME     = "QSnippet"
$ENTRY        = "QSnippet.py"
$ICON_WINDOWS = (Resolve-Path "./images/QSnippet.ico").Path
$ImageDir = Resolve-Path "./images"

# Define custom paths to keep root clean
$BUILD_DIR    = "build"   # work + spec files
$DIST_DIR     = "output/windows"

$PYINSTALLER_ARGS = @(
    "--noconfirm",
    "--onefile",
    "--windowed",
    "--icon=$ICON_WINDOWS",
    "--distpath", $DIST_DIR,
    "--workpath", "$BUILD_DIR/work",
    "--specpath", "$BUILD_DIR/spec",
    "--name", "$APP_NAME", # dropping version here for now, moved to post compile step
    "--add-data", "$ImageDir/QSnippet.ico;images",
    "--add-data", "$ImageDir/QSnippet_256x256.png;images",
    "--add-data", "$ImageDir/QSnippet_128x128.png;images",
    "--add-data", "$ImageDir/QSnippet_64x64.png;images",
    "--add-data", "$ImageDir/QSnippet_32x32.png;images",
    "--add-data", "$ImageDir/QSnippet_16x16.png;images",
    $ENTRY
)

Write-Host "Building $APP_NAME v$VERSION..." -ForegroundColor Cyan

# Clean old build artifacts
if (Test-Path $BUILD_DIR) { Remove-Item $BUILD_DIR -Recurse -Force }

# Detect OS
$OS = $env:OS
if (-not $OS) { $OS = (uname -s) }
Write-Host "Detected OS: $OS"

switch -Regex ($OS) {
    "Windows_NT" {
        Write-Host "Building for Windows..."
        Write-Host "Running: pyinstaller $PYINSTALLER_ARGS"
        & pyinstaller @PYINSTALLER_ARGS

        # After PyInstaller, try Inno Setup if available
        $ISCC = "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
        $ISS  = "QSnippet_v2.iss"

        if (Test-Path $ISCC) {
            if (Test-Path $ISS) {
                try {
                    Write-Host "Patching Inno Setup version in $ISS to $VERSION..."
                    (Get-Content $ISS) -replace '(?<=#define MyAppVersion\s+")[^"]+', $VERSION |
                        Set-Content $ISS -Encoding UTF8
                } catch {
                    Write-Warning "Failed to patch version in $ISS : $_"
                }

                try{
                    Write-Host "Running Inno Setup compiler..."
                    & $ISCC '/Qp' $ISS
                    Write-Host "Inno Setup build complete."
                } catch {
                    Write-Error "Ran into error while compiling installer: $_"
                }

                # Copy binary to portable version
                try{
                    $exePath = Join-Path $DIST_DIR "$APP_NAME.exe"
                    $exeRelease = Join-Path $DIST_DIR "$APP_NAME-$VERSION-portable.exe"
                    if (Test-Path $exePath) {
                        Copy-Item $exePath $exeRelease -Force
                        Write-Host "Copied $exePath to $exeRelease"
                    } else {
                        Write-Warning "Source binary ($exePath) could not be located."
                    }
                } catch {
                    Write-Error "Failed to copy $exePath to $exeRelease"
                }
            }
            else {
                Write-Warning "Inno Setup script file not found: $ISS"
            }
        }
        else {
            Write-Warning "Inno Setup not installed or ISCC.exe not found at $ISCC"
        }
    }
    default {
        Write-Error "Unsupported OS: $OS"
        exit 1
    }
}

Write-Host "Build complete: Binaries located in ./$DIST_DIR" -ForegroundColor Green

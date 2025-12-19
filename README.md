<div align="center">

  <p style="font-size: 24px; font-weight: 700;">QSnippet</p>

  <img src="images/icon_128x128.png">

    
  <p>
    <a href="https://github.com/queball1999/QSnippet/wiki">Wiki</a>
    |
    <a href="https://github.com/users/queball1999/projects/3/views/1">Project Tracking</a>
    |
    <a href="https://github.com/queball1999/QSnippet/releases">Releases</a>
  </p>
  
  <img src="https://img.shields.io/github/license/queball1999/QSnippet" alt="License"/>
  <img src="https://img.shields.io/badge/platform-Windows-blue" alt="Platform"/>
  <img src="https://img.shields.io/badge/python-3.13-blue" alt="Python"/>
  <img src="https://img.shields.io/badge/last%20updated-12/16/25-green" alt="Last Edited"/>
</div>

</br>

> QSnippet currently supports Windows only. Support for macOS and Linux is planned.

QSnippet is a local-first application for system-wide text snippet expansion. While there are several feature-rich snippet tools available, many felt very overwhelming to get started and didn’t fit how I work. 

I built QSnippet to be fast, predictable, and fully under my control. The goal was to provide a simple, reliable tool that improves my daily life without adding unnecessary complexity.

This project also serves to demonstrate my skills as a software developer and is purely a passion project.

## What QSnippet Does

QSnippet helps you:

- Replace repeated typing with short, easy-to-remember triggers
- Store and manage all snippets in one place
- Improve consistency in emails, notes, and documentation
- Work faster without relying on cloud services or browser extensions

## Screenshots

Demo
<img src="images/QSnippet_demo.gif" alt="Demo of QSnippet" style="align:center;"/>

Homepage
<img src="images/homepage.png" alt="Photo of QSnippet" style="align:center;"/>

Snippet Form
<img src="images/snippet_form.png" alt="Photo of QSnippet" style="align:center;"/>

## Installation

Prebuilt binaries are provided on the Releases page.

- Windows installer
- Portable version

If you prefer to build and run QSnippet from source, see the Development Notes below.

## Development Notes

QSnippet is written in Python and can be run directly from source or packaged as a standalone executable.

### Running from Source

Clone the repository and start the application:

```
git clone "https://github.com/queball1999/QSnippet"
cd QSnippet
python main.py
```

### Building with PyInstaller
To build a standalone executable, run:

```
pyinstaller --noconfirm --onefile --windowed --icon ".\images\QSnippet.ico" --add-data ".\images:images" ".\QSnippet.py"
```

or 

```
python -m PyInstaller --noconfirm --onefile --windowed --icon ".\images\QSnippet.ico" --add-data ".\images:images" ".\QSnippet.py"
```

## Verifying Downloads

All QSnippet releases are signed with GPG.

1. Import the public key:
    ```
    gpg --import gpg-public.asc
    ```

2. Verify checksum:
    ```
    gpg --verify SHA256SUMS.txt.sig SHA256SUMS.txt
    ```

3. Verify binary:
    ```
    sha256sum -c SHA256SUMS.txt
    ```

## License

QSnippet is released under the MIT License.  
See the [LICENSE](./LICENSE) file for details.

# Contributions
All contributions are welcome! Feel free to contribute directly to the project as a developer, or support the project’s continued development.

<a href="https://ko-fi.com/queball1999" target="_blank" rel="noopener">
  <img
    src="https://cdn.prod.website-files.com/5c14e387dab576fe667689cf/670f5a01c01ea9191809398c_support_me_on_kofi_blue.png"
    alt="Support me on Ko-fi"
    width="250"
  />
</a>
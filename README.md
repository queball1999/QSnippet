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
  
  <img src="https://img.shields.io/github/v/release/queball1999/QSnippet?color=lime-green" alt="Latest Release">
  <img src="https://img.shields.io/github/downloads/queball1999/qsnippet/total?color=blue" alt="Downloads">
  <img src="https://img.shields.io/github/license/queball1999/QSnippet?color=orange" alt="License"/>
  <img src="https://img.shields.io/github/last-commit/queball1999/QSnippet?color=red" alt="Last Commit"/>
</div>

</br>

> [!Warning]
> Before installing V0.0.5 or later, please back up your snippets and completely uninstall any older versions while ensuring to select option to wipe all data.


QSnippet is a local-first application for system-wide text snippet expansion. While there are several feature-rich snippet tools available, many felt very overwhelming to get started and didn’t fit how I work. 

I built QSnippet to be fast, predictable, and fully under my control. The goal was to provide a simple, reliable tool that improves my daily life without adding unnecessary complexity.

This project also serves to demonstrate my skills as a software developer and is purely a passion project. If you use QSnippet, consider supporting me.

<a href="https://ko-fi.com/queball1999" target="_blank" rel="noopener">
  <img
    src="https://cdn.prod.website-files.com/5c14e387dab576fe667689cf/670f5a01c01ea9191809398c_support_me_on_kofi_blue.png"
    alt="Support me on Ko-fi"
    height="40"
  />
</a>

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

> QSnippet currently supports Windows only. Support for macOS and Linux is planned.

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

### Verifying Downloads

All QSnippet releases are cryptographically signed using GPG. Each downloadable file is accompanied by a corresponding `.sig` signature that allows you to verify its integrity and authenticity.

These steps assume you have downloaded the project’s public signing key [gpg-public.asc](./gpg-public.asc) and want to verify a release file.

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


> **Important:** Do not run any downloaded files unless they are successfully verified.


### Unit Testing
To help mitigate breaking changes, I have added some unit tests to verify the core functionality working. I still need to add additional testing to include the UI elements, but this should do for now.

In order to run these tests, run the following command:

```
pytest
```

You should see something like the following output:
```
===================== test session starts =====================
platform win32 -- Python 3.13.11, pytest-8.4.1, pluggy-1.6.0
rootdir: ...\QSnippet
plugins: Faker-37.4.0
collected 53 items                                  

tests\core\test_flatten_yaml.py ...             [  5%]
tests\core\test_scaling.py ...                  [ 11%] 
tests\service\test_snippet_service.py .......   [ 26%]
tests\utils\test_config_utils.py ..........     [ 45%]
tests\utils\test_file_utils.py ..........       [ 64%]
tests\utils\test_logging_utils.py .....         [ 73%]
tests\utils\test_reg_utils.py ......            [ 84%]
tests\utils\test_snippet_db.py ........         [100%]

===================== 53 passed in 4.99s ======================
```

## License

**License Change Notice**

As of **January 2026**, QSnippet is licensed under the **GNU General Public License v3.0 (GPLv3)**.

- All releases and commits published **on or after January 2026** are distributed under GPLv3.
- All releases published **prior to this date** remain licensed under the MIT License and are unaffected.

This project is licensed under the GNU General Public License v3.0 (GPLv3). 
See the [LICENSE](./LICENSE) file for details.

# Contributions
All contributions are welcome! Feel free to contribute directly to the project as a developer, or support the project’s continued development.
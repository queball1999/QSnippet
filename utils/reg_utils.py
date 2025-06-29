import winreg


class RegUtils():
    def add_to_run_key(app_exe_path: str, entry_name: str = "QSnippet"):
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as run_key:
            # Set a new string value: name=entry_name, data="\"C:\\path\\to\\MyApp.exe\" --some-args"
            value = f"\"{app_exe_path}\""
            winreg.SetValueEx(run_key, entry_name, 0, winreg.REG_SZ, value)

    def remove_from_run_key(entry_name: str = "QSnippet"):
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as run_key:
                winreg.DeleteValue(run_key, entry_name)
        except FileNotFoundError:
            pass

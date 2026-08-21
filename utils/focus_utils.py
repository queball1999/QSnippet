"""
Foreground-window helpers used around modal prompts that interrupt typing.

When a snippet trigger fires, the user is typing in some *other* application.
Any dialog we raise has to (a) actually take keyboard focus, and (b) hand focus
back to that same application before the expander starts sending keystrokes,
otherwise the paste lands in the wrong window.

Windows deliberately blocks SetForegroundWindow from a process that does not
own the foreground window and did not receive the last input event - which
describes us exactly, since the user's keystrokes went to the other app. Three
things are needed to get past that lock, and all three are required; any one of
them alone is unreliable:

  1. Attach our input queue to the thread that *currently owns the foreground*
     (not to the target window's thread - for our own dialog that is us, and
     attaching a thread to itself is a no-op).
  2. Zero the foreground lock timeout for the duration of the call.
  3. As a last resort only, inject a synthetic Alt tap so our process is the
     one that produced the most recent input event. This is deliberately not
     the default: the tap is delivered to whichever application currently has
     focus, and a lone Alt activates the menu bar in many programs. Steps 1
     and 2 together are enough in practice, so the tap is used only after
     those have already failed, and never when handing focus back to the
     user's application.

Everything here is a no-op returning None/False on non-Windows platforms, so
callers do not need to branch.
"""

import sys
import time
import logging

logger = logging.getLogger(__name__)

IS_WINDOWS = sys.platform == "win32"

SW_RESTORE = 9
SW_SHOW = 5
SPI_GETFOREGROUNDLOCKTIMEOUT = 0x2000
SPI_SETFOREGROUNDLOCKTIMEOUT = 0x2001
SPIF_SENDCHANGE = 0x0002
KEYEVENTF_KEYUP = 0x0002
VK_MENU = 0x12

USER32 = None
KERNEL32 = None


def user32():
    """
    Return the user32 WinDLL with prototypes declared, or None when unavailable.

    Declaring argtypes/restype is not optional here: window handles are
    pointer-sized, and ctypes defaults to a 32-bit C int, which silently
    truncates every HWND on 64-bit Windows.
    """
    global USER32, KERNEL32

    if not IS_WINDOWS:
        return None
    if USER32 is not None:
        return USER32

    try:
        import ctypes
        from ctypes import wintypes

        dll = ctypes.WinDLL("user32", use_last_error=True)
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)

        dll.GetForegroundWindow.argtypes = []
        dll.GetForegroundWindow.restype = wintypes.HWND
        dll.SetForegroundWindow.argtypes = [wintypes.HWND]
        dll.SetForegroundWindow.restype = wintypes.BOOL
        dll.SetActiveWindow.argtypes = [wintypes.HWND]
        dll.SetActiveWindow.restype = wintypes.HWND
        dll.SetFocus.argtypes = [wintypes.HWND]
        dll.SetFocus.restype = wintypes.HWND
        dll.BringWindowToTop.argtypes = [wintypes.HWND]
        dll.BringWindowToTop.restype = wintypes.BOOL
        dll.IsIconic.argtypes = [wintypes.HWND]
        dll.IsIconic.restype = wintypes.BOOL
        dll.IsWindow.argtypes = [wintypes.HWND]
        dll.IsWindow.restype = wintypes.BOOL
        dll.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        dll.ShowWindow.restype = wintypes.BOOL
        dll.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.c_void_p]
        dll.GetWindowThreadProcessId.restype = wintypes.DWORD
        dll.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
        dll.AttachThreadInput.restype = wintypes.BOOL
        dll.SystemParametersInfoW.argtypes = [
            wintypes.UINT, wintypes.UINT, ctypes.c_void_p, wintypes.UINT
        ]
        dll.SystemParametersInfoW.restype = wintypes.BOOL
        dll.keybd_event.argtypes = [
            wintypes.BYTE, wintypes.BYTE, wintypes.DWORD, ctypes.c_void_p
        ]
        dll.keybd_event.restype = None

        kernel.GetCurrentThreadId.argtypes = []
        kernel.GetCurrentThreadId.restype = wintypes.DWORD

        USER32, KERNEL32 = dll, kernel
        return USER32
    except Exception as e:
        logger.debug("user32 unavailable: %s", e)
        return None


def active_window():
    """
    Return the focused window as a plain int handle, or None.

    Capture this *before* showing a dialog so the focused application can be
    restored afterwards. A plain int is returned (rather than the ctypes
    object) so the value stays comparable and safe to hold across calls.
    """
    dll = user32()
    if dll is None:
        return None
    try:
        hwnd = dll.GetForegroundWindow()
        return int(hwnd) if hwnd else None
    except Exception as e:
        logger.debug("GetForegroundWindow failed: %s", e)
        return None


def foreground_matches(dll, hwnd) -> bool:
    """True when *hwnd* is currently the foreground window."""
    try:
        current = dll.GetForegroundWindow()
        return bool(current) and int(current) == int(hwnd)
    except Exception:
        return False


def foreground_thread(dll):
    """Return the thread id that owns the current foreground window, or 0."""
    try:
        current = dll.GetForegroundWindow()
        if not current:
            return 0
        return int(dll.GetWindowThreadProcessId(current, None))
    except Exception:
        return 0


def take_foreground_lock(dll):
    """
    Temporarily set the foreground lock timeout to zero.

    Returns the previous timeout so it can be handed to release_foreground_lock;
    None means nothing was changed and no restore is needed.
    """
    try:
        import ctypes
        from ctypes import wintypes

        previous = wintypes.DWORD()
        ok = dll.SystemParametersInfoW(
            SPI_GETFOREGROUNDLOCKTIMEOUT, 0, ctypes.byref(previous), 0
        )
        if not ok:
            return None
        dll.SystemParametersInfoW(
            SPI_SETFOREGROUNDLOCKTIMEOUT, 0, ctypes.c_void_p(0), SPIF_SENDCHANGE
        )
        return int(previous.value)
    except Exception as e:
        logger.debug("Could not clear foreground lock timeout: %s", e)
        return None


def release_foreground_lock(dll, previous) -> None:
    """Restore the foreground lock timeout saved by take_foreground_lock."""
    if previous is None:
        return
    try:
        import ctypes
        dll.SystemParametersInfoW(
            SPI_SETFOREGROUNDLOCKTIMEOUT,
            0,
            ctypes.c_void_p(previous),
            SPIF_SENDCHANGE,
        )
    except Exception:
        pass


def tap_alt(dll) -> None:
    """
    Inject a no-op Alt press/release.

    Windows grants SetForegroundWindow to the process that produced the most
    recent input event; the user's real keystrokes went to another application,
    so we manufacture one.

    Use sparingly. The tap lands in whatever window currently has focus, and a
    lone Alt opens the menu bar in many applications, so this runs only as a
    fallback after the attach/lock-timeout path has already failed.
    """
    try:
        dll.keybd_event(VK_MENU, 0, 0, None)
        dll.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, None)
    except Exception as e:
        logger.debug("Alt tap failed: %s", e)


def raise_window(hwnd, focus: bool = False, nudge: bool = False) -> bool:
    """
    Push *hwnd* to the foreground, defeating the Windows foreground lock.

    Args:
        hwnd: Target window handle.
        focus (bool): Also call SetFocus, giving the window keyboard focus
            rather than only activating it. Only meaningful for our own
            windows, since SetFocus is per input queue.
        nudge (bool): Inject a synthetic Alt tap first. Off by default; see
            tap_alt for why this is a fallback rather than routine.

    Returns:
        bool: True once the OS reports *hwnd* as the foreground window.
    """
    dll = user32()
    if dll is None or not hwnd:
        return False

    try:
        if not dll.IsWindow(hwnd):
            return False
        if dll.IsIconic(hwnd):
            dll.ShowWindow(hwnd, SW_RESTORE)
        else:
            dll.ShowWindow(hwnd, SW_SHOW)
    except Exception:
        pass

    # Attach to whoever owns the foreground *right now*. Attaching to the
    # target's own thread is what the earlier version got wrong: for our own
    # dialog that is the calling thread, and AttachThreadInput(t, t, TRUE) is
    # a no-op, so the foreground lock was never lifted.
    current_thread = 0
    target_thread = 0
    attached = False
    try:
        current_thread = int(KERNEL32.GetCurrentThreadId())
        target_thread = foreground_thread(dll)
        if target_thread and target_thread != current_thread:
            attached = bool(dll.AttachThreadInput(current_thread, target_thread, True))
    except Exception as e:
        logger.debug("AttachThreadInput failed: %s", e)

    previous_timeout = take_foreground_lock(dll)
    try:
        if nudge:
            tap_alt(dll)
        dll.BringWindowToTop(hwnd)
        dll.SetForegroundWindow(hwnd)
        dll.SetActiveWindow(hwnd)
        if focus:
            dll.SetFocus(hwnd)
        return foreground_matches(dll, hwnd)
    except Exception as e:
        logger.debug("raise_window failed: %s", e)
        return False
    finally:
        release_foreground_lock(dll, previous_timeout)
        if attached:
            try:
                dll.AttachThreadInput(current_thread, target_thread, False)
            except Exception:
                pass


def focus_dialog(widget, timeout: float = 0.5) -> bool:
    """
    Give a Qt window real keyboard focus, not just a flashing taskbar button.

    Qt's raise_()/activateWindow() are requests the OS may ignore when another
    process owns the foreground, which is exactly our situation when a snippet
    trigger fires while the user types elsewhere. Retries briefly, because the
    native window is not always ready to be activated on the first attempt.

    Returns:
        bool: True if the window reached the foreground.
    """
    try:
        widget.show()
        widget.raise_()
        widget.activateWindow()
    except Exception:
        pass

    if not IS_WINDOWS:
        return True

    dll = user32()
    if dll is None:
        return False

    try:
        hwnd = int(widget.winId())
    except Exception as e:
        logger.debug("Could not resolve dialog HWND: %s", e)
        return False

    deadline = time.monotonic() + max(0.0, timeout)
    attempt = 0
    while True:
        # Only start injecting Alt once the clean path has clearly failed.
        if raise_window(hwnd, focus=True, nudge=attempt >= 3):
            return True
        attempt += 1
        if time.monotonic() >= deadline:
            break
        time.sleep(0.02)

    logger.warning("Dialog did not reach the foreground after %d attempts", attempt)
    return False


def restore_focus(handle, timeout: float = 0.6) -> bool:
    """
    Return focus to a window captured earlier by active_window().

    Polls until the OS reports the switch has actually happened, because the
    caller normally starts synthesising keystrokes immediately afterwards and
    those would otherwise race the focus change. Returns True once *handle* is
    foreground, or False if it never got there within *timeout*.
    """
    if not handle:
        return False

    dll = user32()
    if dll is None:
        return False

    deadline = time.monotonic() + max(0.0, timeout)
    attempt = 0
    while True:
        if foreground_matches(dll, handle):
            return True

        raise_window(handle)
        attempt += 1

        if time.monotonic() >= deadline:
            break
        time.sleep(0.02)

    logger.debug("Focus was not restored to %s after %d attempts", handle, attempt)
    return False

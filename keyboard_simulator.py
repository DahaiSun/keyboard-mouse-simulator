import argparse
import ctypes
import json
import os
import re
import sys
import threading
import time
from ctypes import wintypes


if sys.platform != "win32":
    raise SystemExit("This script only works on Windows.")

# Declare DPI awareness so that all coordinate APIs (GetSystemMetrics,
# mouse hooks, SetCursorPos, SendInput) agree on physical pixel values.
# Without this, high-DPI displays cause position mismatches.
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
except (AttributeError, OSError):
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except (AttributeError, OSError):
        pass


INPUT_KEYBOARD = 1
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
MAPVK_VK_TO_VSC = 0

INPUT_MOUSE = 0
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_ABSOLUTE = 0x8000

WH_MOUSE_LL = 14
WH_KEYBOARD_LL = 13
WM_LBUTTONDOWN = 0x0201
WM_RBUTTONDOWN = 0x0204
WM_MBUTTONDOWN = 0x0207
WM_KEYDOWN = 0x0100
WM_QUIT_MSG = 0x0012
VK_F6 = 0x75
SM_CXSCREEN = 0
SM_CYSCREEN = 1

ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class INPUT_UNION(ctypes.Union):
    _fields_ = [
        ("mi", MOUSEINPUT),
        ("ki", KEYBDINPUT),
        ("hi", HARDWAREINPUT),
    ]


class INPUT(ctypes.Structure):
    _anonymous_ = ("value",)
    _fields_ = [
        ("type", wintypes.DWORD),
        ("value", INPUT_UNION),
    ]


class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("pt", wintypes.POINT),
        ("mouseData", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


HOOKPROC = ctypes.WINFUNCTYPE(
    ctypes.c_long, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM
)


user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
user32.SendInput.restype = wintypes.UINT
user32.MapVirtualKeyW.argtypes = (wintypes.UINT, wintypes.UINT)
user32.MapVirtualKeyW.restype = wintypes.UINT
user32.VkKeyScanW.argtypes = (wintypes.WCHAR,)
user32.VkKeyScanW.restype = ctypes.c_short
user32.EnumWindows.restype = wintypes.BOOL
user32.IsWindowVisible.argtypes = (wintypes.HWND,)
user32.IsWindowVisible.restype = wintypes.BOOL
user32.GetWindowTextLengthW.argtypes = (wintypes.HWND,)
user32.GetWindowTextLengthW.restype = ctypes.c_int
user32.GetWindowTextW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
user32.GetWindowTextW.restype = ctypes.c_int
user32.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.GetForegroundWindow.restype = wintypes.HWND
user32.IsWindow.argtypes = (wintypes.HWND,)
user32.IsWindow.restype = wintypes.BOOL
user32.ShowWindow.argtypes = (wintypes.HWND, ctypes.c_int)
user32.ShowWindow.restype = wintypes.BOOL
user32.IsIconic.argtypes = (wintypes.HWND,)
user32.IsIconic.restype = wintypes.BOOL
user32.SetForegroundWindow.argtypes = (wintypes.HWND,)
user32.SetForegroundWindow.restype = wintypes.BOOL
user32.BringWindowToTop.argtypes = (wintypes.HWND,)
user32.BringWindowToTop.restype = wintypes.BOOL
kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.QueryFullProcessImageNameW.argtypes = (
    wintypes.HANDLE,
    wintypes.DWORD,
    wintypes.LPWSTR,
    ctypes.POINTER(wintypes.DWORD),
)
kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
kernel32.CloseHandle.restype = wintypes.BOOL

user32.SetWindowsHookExW.argtypes = (
    ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD,
)
user32.SetWindowsHookExW.restype = ctypes.c_void_p
user32.UnhookWindowsHookEx.argtypes = (ctypes.c_void_p,)
user32.UnhookWindowsHookEx.restype = wintypes.BOOL
user32.CallNextHookEx.argtypes = (
    ctypes.c_void_p, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM,
)
user32.CallNextHookEx.restype = ctypes.c_long
user32.GetMessageW.argtypes = (
    ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT,
)
user32.GetMessageW.restype = wintypes.BOOL
user32.TranslateMessage.argtypes = (ctypes.POINTER(wintypes.MSG),)
user32.TranslateMessage.restype = wintypes.BOOL
user32.DispatchMessageW.argtypes = (ctypes.POINTER(wintypes.MSG),)
user32.DispatchMessageW.restype = ctypes.c_long
user32.PostThreadMessageW.argtypes = (
    wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
)
user32.PostThreadMessageW.restype = wintypes.BOOL
user32.SetCursorPos.argtypes = (ctypes.c_int, ctypes.c_int)
user32.SetCursorPos.restype = wintypes.BOOL
user32.GetSystemMetrics.argtypes = (ctypes.c_int,)
user32.GetSystemMetrics.restype = ctypes.c_int
kernel32.GetCurrentThreadId.argtypes = ()
kernel32.GetCurrentThreadId.restype = wintypes.DWORD

WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user32.EnumWindows.argtypes = (WNDENUMPROC, wintypes.LPARAM)


NAMED_KEYS = {
    "backspace": 0x08,
    "tab": 0x09,
    "enter": 0x0D,
    "shift": 0x10,
    "ctrl": 0x11,
    "alt": 0x12,
    "pause": 0x13,
    "capslock": 0x14,
    "escape": 0x1B,
    "space": 0x20,
    "pageup": 0x21,
    "pagedown": 0x22,
    "end": 0x23,
    "home": 0x24,
    "left": 0x25,
    "up": 0x26,
    "right": 0x27,
    "down": 0x28,
    "printscreen": 0x2C,
    "insert": 0x2D,
    "delete": 0x2E,
    "lwin": 0x5B,
    "rwin": 0x5C,
    "menu": 0x5D,
    "numlock": 0x90,
    "scrolllock": 0x91,
    "lshift": 0xA0,
    "rshift": 0xA1,
    "lctrl": 0xA2,
    "rctrl": 0xA3,
    "lalt": 0xA4,
    "ralt": 0xA5,
    "numpad0": 0x60,
    "numpad1": 0x61,
    "numpad2": 0x62,
    "numpad3": 0x63,
    "numpad4": 0x64,
    "numpad5": 0x65,
    "numpad6": 0x66,
    "numpad7": 0x67,
    "numpad8": 0x68,
    "numpad9": 0x69,
    "multiply": 0x6A,
    "add": 0x6B,
    "separator": 0x6C,
    "subtract": 0x6D,
    "decimal": 0x6E,
    "divide": 0x6F,
}

for index in range(1, 25):
    NAMED_KEYS[f"f{index}"] = 0x6F + index


KEY_ALIASES = {
    "return": "enter",
    "esc": "escape",
    "del": "delete",
    "ins": "insert",
    "pgup": "pageup",
    "pgdn": "pagedown",
    "bksp": "backspace",
    "spacebar": "space",
    "control": "ctrl",
    "ctl": "ctrl",
    "option": "alt",
    "cmd": "lwin",
    "win": "lwin",
    "windows": "lwin",
    "apps": "menu",
    "plus": "+",
    "minus": "-",
    "equals": "=",
    "comma": ",",
    "period": ".",
    "dot": ".",
    "slash": "/",
    "forwardslash": "/",
    "semicolon": ";",
    "quote": "'",
    "apostrophe": "'",
    "backtick": "`",
    "grave": "`",
    "lbracket": "[",
    "rbracket": "]",
    "leftbracket": "[",
    "rightbracket": "]",
    "backslash": "\\",
}

TK_SHIFT_MASK = 0x0001
TK_CONTROL_MASK = 0x0004
TK_ALT_MASK = 0x0008
TK_WIN_MASK = 0x0040

MODIFIER_DISPLAY_ORDER = ["ctrl", "alt", "shift", "win"]
MODIFIER_TOKENS = set(MODIFIER_DISPLAY_ORDER)
PRESS_SEQUENCE_SEPARATOR = ", "
MAX_PRESS_KEYS = 2
SW_RESTORE = 9
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


class ActionCancelled(Exception):
    pass

TK_KEYSYM_ALIASES = {
    "backspace": "backspace",
    "tab": "tab",
    "return": "enter",
    "enter": "enter",
    "escape": "escape",
    "space": "space",
    "prior": "pageup",
    "next": "pagedown",
    "left": "left",
    "right": "right",
    "up": "up",
    "down": "down",
    "home": "home",
    "end": "end",
    "insert": "insert",
    "delete": "delete",
    "print": "printscreen",
    "menu": "menu",
    "control_l": "ctrl",
    "control_r": "ctrl",
    "shift_l": "shift",
    "shift_r": "shift",
    "alt_l": "alt",
    "alt_r": "alt",
    "option_l": "alt",
    "option_r": "alt",
    "super_l": "win",
    "super_r": "win",
    "win_l": "win",
    "win_r": "win",
    "kp_enter": "enter",
    "kp_add": "add",
    "kp_subtract": "subtract",
    "kp_multiply": "multiply",
    "kp_divide": "divide",
    "kp_decimal": "decimal",
    "kp_separator": "separator",
    "equal": "equals",
    "plus": "plus",
    "minus": "minus",
    "comma": "comma",
    "period": "period",
    "slash": "slash",
    "backslash": "backslash",
    "semicolon": "semicolon",
    "colon": ":",
    "apostrophe": "'",
    "quotedbl": "\"",
    "quoteleft": "backtick",
    "asciitilde": "~",
    "bracketleft": "[",
    "braceleft": "{",
    "bracketright": "]",
    "braceright": "}",
}

EXTENDED_KEYS = {
    NAMED_KEYS["pageup"],
    NAMED_KEYS["pagedown"],
    NAMED_KEYS["end"],
    NAMED_KEYS["home"],
    NAMED_KEYS["left"],
    NAMED_KEYS["up"],
    NAMED_KEYS["right"],
    NAMED_KEYS["down"],
    NAMED_KEYS["insert"],
    NAMED_KEYS["delete"],
    NAMED_KEYS["lwin"],
    NAMED_KEYS["rwin"],
    NAMED_KEYS["menu"],
    NAMED_KEYS["rctrl"],
    NAMED_KEYS["ralt"],
    NAMED_KEYS["divide"],
}

SHIFT_KEY = NAMED_KEYS["shift"]
CTRL_KEY = NAMED_KEYS["ctrl"]
ALT_KEY = NAMED_KEYS["alt"]


def ensure_non_negative(name: str, value: float) -> None:
    if value < 0:
        raise ValueError(f"{name} cannot be negative.")


def ensure_positive(name: str, value: float) -> None:
    if value <= 0:
        raise ValueError(f"{name} must be greater than 0.")


def normalize_key_name(key_spec: str) -> str:
    normalized = key_spec.strip().lower()
    return KEY_ALIASES.get(normalized, normalized)


def vk_combo_for_char(character: str) -> list[int]:
    key_data = user32.VkKeyScanW(character)
    if key_data == -1:
        raise ValueError(f"Unsupported key: {character!r}")

    virtual_key = key_data & 0xFF
    shift_state = (key_data >> 8) & 0xFF
    combo: list[int] = []

    if shift_state & 0x01:
        combo.append(SHIFT_KEY)
    if shift_state & 0x02:
        combo.append(CTRL_KEY)
    if shift_state & 0x04:
        combo.append(ALT_KEY)

    combo.append(virtual_key)
    return combo


def resolve_key_spec(key_spec: str) -> list[int]:
    cleaned = key_spec.strip()
    if not cleaned:
        raise ValueError("Key cannot be empty.")

    if len(cleaned) == 1:
        return vk_combo_for_char(cleaned)

    normalized = normalize_key_name(cleaned)
    if normalized in NAMED_KEYS:
        return [NAMED_KEYS[normalized]]
    if len(normalized) == 1:
        return vk_combo_for_char(normalized)

    raise ValueError(f"Unknown key name: {key_spec}")


def expand_hotkey_specs(keys: list[str]) -> list[str]:
    if len(keys) == 1 and "+" in keys[0] and keys[0] != "+":
        return [part for part in keys[0].split("+") if part]
    return keys


def dedupe_preserve_order(values: list[int]) -> list[int]:
    seen: set[int] = set()
    result: list[int] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def display_key_token_from_keysym(keysym: str, char: str) -> str | None:
    normalized_keysym = keysym.strip().lower()
    if not normalized_keysym:
        return None

    if normalized_keysym in TK_KEYSYM_ALIASES:
        return TK_KEYSYM_ALIASES[normalized_keysym]

    if normalized_keysym.startswith("kp_") and normalized_keysym[3:].isdigit():
        return f"numpad{normalized_keysym[3:]}"

    if normalized_keysym.startswith("f") and normalized_keysym[1:].isdigit():
        return normalized_keysym

    if len(char) == 1 and char.isprintable() and char not in {" ", "\t", "\r", "\n"}:
        if char == "+":
            return "plus"
        if char == ",":
            return "comma"
        if char == ".":
            return "period"
        if char == "/":
            return "slash"
        if char == "\\":
            return "backslash"
        if char == ";":
            return "semicolon"
        if char == "`":
            return "backtick"
        return char.lower() if char.isalpha() else char

    if len(normalized_keysym) == 1:
        return normalized_keysym

    return None


def modifiers_from_tk_state(state: int) -> list[str]:
    modifiers: list[str] = []
    if state & TK_CONTROL_MASK:
        modifiers.append("ctrl")
    if state & TK_ALT_MASK:
        modifiers.append("alt")
    if state & TK_SHIFT_MASK:
        modifiers.append("shift")
    if state & TK_WIN_MASK:
        modifiers.append("win")
    return modifiers


def ordered_modifier_tokens(tokens: list[str]) -> list[str]:
    result: list[str] = []
    for token in MODIFIER_DISPLAY_ORDER:
        if token in tokens and token not in result:
            result.append(token)
    return result


def recorded_value_from_tk_event(event, combo_mode: bool) -> str | None:
    key_token = display_key_token_from_keysym(getattr(event, "keysym", ""), getattr(event, "char", ""))
    if not key_token:
        return None

    modifiers = modifiers_from_tk_state(getattr(event, "state", 0))
    if key_token in MODIFIER_TOKENS:
        if key_token not in modifiers:
            modifiers.append(key_token)
        return "+".join(ordered_modifier_tokens(modifiers))

    if not combo_mode:
        return key_token

    ordered_modifiers = ordered_modifier_tokens(modifiers)
    if ordered_modifiers:
        return "+".join(ordered_modifiers + [key_token])
    return key_token


def parse_press_specs(keys: str | list[str]) -> list[str]:
    if isinstance(keys, list):
        parts = [part.strip() for part in keys if part.strip()]
    else:
        raw_text = keys.strip()
        if not raw_text:
            raise ValueError("Key cannot be empty.")
        if "," in raw_text:
            parts = [part.strip() for part in raw_text.split(",") if part.strip()]
        else:
            parts = [part.strip() for part in re.split(r"\s+", raw_text) if part.strip()]

    if not parts:
        raise ValueError("Key cannot be empty.")
    if len(parts) > MAX_PRESS_KEYS:
        raise ValueError(f"Press key supports at most {MAX_PRESS_KEYS} keys.")

    return parts


def format_press_specs(keys: list[str]) -> str:
    return PRESS_SEQUENCE_SEPARATOR.join(keys)


def append_press_recorded_value(current_value: str, new_key: str) -> tuple[str, bool]:
    if not new_key:
        return current_value, False

    existing_keys = [part.strip() for part in current_value.split(",") if part.strip()]
    if len(existing_keys) >= MAX_PRESS_KEYS:
        return current_value, False

    existing_keys.append(new_key)
    return format_press_specs(existing_keys), True


def get_window_text(hwnd: int) -> str:
    length = user32.GetWindowTextLengthW(hwnd)
    if length <= 0:
        return ""

    buffer = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buffer, len(buffer))
    return buffer.value.strip()


def get_process_name(pid: int) -> str:
    process_handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not process_handle:
        return f"pid {pid}"

    try:
        buffer_size = wintypes.DWORD(1024)
        buffer = ctypes.create_unicode_buffer(buffer_size.value)
        if kernel32.QueryFullProcessImageNameW(process_handle, 0, buffer, ctypes.byref(buffer_size)):
            return os.path.basename(buffer.value) or buffer.value
    finally:
        kernel32.CloseHandle(process_handle)

    return f"pid {pid}"


def list_visible_windows() -> list[dict[str, object]]:
    windows: list[dict[str, object]] = []

    @WNDENUMPROC
    def enum_windows_callback(hwnd, _lparam) -> bool:
        if not user32.IsWindowVisible(hwnd):
            return True

        title = get_window_text(hwnd)
        if not title:
            return True

        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        process_name = get_process_name(pid.value)
        windows.append(
            {
                "hwnd": int(hwnd),
                "title": title,
                "pid": pid.value,
                "process_name": process_name,
            }
        )
        return True

    if not user32.EnumWindows(enum_windows_callback, 0):
        raise ctypes.WinError(ctypes.get_last_error())

    return windows


def activate_window(hwnd: int) -> bool:
    if not hwnd or not user32.IsWindow(hwnd):
        return False

    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)
    else:
        user32.ShowWindow(hwnd, 5)

    user32.BringWindowToTop(hwnd)
    user32.SetForegroundWindow(hwnd)
    foreground_hwnd = user32.GetForegroundWindow() or 0
    return foreground_hwnd == hwnd


def raise_if_cancelled(stop_event: threading.Event | None) -> None:
    if stop_event and stop_event.is_set():
        raise ActionCancelled("Action stopped.")


def sleep_with_cancel(seconds: float, stop_event: threading.Event | None, chunk: float = 0.05) -> None:
    if seconds <= 0:
        raise_if_cancelled(stop_event)
        return

    if not stop_event:
        time.sleep(seconds)
        return

    deadline = time.monotonic() + seconds
    while True:
        raise_if_cancelled(stop_event)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return
        time.sleep(min(chunk, remaining))


def keyboard_input(virtual_key: int, key_up: bool = False) -> INPUT:
    flags = KEYEVENTF_KEYUP if key_up else 0
    if virtual_key in EXTENDED_KEYS:
        flags |= KEYEVENTF_EXTENDEDKEY

    return INPUT(
        type=INPUT_KEYBOARD,
        ki=KEYBDINPUT(
            wVk=virtual_key,
            wScan=user32.MapVirtualKeyW(virtual_key, MAPVK_VK_TO_VSC),
            dwFlags=flags,
            time=0,
            dwExtraInfo=0,
        ),
    )


def unicode_inputs(character: str) -> list[INPUT]:
    encoded = character.encode("utf-16-le")
    code_units = [
        encoded[index] | (encoded[index + 1] << 8)
        for index in range(0, len(encoded), 2)
    ]

    inputs: list[INPUT] = []
    for code_unit in code_units:
        inputs.append(
            INPUT(
                type=INPUT_KEYBOARD,
                ki=KEYBDINPUT(
                    wVk=0,
                    wScan=code_unit,
                    dwFlags=KEYEVENTF_UNICODE,
                    time=0,
                    dwExtraInfo=0,
                ),
            )
        )
        inputs.append(
            INPUT(
                type=INPUT_KEYBOARD,
                ki=KEYBDINPUT(
                    wVk=0,
                    wScan=code_unit,
                    dwFlags=KEYEVENTF_UNICODE | KEYEVENTF_KEYUP,
                    time=0,
                    dwExtraInfo=0,
                ),
            )
        )

    return inputs


def send_inputs(inputs: list[INPUT]) -> None:
    if not inputs:
        return

    input_array = (INPUT * len(inputs))(*inputs)
    sent = user32.SendInput(len(inputs), input_array, ctypes.sizeof(INPUT))
    if sent != len(inputs):
        raise ctypes.WinError(ctypes.get_last_error())


def tap_combo(combo: list[int]) -> None:
    key_downs = [keyboard_input(key_code) for key_code in combo]
    key_ups = [keyboard_input(key_code, key_up=True) for key_code in reversed(combo)]
    send_inputs(key_downs + key_ups)


def hold_combo(combo: list[int], seconds: float, stop_event: threading.Event | None = None) -> None:
    send_inputs([keyboard_input(key_code) for key_code in combo])
    try:
        sleep_with_cancel(seconds, stop_event)
    finally:
        send_inputs([keyboard_input(key_code, key_up=True) for key_code in reversed(combo)])


def type_text(content: str, interval: float, stop_event: threading.Event | None = None) -> None:
    for character in content:
        raise_if_cancelled(stop_event)
        if character == "\n":
            tap_combo([NAMED_KEYS["enter"]])
        elif character == "\t":
            tap_combo([NAMED_KEYS["tab"]])
        else:
            send_inputs(unicode_inputs(character))

        if interval:
            sleep_with_cancel(interval, stop_event)


def mouse_click_at(
    x: int, y: int, button: str = "left", stop_event: threading.Event | None = None,
) -> None:
    """Move cursor to (x, y) and perform a mouse click.

    Uses SetCursorPos for positioning (works with raw screen coordinates
    from the low-level mouse hook) and SendInput for the click events.
    """
    raise_if_cancelled(stop_event)

    # Move the cursor first — this is the most reliable method because
    # SetCursorPos takes direct screen-pixel coordinates, avoiding the
    # 0-65535 normalised-coordinate math that MOUSEEVENTF_ABSOLUTE needs.
    user32.SetCursorPos(x, y)

    if button == "right":
        down_flag, up_flag = MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP
    elif button == "middle":
        down_flag, up_flag = MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP
    else:
        down_flag, up_flag = MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP

    down = INPUT(
        type=INPUT_MOUSE,
        mi=MOUSEINPUT(dx=0, dy=0, mouseData=0, dwFlags=down_flag, time=0, dwExtraInfo=0),
    )
    up = INPUT(
        type=INPUT_MOUSE,
        mi=MOUSEINPUT(dx=0, dy=0, mouseData=0, dwFlags=up_flag, time=0, dwExtraInfo=0),
    )
    send_inputs([down, up])


class ClickRecorder:
    """Records mouse clicks globally using low-level Windows hooks.

    Press F6 to stop recording.  Each recorded click stores the screen
    coordinates, the button used, and the delay since the previous click.
    """

    LLMHF_INJECTED = 0x01

    def __init__(self) -> None:
        self.recorded_clicks: list[dict[str, object]] = []
        self._recording = False
        self._thread: threading.Thread | None = None
        self._thread_id: int = 0
        self._last_click_time: float = 0.0
        self._on_click = None
        self._on_stop = None
        self._on_error = None
        self._stop_requested = False
        # prevent garbage collection of the callback closures
        self._mouse_hook_ref: HOOKPROC | None = None
        self._kb_hook_ref: HOOKPROC | None = None

    @property
    def is_recording(self) -> bool:
        return self._recording

    def start(self, on_click=None, on_stop=None, on_error=None) -> None:
        if self._recording:
            return
        self._on_click = on_click
        self._on_stop = on_stop
        self._on_error = on_error
        self.recorded_clicks = []
        self._stop_requested = False
        self._recording = True
        self._thread = threading.Thread(target=self._run_hook_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if not self._recording:
            return
        self._stop_requested = True
        if self._thread_id:
            user32.PostThreadMessageW(self._thread_id, WM_QUIT_MSG, 0, 0)

    def _run_hook_loop(self) -> None:
        self._thread_id = kernel32.GetCurrentThreadId()
        self._last_click_time = time.monotonic()

        self._mouse_hook_ref = HOOKPROC(self._mouse_proc)
        self._kb_hook_ref = HOOKPROC(self._kb_proc)

        m_hook = user32.SetWindowsHookExW(WH_MOUSE_LL, self._mouse_hook_ref, None, 0)
        k_hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._kb_hook_ref, None, 0)
        if not m_hook or not k_hook:
            error_code = ctypes.get_last_error()
            if m_hook:
                user32.UnhookWindowsHookEx(m_hook)
            if k_hook:
                user32.UnhookWindowsHookEx(k_hook)
            self._recording = False
            self._thread_id = 0
            self._stop_requested = False
            self._mouse_hook_ref = None
            self._kb_hook_ref = None
            if self._on_error:
                self._on_error(f"Failed to install recording hooks. Windows error: {error_code}")
            return

        if not self._stop_requested:
            msg = wintypes.MSG()
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))

        if m_hook:
            user32.UnhookWindowsHookEx(m_hook)
        if k_hook:
            user32.UnhookWindowsHookEx(k_hook)

        self._recording = False
        self._thread_id = 0
        self._stop_requested = False
        self._mouse_hook_ref = None
        self._kb_hook_ref = None
        if self._on_stop:
            self._on_stop()

    def _mouse_proc(self, nCode, wParam, lParam):
        if nCode >= 0 and wParam in (WM_LBUTTONDOWN, WM_RBUTTONDOWN, WM_MBUTTONDOWN):
            info = ctypes.cast(lParam, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
            # skip events injected by SendInput (our own playback)
            if info.flags & self.LLMHF_INJECTED:
                return user32.CallNextHookEx(None, nCode, wParam, lParam)

            now = time.monotonic()
            delay = now - self._last_click_time if self.recorded_clicks else 0.0
            self._last_click_time = now

            btn = {
                WM_LBUTTONDOWN: "left",
                WM_RBUTTONDOWN: "right",
                WM_MBUTTONDOWN: "middle",
            }.get(wParam, "left")
            click = {
                "x": info.pt.x,
                "y": info.pt.y,
                "button": btn,
                "delay": round(delay, 3),
            }
            self.recorded_clicks.append(click)
            if self._on_click:
                self._on_click(click)

        return user32.CallNextHookEx(None, nCode, wParam, lParam)

    def _kb_proc(self, nCode, wParam, lParam):
        if nCode >= 0 and wParam == WM_KEYDOWN:
            info = ctypes.cast(lParam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
            if info.vkCode in (VK_F6, 0x1B):  # F6 or Escape
                self.stop()
                return 1  # consume the key
        return user32.CallNextHookEx(None, nCode, wParam, lParam)


def run_click_flow(
    clicks: list[dict[str, object]],
    repeat: int = 1,
    speed: float = 1.0,
    use_delays: bool = True,
    fixed_interval: float = 0.5,
    cycle_interval: float = 1.0,
    stop_event: threading.Event | None = None,
) -> None:
    """Replay a list of recorded mouse clicks."""
    if not clicks:
        raise ValueError("No clicks to replay.")
    ensure_positive("repeat", repeat)
    ensure_positive("speed", speed)

    for _cycle in range(repeat):
        # pause between cycles (not before the first one)
        if _cycle > 0 and cycle_interval > 0:
            sleep_with_cancel(cycle_interval, stop_event)

        for index, click in enumerate(clicks):
            raise_if_cancelled(stop_event)

            # determine delay before this click
            if index == 0:
                wait = 0.0
            elif use_delays:
                wait = float(click.get("delay", 0)) / speed
            else:
                wait = fixed_interval / speed

            if wait > 0:
                sleep_with_cancel(wait, stop_event)

            mouse_click_at(
                int(click["x"]),
                int(click["y"]),
                str(click.get("button", "left")),
                stop_event=stop_event,
            )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Simulate keyboard input on Windows.")
    parser.add_argument(
        "--console",
        action="store_true",
        help="Open console prompts instead of the GUI when no subcommand is provided.",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.0,
        help="Wait for N seconds before sending input.",
    )

    subcommands = parser.add_subparsers(dest="command")

    press_parser = subcommands.add_parser("press", help="Press one or two keys in sequence.")
    press_parser.add_argument(
        "keys",
        nargs="+",
        help="Key names like enter, f5, a, or two keys such as enter tab.",
    )
    press_parser.add_argument("--repeat", type=int, default=1, help="Number of times to repeat.")
    press_parser.add_argument(
        "--interval",
        type=float,
        default=0.05,
        help="Delay between repeated presses in seconds.",
    )

    hotkey_parser = subcommands.add_parser("hotkey", help="Press a hotkey combination.")
    hotkey_parser.add_argument(
        "keys",
        nargs="+",
        help="Example: ctrl c or ctrl+shift+s",
    )
    hotkey_parser.add_argument("--repeat", type=int, default=1, help="Number of times to repeat.")
    hotkey_parser.add_argument(
        "--interval",
        type=float,
        default=0.05,
        help="Delay between repeated hotkeys in seconds.",
    )

    text_parser = subcommands.add_parser("text", help="Type text into the focused window.")
    text_parser.add_argument("content", help="Wrap text in quotes if it contains spaces.")
    text_parser.add_argument(
        "--interval",
        type=float,
        default=0.02,
        help="Delay between characters in seconds.",
    )

    hold_parser = subcommands.add_parser("hold", help="Hold a key for a number of seconds.")
    hold_parser.add_argument("key", help="A key name like w, shift, or left.")
    hold_parser.add_argument(
        "--seconds",
        type=float,
        default=1.0,
        help="How long to hold the key down.",
    )

    return parser


def prompt_float(label: str, default: float, minimum: float = 0.0) -> float:
    while True:
        raw = input(f"{label} [{default}]: ").strip()
        if not raw:
            return default
        try:
            value = float(raw)
        except ValueError:
            print("Please enter a valid number.")
            continue
        if value < minimum:
            print(f"Value must be >= {minimum}.")
            continue
        return value


def prompt_int(label: str, default: int, minimum: int = 1) -> int:
    while True:
        raw = input(f"{label} [{default}]: ").strip()
        if not raw:
            return default
        try:
            value = int(raw)
        except ValueError:
            print("Please enter a valid integer.")
            continue
        if value < minimum:
            print(f"Value must be >= {minimum}.")
            continue
        return value


def interactive_mode() -> None:
    print("Keyboard simulator interactive mode")
    print("1. Press a key")
    print("2. Press a hotkey")
    print("3. Type text")
    print("4. Hold a key")

    while True:
        choice = input("Choose an action [1-4]: ").strip()
        if choice in {"1", "2", "3", "4"}:
            break
        print("Please choose 1, 2, 3, or 4.")

    delay = prompt_float("Delay before start (seconds)", 0.0, 0.0)
    if delay:
        time.sleep(delay)

    if choice == "1":
        key = input("Key or up to two keys (example: a or enter tab): ").strip()
        repeat = prompt_int("Repeat count", 1, 1)
        interval = prompt_float("Interval between presses (seconds)", 0.05, 0.0)
        run_press(key, repeat, interval)
    elif choice == "2":
        keys_text = input("Hotkey (example: ctrl+c or ctrl+shift+s): ").strip()
        repeat = prompt_int("Repeat count", 1, 1)
        interval = prompt_float("Interval between hotkeys (seconds)", 0.05, 0.0)
        run_hotkey([keys_text], repeat, interval)
    elif choice == "3":
        content = input("Text to type: ")
        interval = prompt_float("Interval between characters (seconds)", 0.02, 0.0)
        type_text(content, interval)
    elif choice == "4":
        key = input("Key to hold (example: w, shift, left): ").strip()
        seconds = prompt_float("Hold duration (seconds)", 1.0, 0.0)
        run_hold(key, seconds)


def launch_gui() -> None:
    try:
        import tkinter as tk
        from tkinter import messagebox, ttk
    except ImportError as error:
        raise SystemExit("Tkinter is not available on this Python installation.") from error

    class KeyboardSimulatorApp:
        def __init__(self, root: "tk.Tk") -> None:
            self.root = root
            self.root.title("Keyboard & Mouse Simulator")
            self.root.resizable(False, False)

            self.mode_var = tk.StringVar(value="press")
            self.delay_var = tk.StringVar(value="3")
            self.minimize_var = tk.BooleanVar(value=True)
            self.use_selected_window_var = tk.BooleanVar(value=False)
            self.target_window_var = tk.StringVar(value="")

            self.press_key_var = tk.StringVar(value="a")
            self.press_repeat_var = tk.StringVar(value="1")
            self.press_interval_var = tk.StringVar(value="0.05")

            self.hotkey_var = tk.StringVar(value="ctrl+c")
            self.hotkey_repeat_var = tk.StringVar(value="1")
            self.hotkey_interval_var = tk.StringVar(value="0.05")

            self.text_interval_var = tk.StringVar(value="0.02")

            self.hold_key_var = tk.StringVar(value="w")
            self.hold_seconds_var = tk.StringVar(value="1.0")

            self.clickflow_repeat_var = tk.StringVar(value="1")
            self.clickflow_speed_var = tk.StringVar(value="1.0")
            self.clickflow_use_delays_var = tk.BooleanVar(value=True)
            self.clickflow_interval_var = tk.StringVar(value="0.5")
            self.clickflow_cycle_interval_var = tk.StringVar(value="1.0")
            self.click_recorder = ClickRecorder()
            self._recording_overlay: tk.Toplevel | None = None
            self._recording_count_var: tk.StringVar | None = None
            self._countdown_window: tk.Toplevel | None = None

            self.status_var = tk.StringVar(
                value="Set the action, click Start, then switch to the target window."
            )
            self.worker: threading.Thread | None = None
            self.stop_event = threading.Event()
            self.mode_frames: dict[str, "ttk.Frame"] = {}
            self.window_targets: list[dict[str, object]] = []

            self.build_ui(tk, ttk)
            self.refresh_window_list()
            self.update_mode_fields()

        def build_ui(self, tk_module, ttk_module) -> None:
            container = ttk_module.Frame(self.root, padding=14)
            container.grid(sticky="nsew")

            title = ttk_module.Label(
                container,
                text="Keyboard Simulator",
                font=("Segoe UI", 13, "bold"),
            )
            title.grid(row=0, column=0, sticky="w")

            hint = ttk_module.Label(
                container,
                text="The input is sent to the currently focused window. Use a delay so you can switch windows.",
                wraplength=420,
                justify="left",
            )
            hint.grid(row=1, column=0, sticky="w", pady=(4, 12))

            common_frame = ttk_module.LabelFrame(container, text="General", padding=10)
            common_frame.grid(row=2, column=0, sticky="ew")
            common_frame.columnconfigure(1, weight=1)

            ttk_module.Label(common_frame, text="Delay (seconds)").grid(row=0, column=0, sticky="w")
            ttk_module.Entry(common_frame, textvariable=self.delay_var, width=12).grid(
                row=0, column=1, sticky="w"
            )

            ttk_module.Checkbutton(
                common_frame,
                text="Auto minimize the window before sending keys",
                variable=self.minimize_var,
            ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(8, 0))

            target_frame = ttk_module.LabelFrame(container, text="Target Window", padding=10)
            target_frame.grid(row=3, column=0, sticky="ew", pady=(12, 0))
            target_frame.columnconfigure(1, weight=1)

            ttk_module.Checkbutton(
                target_frame,
                text="Use selected window",
                variable=self.use_selected_window_var,
            ).grid(row=0, column=0, columnspan=3, sticky="w")

            ttk_module.Label(target_frame, text="Window").grid(row=1, column=0, sticky="w", pady=(8, 0))
            self.target_combo = ttk_module.Combobox(
                target_frame,
                textvariable=self.target_window_var,
                state="readonly",
                width=54,
            )
            self.target_combo.grid(row=1, column=1, sticky="ew", pady=(8, 0))
            self.target_combo.bind("<<ComboboxSelected>>", self.handle_target_selected)
            ttk_module.Button(
                target_frame,
                text="Refresh",
                command=self.refresh_window_list,
            ).grid(row=1, column=2, sticky="w", padx=(8, 0), pady=(8, 0))

            ttk_module.Label(
                target_frame,
                text="Choose a program window here if you want the script to activate it automatically before typing.",
                wraplength=420,
                justify="left",
            ).grid(row=2, column=0, columnspan=3, sticky="w", pady=(6, 0))

            mode_frame = ttk_module.LabelFrame(container, text="Action", padding=10)
            mode_frame.grid(row=4, column=0, sticky="ew", pady=(12, 0))

            selector = ttk_module.Frame(mode_frame)
            selector.grid(row=0, column=0, sticky="w")
            for index, (label, value) in enumerate(
                [
                    ("Press key", "press"),
                    ("Hotkey", "hotkey"),
                    ("Type text", "text"),
                    ("Hold key", "hold"),
                    ("Click Flow", "clickflow"),
                ]
            ):
                ttk_module.Radiobutton(
                    selector,
                    text=label,
                    value=value,
                    variable=self.mode_var,
                    command=self.update_mode_fields,
                ).grid(row=0, column=index, sticky="w", padx=(0, 10))

            panels = ttk_module.Frame(mode_frame)
            panels.grid(row=1, column=0, sticky="ew", pady=(12, 0))
            panels.columnconfigure(1, weight=1)

            press_frame = ttk_module.Frame(panels)
            ttk_module.Label(press_frame, text="Keys").grid(row=0, column=0, sticky="w")
            press_entry = ttk_module.Entry(press_frame, textvariable=self.press_key_var, width=24)
            press_entry.grid(row=0, column=1, sticky="w")
            ttk_module.Button(
                press_frame,
                text="Clear",
                command=lambda: self.clear_recording(self.press_key_var),
            ).grid(row=0, column=2, sticky="w", padx=(8, 0))
            self.bind_capture_entry(
                press_entry,
                self.press_key_var,
                combo_mode=False,
                focus_message="Press up to two keys. They will be sent in order.",
            )
            ttk_module.Label(
                press_frame,
                text="Click the box and press up to two keys to record a sequence.",
            ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(4, 0))
            ttk_module.Label(press_frame, text="Repeat").grid(row=2, column=0, sticky="w", pady=(8, 0))
            ttk_module.Entry(press_frame, textvariable=self.press_repeat_var, width=12).grid(
                row=2, column=1, sticky="w", pady=(8, 0)
            )
            ttk_module.Label(press_frame, text="Interval (seconds)").grid(row=3, column=0, sticky="w", pady=(8, 0))
            ttk_module.Entry(press_frame, textvariable=self.press_interval_var, width=12).grid(
                row=3, column=1, sticky="w", pady=(8, 0)
            )
            self.mode_frames["press"] = press_frame

            hotkey_frame = ttk_module.Frame(panels)
            ttk_module.Label(hotkey_frame, text="Hotkey").grid(row=0, column=0, sticky="w")
            hotkey_entry = ttk_module.Entry(hotkey_frame, textvariable=self.hotkey_var, width=24)
            hotkey_entry.grid(row=0, column=1, sticky="w")
            ttk_module.Button(
                hotkey_frame,
                text="Clear",
                command=lambda: self.clear_recording(self.hotkey_var),
            ).grid(row=0, column=2, sticky="w", padx=(8, 0))
            self.bind_capture_entry(
                hotkey_entry,
                self.hotkey_var,
                combo_mode=True,
                focus_message="Press the hotkey combination you want to record.",
            )
            ttk_module.Label(
                hotkey_frame,
                text="Click the box and press the keyboard combination directly.",
            ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(4, 0))
            ttk_module.Label(
                hotkey_frame,
                text="Examples: ctrl+c, ctrl+shift+s, alt+tab",
            ).grid(row=2, column=0, columnspan=3, sticky="w", pady=(2, 0))
            ttk_module.Label(hotkey_frame, text="Repeat").grid(row=3, column=0, sticky="w", pady=(8, 0))
            ttk_module.Entry(hotkey_frame, textvariable=self.hotkey_repeat_var, width=12).grid(
                row=3, column=1, sticky="w", pady=(8, 0)
            )
            ttk_module.Label(hotkey_frame, text="Interval (seconds)").grid(row=4, column=0, sticky="w", pady=(8, 0))
            ttk_module.Entry(hotkey_frame, textvariable=self.hotkey_interval_var, width=12).grid(
                row=4, column=1, sticky="w", pady=(8, 0)
            )
            self.mode_frames["hotkey"] = hotkey_frame

            text_frame = ttk_module.Frame(panels)
            ttk_module.Label(text_frame, text="Text").grid(row=0, column=0, sticky="nw")
            self.text_widget = tk_module.Text(text_frame, width=36, height=6, wrap="word")
            self.text_widget.grid(row=0, column=1, sticky="w")
            ttk_module.Label(text_frame, text="Interval (seconds)").grid(row=1, column=0, sticky="w", pady=(8, 0))
            ttk_module.Entry(text_frame, textvariable=self.text_interval_var, width=12).grid(
                row=1, column=1, sticky="w", pady=(8, 0)
            )
            self.mode_frames["text"] = text_frame

            hold_frame = ttk_module.Frame(panels)
            ttk_module.Label(hold_frame, text="Key").grid(row=0, column=0, sticky="w")
            hold_entry = ttk_module.Entry(hold_frame, textvariable=self.hold_key_var, width=24)
            hold_entry.grid(row=0, column=1, sticky="w")
            ttk_module.Button(
                hold_frame,
                text="Clear",
                command=lambda: self.clear_recording(self.hold_key_var),
            ).grid(row=0, column=2, sticky="w", padx=(8, 0))
            self.bind_capture_entry(
                hold_entry,
                self.hold_key_var,
                combo_mode=False,
                focus_message="Press the key you want to hold.",
            )
            ttk_module.Label(
                hold_frame,
                text="Click the box and press a key to record it.",
            ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(4, 0))
            ttk_module.Label(hold_frame, text="Hold seconds").grid(row=2, column=0, sticky="w", pady=(8, 0))
            ttk_module.Entry(hold_frame, textvariable=self.hold_seconds_var, width=12).grid(
                row=2, column=1, sticky="w", pady=(8, 0)
            )
            self.mode_frames["hold"] = hold_frame

            clickflow_frame = ttk_module.Frame(panels)

            # --- button bar: Record / Clear / Save / Load ---
            btn_bar = ttk_module.Frame(clickflow_frame)
            btn_bar.grid(row=0, column=0, columnspan=3, sticky="w")
            self.record_button = ttk_module.Button(
                btn_bar, text="\u25cf Record", command=self.start_click_recording,
            )
            self.record_button.grid(row=0, column=0, sticky="w")
            ttk_module.Button(
                btn_bar, text="Clear", command=self.clear_click_flow,
            ).grid(row=0, column=1, sticky="w", padx=(6, 0))
            ttk_module.Button(
                btn_bar, text="Save", command=self.save_click_flow,
            ).grid(row=0, column=2, sticky="w", padx=(6, 0))
            ttk_module.Button(
                btn_bar, text="Load", command=self.load_click_flow,
            ).grid(row=0, column=3, sticky="w", padx=(6, 0))

            ttk_module.Label(
                clickflow_frame,
                text="Click Record \u2192 3s countdown \u2192 click on screen \u2192 F6 / Esc to stop",
            ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(4, 0))

            # --- listbox + scrollbar ---
            list_frame = ttk_module.Frame(clickflow_frame)
            list_frame.grid(row=2, column=0, columnspan=3, sticky="w", pady=(4, 0))
            self.click_listbox = tk_module.Listbox(
                list_frame, width=46, height=6, font=("Consolas", 9),
                selectmode="extended",
            )
            list_scroll = ttk_module.Scrollbar(list_frame, orient="vertical", command=self.click_listbox.yview)
            self.click_listbox.configure(yscrollcommand=list_scroll.set)
            self.click_listbox.grid(row=0, column=0, sticky="nsew")
            list_scroll.grid(row=0, column=1, sticky="ns")
            self.click_listbox.bind("<Delete>", lambda _e: self.delete_selected_clicks())
            self.click_listbox.bind("<BackSpace>", lambda _e: self.delete_selected_clicks())

            ttk_module.Label(
                clickflow_frame,
                text="Select items and press Delete to remove.",
                foreground="gray",
            ).grid(row=3, column=0, columnspan=3, sticky="w", pady=(2, 0))

            # --- replay options in a compact grid ---
            opts = ttk_module.LabelFrame(clickflow_frame, text="Replay options", padding=6)
            opts.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(8, 0))
            ttk_module.Label(opts, text="Repeat").grid(row=0, column=0, sticky="w")
            ttk_module.Entry(opts, textvariable=self.clickflow_repeat_var, width=8).grid(
                row=0, column=1, sticky="w", padx=(4, 12),
            )
            ttk_module.Label(opts, text="Speed").grid(row=0, column=2, sticky="w")
            ttk_module.Entry(opts, textvariable=self.clickflow_speed_var, width=8).grid(
                row=0, column=3, sticky="w", padx=(4, 0),
            )
            ttk_module.Checkbutton(
                opts,
                text="Use original timing between clicks",
                variable=self.clickflow_use_delays_var,
            ).grid(row=1, column=0, columnspan=4, sticky="w", pady=(6, 0))
            ttk_module.Label(opts, text="Fixed interval (s)").grid(row=2, column=0, columnspan=2, sticky="w", pady=(4, 0))
            ttk_module.Entry(opts, textvariable=self.clickflow_interval_var, width=8).grid(
                row=2, column=2, sticky="w", padx=(4, 0), pady=(4, 0),
            )
            ttk_module.Label(
                opts, text="(used when original timing is off)", foreground="gray",
            ).grid(row=2, column=3, sticky="w", padx=(4, 0), pady=(4, 0))
            ttk_module.Label(opts, text="Cycle interval (s)").grid(row=3, column=0, columnspan=2, sticky="w", pady=(4, 0))
            ttk_module.Entry(opts, textvariable=self.clickflow_cycle_interval_var, width=8).grid(
                row=3, column=2, sticky="w", padx=(4, 0), pady=(4, 0),
            )
            ttk_module.Label(
                opts, text="(pause between each loop)", foreground="gray",
            ).grid(row=3, column=3, sticky="w", padx=(4, 0), pady=(4, 0))

            self.mode_frames["clickflow"] = clickflow_frame

            action_bar = ttk_module.Frame(container)
            action_bar.grid(row=5, column=0, sticky="ew", pady=(12, 0))
            self.start_button = ttk_module.Button(action_bar, text="Start", command=self.start_action)
            self.start_button.grid(row=0, column=0, sticky="w")
            self.stop_button = ttk_module.Button(action_bar, text="Stop", command=self.stop_action)
            self.stop_button.grid(row=0, column=1, sticky="w", padx=(8, 0))
            self.stop_button.state(["disabled"])
            ttk_module.Button(action_bar, text="Close", command=self.root.destroy).grid(
                row=0, column=2, sticky="w", padx=(8, 0)
            )

            status_label = ttk_module.Label(
                container,
                textvariable=self.status_var,
                wraplength=420,
                justify="left",
            )
            status_label.grid(row=6, column=0, sticky="w", pady=(12, 0))

        def bind_capture_entry(
            self,
            entry,
            variable,
            combo_mode: bool,
            focus_message: str,
        ) -> None:
            entry.bind(
                "<FocusIn>",
                lambda _event, message=focus_message: self.status_var.set(message),
            )
            entry.bind(
                "<KeyPress>",
                lambda event, value=variable, is_combo=combo_mode: self.handle_capture_keypress(
                    event,
                    value,
                    is_combo,
                ),
            )

        def handle_capture_keypress(self, event, variable, combo_mode: bool) -> str:
            recorded = recorded_value_from_tk_event(event, combo_mode)
            if recorded:
                if combo_mode:
                    variable.set(recorded)
                    self.status_var.set(f"Recorded: {recorded}")
                else:
                    updated_value, appended = append_press_recorded_value(variable.get(), recorded)
                    if appended:
                        variable.set(updated_value)
                        self.status_var.set(f"Recorded: {updated_value}")
                    else:
                        self.status_var.set(
                            f"Press key mode supports up to {MAX_PRESS_KEYS} keys. Use Clear to record again."
                        )
            return "break"

        def clear_recording(self, variable) -> None:
            variable.set("")
            self.status_var.set("Cleared. Click a box and press the keyboard to record again.")

        def start_click_recording(self) -> None:
            if self.click_recorder.is_recording:
                return
            if self.worker and self.worker.is_alive():
                messagebox.showinfo("Busy", "An action is already running.")
                return
            self.click_listbox.delete(0, "end")
            self.record_button.state(["disabled"])
            self.start_button.state(["disabled"])
            self.status_var.set("Preparing to record...")
            self.root.iconify()
            # start a 3-second countdown before recording
            self._show_countdown(3)

        def _show_countdown(self, remaining: int) -> None:
            """Show a large countdown overlay, then begin recording."""
            if remaining <= 0:
                # countdown finished — destroy overlay and start recording
                if self._countdown_window:
                    self._countdown_window.destroy()
                    self._countdown_window = None
                self._begin_recording()
                return

            if self._countdown_window is None:
                cw = tk.Toplevel(self.root)
                cw.overrideredirect(True)
                cw.attributes("-topmost", True)
                cw.attributes("-alpha", 0.85)
                cw.configure(bg="#1a1a2e")
                w, h = 220, 140
                sx = self.root.winfo_screenwidth() // 2 - w // 2
                sy = self.root.winfo_screenheight() // 2 - h // 2
                cw.geometry(f"{w}x{h}+{sx}+{sy}")
                self._countdown_label = tk.Label(
                    cw, text="", font=("Segoe UI", 48, "bold"),
                    fg="#e94560", bg="#1a1a2e",
                )
                self._countdown_label.pack(expand=True)
                self._countdown_hint = tk.Label(
                    cw, text="Recording will start...",
                    font=("Segoe UI", 10), fg="#aaaaaa", bg="#1a1a2e",
                )
                self._countdown_hint.pack(pady=(0, 10))
                self._countdown_window = cw

            self._countdown_label.configure(text=str(remaining))
            self.root.after(1000, self._show_countdown, remaining - 1)

        def _begin_recording(self) -> None:
            """Actually start the hook-based recording and show floating indicator."""
            self._show_recording_overlay()
            self.click_recorder.start(
                on_click=lambda click: self.root.after(0, self._on_click_recorded, click),
                on_stop=lambda: self.root.after(0, self._on_recording_stopped),
            )

        def _show_recording_overlay(self) -> None:
            """Small always-on-top indicator in the top-right corner."""
            ov = tk.Toplevel(self.root)
            ov.overrideredirect(True)
            ov.attributes("-topmost", True)
            ov.attributes("-alpha", 0.9)
            ov.configure(bg="#2d2d44")
            w, h = 260, 56
            sx = self.root.winfo_screenwidth() - w - 16
            ov.geometry(f"{w}x{h}+{sx}+16")

            top_row = tk.Frame(ov, bg="#2d2d44")
            top_row.pack(fill="x", padx=8, pady=(6, 0))
            tk.Label(
                top_row, text="\u25cf REC", font=("Segoe UI", 11, "bold"),
                fg="#e94560", bg="#2d2d44",
            ).pack(side="left")
            self._recording_count_var = tk.StringVar(value="  0 clicks")
            tk.Label(
                top_row, textvariable=self._recording_count_var,
                font=("Segoe UI", 10), fg="#ffffff", bg="#2d2d44",
            ).pack(side="left", padx=(6, 0))

            tk.Label(
                ov, text="Press F6 or Esc to stop",
                font=("Segoe UI", 9), fg="#aaaaaa", bg="#2d2d44",
            ).pack(anchor="w", padx=8, pady=(2, 6))

            self._recording_overlay = ov

        def _dismiss_recording_overlay(self) -> None:
            if self._recording_overlay:
                self._recording_overlay.destroy()
                self._recording_overlay = None
                self._recording_count_var = None

        def _on_click_recorded(self, click: dict) -> None:
            idx = len(self.click_recorder.recorded_clicks)
            btn = click["button"]
            x, y = click["x"], click["y"]
            delay = click["delay"]
            label = f"{idx}. {btn} ({x}, {y})"
            if delay > 0:
                label += f"  +{delay:.2f}s"
            self.click_listbox.insert("end", label)
            self.click_listbox.see("end")
            if self._recording_count_var:
                self._recording_count_var.set(f"  {idx} click(s)")

        def _on_recording_stopped(self) -> None:
            self._dismiss_recording_overlay()
            self.record_button.state(["!disabled"])
            self.start_button.state(["!disabled"])
            self.root.deiconify()
            self.root.lift()
            count = len(self.click_recorder.recorded_clicks)
            self.status_var.set(f"Recording finished — {count} click(s) captured.")

        def clear_click_flow(self) -> None:
            if self.click_recorder.is_recording:
                self.click_recorder.stop()
            self.click_recorder.recorded_clicks = []
            self.click_listbox.delete(0, "end")
            self.status_var.set("Click flow cleared.")

        def delete_selected_clicks(self) -> None:
            """Remove the selected entries from the listbox and the recorded data."""
            selection = list(self.click_listbox.curselection())
            if not selection:
                return
            for index in reversed(selection):
                self.click_listbox.delete(index)
                if index < len(self.click_recorder.recorded_clicks):
                    self.click_recorder.recorded_clicks.pop(index)
            self._refresh_click_labels()
            self.status_var.set(f"Deleted {len(selection)} item(s). {len(self.click_recorder.recorded_clicks)} remaining.")

        def _refresh_click_labels(self) -> None:
            """Rebuild listbox labels after deletion to fix numbering."""
            self.click_listbox.delete(0, "end")
            for idx, click in enumerate(self.click_recorder.recorded_clicks, 1):
                btn = click["button"]
                x, y = click["x"], click["y"]
                delay = float(click["delay"])
                label = f"{idx}. {btn} ({x}, {y})"
                if delay > 0:
                    label += f"  +{delay:.2f}s"
                self.click_listbox.insert("end", label)

        def save_click_flow(self) -> None:
            """Save recorded clicks to a JSON file."""
            from tkinter import filedialog
            if not self.click_recorder.recorded_clicks:
                messagebox.showinfo("Nothing to save", "Record some clicks first.")
                return
            path = filedialog.asksaveasfilename(
                title="Save click flow",
                defaultextension=".json",
                filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            )
            if not path:
                return
            try:
                with open(path, "w", encoding="utf-8") as fh:
                    json.dump(self.click_recorder.recorded_clicks, fh, indent=2, ensure_ascii=False)
                self.status_var.set(f"Saved {len(self.click_recorder.recorded_clicks)} click(s) to {os.path.basename(path)}")
            except OSError as err:
                messagebox.showerror("Save failed", str(err))

        def load_click_flow(self) -> None:
            """Load clicks from a JSON file."""
            from tkinter import filedialog
            path = filedialog.askopenfilename(
                title="Load click flow",
                filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            )
            if not path:
                return
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                if not isinstance(data, list) or not data:
                    raise ValueError("File does not contain a valid click list.")
                for item in data:
                    if not all(k in item for k in ("x", "y", "button", "delay")):
                        raise ValueError("Invalid click entry format.")
                self.click_recorder.recorded_clicks = data
                self._refresh_click_labels()
                self.status_var.set(f"Loaded {len(data)} click(s) from {os.path.basename(path)}")
            except (OSError, json.JSONDecodeError, ValueError) as err:
                messagebox.showerror("Load failed", str(err))

        def build_window_label(self, window_info: dict[str, object]) -> str:
            title = str(window_info["title"])
            process_name = str(window_info["process_name"])
            hwnd = int(window_info["hwnd"])
            return f"{title} [{process_name}] (0x{hwnd:08X})"

        def refresh_window_list(self) -> None:
            selected_hwnd = self.get_selected_window_handle()
            windows = [
                window_info
                for window_info in list_visible_windows()
                if not (
                    int(window_info["pid"]) == os.getpid()
                    and str(window_info["title"]) == self.root.title()
                )
            ]

            self.window_targets = windows
            self.target_combo["values"] = [self.build_window_label(window_info) for window_info in windows]

            if not windows:
                self.target_window_var.set("")
                self.status_var.set("No visible target windows were found.")
                return

            if selected_hwnd:
                for index, window_info in enumerate(windows):
                    if int(window_info["hwnd"]) == selected_hwnd:
                        self.target_combo.current(index)
                        return

            self.target_window_var.set("")

        def handle_target_selected(self, _event=None) -> None:
            if self.target_combo.current() >= 0:
                self.use_selected_window_var.set(True)
                self.status_var.set("Selected window will be activated before the action runs.")

        def get_selected_window_handle(self) -> int | None:
            index = self.target_combo.current()
            if index < 0 or index >= len(self.window_targets):
                return None
            return int(self.window_targets[index]["hwnd"])

        def update_mode_fields(self) -> None:
            current_mode = self.mode_var.get()
            for mode_name, frame in self.mode_frames.items():
                if mode_name == current_mode:
                    frame.grid(row=0, column=0, sticky="ew")
                else:
                    frame.grid_forget()

        def parse_float(self, raw_value: str, field_name: str, minimum: float = 0.0) -> float:
            value_text = raw_value.strip()
            if not value_text:
                raise ValueError(f"{field_name} cannot be empty.")
            try:
                value = float(value_text)
            except ValueError as error:
                raise ValueError(f"{field_name} must be a number.") from error
            if value < minimum:
                raise ValueError(f"{field_name} must be >= {minimum}.")
            return value

        def parse_int(self, raw_value: str, field_name: str, minimum: int = 1) -> int:
            value_text = raw_value.strip()
            if not value_text:
                raise ValueError(f"{field_name} cannot be empty.")
            try:
                value = int(value_text)
            except ValueError as error:
                raise ValueError(f"{field_name} must be an integer.") from error
            if value < minimum:
                raise ValueError(f"{field_name} must be >= {minimum}.")
            return value

        def collect_request(self) -> dict[str, object]:
            request: dict[str, object] = {
                "mode": self.mode_var.get(),
                "delay": self.parse_float(self.delay_var.get(), "Delay"),
                "minimize": self.minimize_var.get(),
                "target_hwnd": None,
            }

            if self.use_selected_window_var.get():
                target_hwnd = self.get_selected_window_handle()
                if not target_hwnd:
                    raise ValueError("Please choose a target window or turn off 'Use selected window'.")
                request["target_hwnd"] = target_hwnd

            if request["mode"] == "press":
                request["key"] = self.press_key_var.get().strip()
                request["repeat"] = self.parse_int(self.press_repeat_var.get(), "Repeat")
                request["interval"] = self.parse_float(self.press_interval_var.get(), "Interval (seconds)")
            elif request["mode"] == "hotkey":
                request["keys_text"] = self.hotkey_var.get().strip()
                request["repeat"] = self.parse_int(self.hotkey_repeat_var.get(), "Repeat")
                request["interval"] = self.parse_float(self.hotkey_interval_var.get(), "Interval (seconds)")
            elif request["mode"] == "text":
                request["content"] = self.text_widget.get("1.0", "end-1c")
                request["interval"] = self.parse_float(self.text_interval_var.get(), "Interval (seconds)")
            elif request["mode"] == "hold":
                request["key"] = self.hold_key_var.get().strip()
                request["seconds"] = self.parse_float(self.hold_seconds_var.get(), "Hold seconds")
            elif request["mode"] == "clickflow":
                if not self.click_recorder.recorded_clicks:
                    raise ValueError("No clicks recorded. Click Record first.")
                request["clicks"] = list(self.click_recorder.recorded_clicks)
                request["repeat"] = self.parse_int(self.clickflow_repeat_var.get(), "Repeat")
                request["speed"] = self.parse_float(self.clickflow_speed_var.get(), "Speed", 0.01)
                request["use_delays"] = self.clickflow_use_delays_var.get()
                request["fixed_interval"] = self.parse_float(self.clickflow_interval_var.get(), "Fixed interval")
                request["cycle_interval"] = self.parse_float(self.clickflow_cycle_interval_var.get(), "Cycle interval")
            else:
                raise ValueError(f"Unsupported mode: {request['mode']}")

            return request

        def start_action(self) -> None:
            if self.worker and self.worker.is_alive():
                messagebox.showinfo("Busy", "An action is already running.")
                return

            try:
                request = self.collect_request()
            except ValueError as error:
                messagebox.showerror("Invalid input", str(error))
                return

            self.stop_event = threading.Event()
            self.status_var.set("Action started. Switch to the target window before the delay ends.")
            self.start_button.state(["disabled"])
            self.stop_button.state(["!disabled"])

            if request["minimize"]:
                self.root.iconify()

            self.worker = threading.Thread(target=self.execute_request, args=(request,), daemon=True)
            self.worker.start()

        def stop_action(self) -> None:
            if not (self.worker and self.worker.is_alive()):
                self.status_var.set("No action is currently running.")
                self.stop_button.state(["disabled"])
                return

            self.stop_event.set()
            self.stop_button.state(["disabled"])
            self.status_var.set("Stopping action...")

        def execute_request(self, request: dict[str, object]) -> None:
            try:
                delay = float(request["delay"])
                if delay:
                    sleep_with_cancel(delay, self.stop_event)

                target_hwnd = int(request.get("target_hwnd") or 0)
                if target_hwnd:
                    raise_if_cancelled(self.stop_event)
                    if not activate_window(target_hwnd):
                        raise ValueError("Could not activate the selected target window. It may have been closed.")
                    sleep_with_cancel(0.15, self.stop_event)

                mode = str(request["mode"])
                if mode == "press":
                    run_press(
                        str(request["key"]),
                        int(request["repeat"]),
                        float(request["interval"]),
                        stop_event=self.stop_event,
                    )
                elif mode == "hotkey":
                    run_hotkey(
                        [str(request["keys_text"])],
                        int(request["repeat"]),
                        float(request["interval"]),
                        stop_event=self.stop_event,
                    )
                elif mode == "text":
                    type_text(
                        str(request["content"]),
                        float(request["interval"]),
                        stop_event=self.stop_event,
                    )
                elif mode == "hold":
                    run_hold(
                        str(request["key"]),
                        float(request["seconds"]),
                        stop_event=self.stop_event,
                    )
                elif mode == "clickflow":
                    run_click_flow(
                        request["clicks"],
                        repeat=int(request["repeat"]),
                        speed=float(request["speed"]),
                        use_delays=bool(request["use_delays"]),
                        fixed_interval=float(request["fixed_interval"]),
                        cycle_interval=float(request["cycle_interval"]),
                        stop_event=self.stop_event,
                    )
                else:
                    raise ValueError(f"Unsupported mode: {mode}")
            except ActionCancelled as error:
                self.root.after(0, self.finish_action, True, str(error), False)
                return
            except (ValueError, OSError) as error:
                self.root.after(0, self.finish_action, False, str(error), True)
                return
            except Exception as error:
                self.root.after(0, self.finish_action, False, f"Unexpected error: {error}", True)
                return

            self.root.after(0, self.finish_action, True, "Action completed.", False)

        def finish_action(self, success: bool, message: str, show_error_dialog: bool) -> None:
            self.start_button.state(["!disabled"])
            self.stop_button.state(["disabled"])
            self.root.deiconify()
            self.root.lift()
            self.status_var.set(message)

            if success or not show_error_dialog:
                return
            messagebox.showerror("Execution failed", message)

    root = tk.Tk()
    KeyboardSimulatorApp(root)
    root.mainloop()


def run_press(
    key: str | list[str],
    repeat: int,
    interval: float,
    stop_event: threading.Event | None = None,
) -> None:
    if repeat < 1:
        raise ValueError("repeat must be at least 1.")
    ensure_non_negative("interval", interval)

    key_specs = parse_press_specs(key)
    total_presses = repeat * len(key_specs)
    press_index = 0
    for _index in range(repeat):
        for key_spec in key_specs:
            raise_if_cancelled(stop_event)
            combo = resolve_key_spec(key_spec)
            tap_combo(combo)
            press_index += 1
            if press_index < total_presses and interval:
                sleep_with_cancel(interval, stop_event)


def run_hotkey(
    keys: list[str],
    repeat: int,
    interval: float,
    stop_event: threading.Event | None = None,
) -> None:
    if repeat < 1:
        raise ValueError("repeat must be at least 1.")
    ensure_non_negative("interval", interval)

    combo: list[int] = []
    for key_spec in expand_hotkey_specs(keys):
        combo.extend(resolve_key_spec(key_spec))

    resolved_combo = dedupe_preserve_order(combo)
    for index in range(repeat):
        raise_if_cancelled(stop_event)
        tap_combo(resolved_combo)
        if index < repeat - 1 and interval:
            sleep_with_cancel(interval, stop_event)


def run_hold(key: str, seconds: float, stop_event: threading.Event | None = None) -> None:
    ensure_non_negative("seconds", seconds)
    combo = resolve_key_spec(key)
    hold_combo(combo, seconds, stop_event=stop_event)


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        if args.command is None:
            if args.console:
                interactive_mode()
            else:
                launch_gui()
            return 0

        ensure_non_negative("delay", args.delay)

        if args.delay:
            time.sleep(args.delay)

        if args.command == "press":
            run_press(args.keys, args.repeat, args.interval)
        elif args.command == "hotkey":
            run_hotkey(args.keys, args.repeat, args.interval)
        elif args.command == "text":
            ensure_non_negative("interval", args.interval)
            type_text(args.content, args.interval)
        elif args.command == "hold":
            run_hold(args.key, args.seconds)
        else:
            parser.error(f"Unsupported command: {args.command}")
    except ValueError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2
    except OSError as error:
        print(f"Windows API error: {error}", file=sys.stderr)
        return 3

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

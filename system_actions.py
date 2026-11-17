"""Windows integration: applications, audio, screenshots, and weather."""

import asyncio
import ctypes
import datetime
import json
import os
import subprocess
import urllib.error
import urllib.parse
import urllib.request

import psutil
from PIL import ImageGrab
from pycaw.pycaw import AudioUtilities
from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionManager

from .config import CLOSABLE_PROGRAMS, PROGRAM_LAUNCHERS, WEATHER_CITY, WEATHER_LATITUDE, WEATHER_LONGITUDE
from .voice import speak

def get_weather():
    query = urllib.parse.urlencode({
        "latitude": WEATHER_LATITUDE,
        "longitude": WEATHER_LONGITUDE,
        "current": "temperature_2m,relative_humidity_2m,apparent_temperature,weather_code",
        "timezone": "auto",
    })
    url = "https://api.open-meteo.com/v1/forecast?" + query
    with urllib.request.urlopen(url, timeout=10) as response:
        data = json.load(response)

    current = data["current"]
    weather_codes = {
        0: "ясно",
        1: "переважно ясно",
        2: "мінлива хмарність",
        3: "хмарно",
        45: "туман",
        48: "туман",
        51: "легка мряка",
        53: "мряка",
        55: "сильна мряка",
        61: "невеликий дощ",
        63: "дощ",
        65: "сильний дощ",
        71: "невеликий сніг",
        73: "сніг",
        75: "сильний сніг",
        80: "короткочасний дощ",
        81: "дощ",
        82: "сильний дощ",
        95: "гроза",
    }
    condition = weather_codes.get(current["weather_code"], "невідомі умови")
    return (
        f"У місті {WEATHER_CITY} зараз {condition}, "
        f"{round(current['temperature_2m'])} градусів. "
        f"Відчувається як {round(current['apparent_temperature'])}, "
        f"вологість {current['relative_humidity_2m']} відсотків."
    )

def adjust_volume(change):
    endpoint = AudioUtilities.GetSpeakers().EndpointVolume
    current = endpoint.GetMasterVolumeLevelScalar()
    updated = min(1.0, max(0.0, current + change))
    endpoint.SetMasterVolumeLevelScalar(updated, None)
    return round(updated * 100)

def launch_configured_program(program):
    config = PROGRAM_LAUNCHERS[program]
    for candidate in config["executables"]:
        executable = os.path.expandvars(candidate)
        if os.path.isabs(executable) and os.path.isfile(executable):
            if program == "discord" and os.path.basename(executable).lower() == "update.exe":
                subprocess.Popen([executable, "--processStart", "Discord.exe"])
            else:
                subprocess.Popen([executable])
            return
        if not os.path.isabs(executable):
            try:
                subprocess.Popen([executable])
                return
            except OSError:
                continue

    for shortcut in config["shortcuts"]:
        shortcut_path = find_start_menu_shortcut(shortcut)
        if shortcut_path:
            try:
                os.startfile(shortcut_path)
                return
            except OSError:
                continue

    for uri in config["uris"]:
        try:
            os.startfile(uri)
            return
        except OSError:
            continue

    raise OSError(f"No installed launcher found for {program}")

def find_start_menu_shortcut(app_name):
    start_menu_paths = (
        os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs"),
        os.path.join(os.environ.get("PROGRAMDATA", ""), r"Microsoft\Windows\Start Menu\Programs"),
    )
    expected_name = app_name.casefold()
    for root in start_menu_paths:
        if not os.path.isabs(root) or not os.path.isdir(root):
            continue
        for directory, _, filenames in os.walk(root):
            for filename in filenames:
                if filename.casefold() in (expected_name + ".lnk", expected_name + ".appref-ms"):
                    return os.path.join(directory, filename)
    return None

def close_program_windows(process_names):
    user32 = ctypes.windll.user32
    closed_windows = 0
    enum_windows_proc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_ssize_t)

    def close_matching_window(hwnd, _):
        nonlocal closed_windows
        if not user32.IsWindowVisible(hwnd):
            return True

        process_id = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
        try:
            process_name = psutil.Process(process_id.value).name().lower()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return True

        if process_name in process_names and user32.PostMessageW(hwnd, 0x0010, 0, 0):
            closed_windows += 1
        return True

    callback = enum_windows_proc(close_matching_window)
    user32.EnumWindows(callback, 0)
    return closed_windows

def execute_programs_except(program_names):
    if not program_names:
        speak("Назви програму, яку потрібно залишити відкритою.")
        return

    keep_process_names = set()
    unknown_names = []
    for name in program_names:
        process_names = CLOSABLE_PROGRAMS.get(name)
        if process_names is None:
            unknown_names.append(name)
        else:
            keep_process_names.update(process_name.lower() for process_name in process_names)

    if unknown_names:
        speak(
            "Не знаю цю програму для винятку: "
            + ", ".join(unknown_names)
            + ". Нічого не закривав."
        )
        return

    protected_processes = {
        "csrss.exe",
        "dwm.exe",
        "explorer.exe",
        "lsass.exe",
        "services.exe",
        "smss.exe",
        "svchost.exe",
        "system",
        "wininit.exe",
        "winlogon.exe",
    }
    user32 = ctypes.windll.user32
    closed_windows = 0
    current_process_id = os.getpid()
    enum_windows_proc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_ssize_t)

    def close_unprotected_window(hwnd, _):
        nonlocal closed_windows
        if not user32.IsWindowVisible(hwnd):
            return True

        process_id = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
        if process_id.value == current_process_id:
            return True

        try:
            process_name = psutil.Process(process_id.value).name().lower()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return True

        if process_name in protected_processes or process_name in keep_process_names:
            return True

        if user32.PostMessageW(hwnd, 0x0010, 0, 0):
            closed_windows += 1
        return True

    callback = enum_windows_proc(close_unprotected_window)
    user32.EnumWindows(callback, 0)
    speak(f"Надіслав запит на закриття вікон: {closed_windows}.")

def save_screenshot():
    pictures_folder = os.path.join(os.path.expanduser("~"), "Pictures")
    try:
        os.makedirs(pictures_folder, exist_ok=True)
        filename = "jarvis_screenshot_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S") + ".png"
        path = os.path.join(pictures_folder, filename)
        ImageGrab.grab().save(path)
    except (OSError, RuntimeError) as e:
        print("[log] Не вдалося зробити скриншот:", e)
        speak("Не вдалося зробити скриншот.")
        return
    speak(f"Скриншот збережено в папці Зображення. Файл: {filename}.")

def is_browser_media_session(session):
    app_id = session.source_app_user_model_id.casefold()
    return (
        app_id in ("chrome.exe", "msedge.exe", "firefox.exe")
        or "microsoftedge" in app_id
    )

def find_browser_media_session(manager):
    current_session = manager.get_current_session()
    if current_session and is_browser_media_session(current_session):
        return current_session

    browser_sessions = [
        session for session in manager.get_sessions()
        if is_browser_media_session(session)
    ]
    return browser_sessions[0] if len(browser_sessions) == 1 else None

async def send_media_command_async(command):
    manager = await GlobalSystemMediaTransportControlsSessionManager.request_async()
    session = find_browser_media_session(manager)
    if session is None:
        return False

    commands = {
        "pause": session.try_pause_async,
        "play": session.try_play_async,
        "toggle": session.try_toggle_play_pause_async,
        "next": session.try_skip_next_async,
        "previous": session.try_skip_previous_async,
    }
    send_command = commands.get(command)
    if send_command is None:
        raise ValueError(f"Unsupported media command: {command}")
    return await send_command()

def send_media_command(command):
    try:
        return asyncio.run(send_media_command_async(command))
    except (OSError, RuntimeError) as e:
        print(f"[log] Не вдалося керувати медіасеансом браузера: {e}")
        return False

def find_program_window(process_names):
    user32 = ctypes.windll.user32
    matching_window = []
    enum_windows_proc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_ssize_t)

    def find_matching_window(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True

        process_id = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
        try:
            process_name = psutil.Process(process_id.value).name().lower()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return True

        if process_name in process_names:
            matching_window.append(hwnd)
            return False
        return True

    callback = enum_windows_proc(find_matching_window)
    user32.EnumWindows(callback, 0)
    return matching_window[0] if matching_window else None

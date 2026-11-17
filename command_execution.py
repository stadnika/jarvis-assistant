import datetime
import json
import os
import urllib.error
import urllib.parse
import webbrowser
import subprocess

import psutil
from pycaw.pycaw import AudioUtilities

from . import state
from .command_parsing import normalize_text
from .config import CLOSABLE_PROGRAMS, PROGRAMS, PROGRAM_LAUNCHERS, WEBSITES
from .system_actions import (
    adjust_volume,
    close_program_windows,
    execute_programs_except,
    get_weather,
    launch_configured_program,
    save_screenshot,
    send_media_command,
)
from .voice import speak

def execute_cmd(cmd):
    if cmd == 'ctime':
        now = datetime.datetime.now()
        speak("Зараз " + str(now.hour) + ":" + str(now.minute))

    elif cmd == 'radio':
        speak("Відкриваю музику")
        webbrowser.open("https://www.youtube.com/watch?v=Jf1j6g8k5nY")

    elif cmd == 'stupid1':
        speak("Мій розробник не навчив мене анекдотам... Ха-ха")

    elif cmd == "thanks":
        speak("Будь ласка! Радий допомогти.")

    elif cmd == "weather":
        try:
            speak(get_weather())
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
            print("[log] Не вдалося отримати погоду:", e)
            speak("Не вдалося отримати погоду. Перевір підключення до інтернету.")

    elif cmd == "battery":
        battery = psutil.sensors_battery()
        if battery is None:
            speak("Не вдалося отримати інформацію про батарею.")
        else:
            charging = "підключений до зарядки" if battery.power_plugged else "не підключений до зарядки"
            speak(f"Заряд батареї {round(battery.percent)} відсотків, комп'ютер {charging}.")

    elif cmd == "volume_up":
        speak(f"Гучність {adjust_volume(0.1)} відсотків.")

    elif cmd == "volume_down":
        speak(f"Гучність {adjust_volume(-0.1)} відсотків.")

    elif cmd == "mute":
        AudioUtilities.GetSpeakers().EndpointVolume.SetMute(1, None)
        speak("Звук вимкнено.")

    elif cmd == "unmute":
        AudioUtilities.GetSpeakers().EndpointVolume.SetMute(0, None)
        speak("Звук увімкнено.")

    elif cmd == "open_browser":
        speak("Відкриваю браузер")
        chrome_paths = [
            r'C:\Program Files\Google\Chrome\Application\chrome.exe',
            r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe'
        ]
        opened = False
        for path in chrome_paths:
            if os.path.exists(path):
                os.startfile(path)
                opened = True
                break
        if not opened:
            webbrowser.open("https://www.google.com")

    elif cmd == "screenshot":
        save_screenshot()

    elif cmd == "music_pause":
        if send_media_command("pause"):
            speak("Музику призупинено.")
        else:
            speak("Не знайшов активний медіасеанс браузера. Переконайся, що YouTube Music відкритий.")

    elif cmd == "music_play":
        if send_media_command("play"):
            speak("Відтворення музики продовжено.")
        else:
            speak("Не знайшов активний медіасеанс браузера. Переконайся, що YouTube Music відкритий.")

    elif cmd == "music_toggle":
        if send_media_command("toggle"):
            speak("Перемкнув відтворення музики.")
        else:
            speak("Не знайшов активний медіасеанс браузера. Переконайся, що YouTube Music відкритий.")

    elif cmd == "music_next":
        if send_media_command("next"):
            speak("Увімкнув наступний трек.")
        else:
            speak("Не вдалося перемкнути трек у медіасеансі браузера.")

    elif cmd == "music_previous":
        if send_media_command("previous"):
            speak("Увімкнув попередній трек.")
        else:
            speak("Не вдалося перемкнути трек у медіасеансі браузера.")

    elif cmd == "shutdown":
        speak("Вимикаю комп'ютер")
        os.system("shutdown /s /t 10")

    elif cmd == "reboot":
        speak("Перезавантажую комп'ютер")
        os.system("shutdown /r /t 10")

    elif cmd == "sleep":
        state.LISTENING = False
        speak("Добре, я відпочиваю. Коли захочеш, скажи: Джарвіс.")

    else:
        print('Команда не распознана, повторите!')

def execute_dynamic_cmd(action, value):
    if action in ("launch_programs", "close_programs"):
        execute_program_list(action, value)
        return

    if action == "close_programs_except":
        execute_programs_except(value)
        return

    if action == "close_program":
        process_names = CLOSABLE_PROGRAMS.get(value)
        if process_names is None:
            speak("Цю програму закривати не вмію. Спробуй калькулятор, блокнот, Paint, диспетчер завдань або браузер.")
            return
        closed_windows = close_program_windows(process_names)
        if closed_windows:
            speak(f"Закрив вікон: {closed_windows}.")
        else:
            speak(f"Не знайшов відкритих вікон програми {value}.")
    elif action == "launch_program":
        program = PROGRAMS.get(value)
        if program is None:
            speak("Цю програму запускати не вмію. Спробуй назвати одну з відомих програм.")
            return
        try:
            if program == "browser":
                webbrowser.open("https://www.google.com")
            elif program in PROGRAM_LAUNCHERS:
                launch_configured_program(program)
            else:
                subprocess.Popen([program])
            speak(f"Запускаю {value}.")
        except OSError as e:
            print("[log] Не вдалося запустити програму:", e)
            speak(f"Не вдалося запустити {value}. Перевір, чи програму встановлено.")
    elif action == "open_website":
        target = value.strip().lower()
        url = WEBSITES.get(target)
        if url is None:
            if is_website_target(target):
                url = target if target.startswith(("http://", "https://")) else "https://" + target
            else:
                speak("Не зрозумів назву сайту. Скажи, наприклад: відкрий сайт youtube.com.")
                return
        webbrowser.open(url)
        speak("Відкриваю сайт.")
    elif action == "launch_browser":
        webbrowser.open("https://www.google.com")
        speak("Відкриваю браузер.")
    elif action == "web_search":
        if not value.strip():
            speak("Скажи, що саме потрібно знайти.")
            return
        url = "https://www.google.com/search?" + urllib.parse.urlencode({"q": value})
        webbrowser.open(url)
        speak(f"Шукаю в інтернеті: {value}.")

def execute_program_list(action, program_names):
    successful = []
    failed = []

    for name in program_names:
        if action == "launch_programs":
            program = PROGRAMS.get(name)
            if program is None:
                failed.append(name)
                continue
            try:
                if program in PROGRAM_LAUNCHERS:
                    launch_configured_program(program)
                else:
                    subprocess.Popen([program])
                successful.append(name)
            except OSError as e:
                print(f"[log] Не вдалося запустити {name}:", e)
                failed.append(name)
        else:
            process_names = CLOSABLE_PROGRAMS.get(name)
            if process_names is None:
                failed.append(name)
                continue
            try:
                if close_program_windows(process_names):
                    successful.append(name)
                else:
                    failed.append(name)
            except OSError as e:
                print(f"[log] Не вдалося закрити {name}:", e)
                failed.append(name)

    if successful:
        action_text = "Запустив" if action == "launch_programs" else "Надіслав запит на закриття"
        speak(f"{action_text}: {', '.join(successful)}.")
    if failed:
        speak(f"Не вдалося виконати команду для: {', '.join(failed)}.")

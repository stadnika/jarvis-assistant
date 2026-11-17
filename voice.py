
import ctypes
import json
import os
from pathlib import Path

import speech_recognition as sr
import pyttsx3

from . import state
from .config import ASR_BACKEND, VOSK_MODEL_PATH, opts
from .command_parsing import (
    extract_timer_seconds,
    extract_wake_command,
    has_program_action_intent,
    normalize_text,
    parse_dynamic_command,
    recognize_cmd,
)

speak_engine = None
vosk_model = None


def _vosk_model_path(model_path):
    path = str(model_path)
    if os.name != "nt" or path.isascii():
        return path

    get_short_path = ctypes.WinDLL("kernel32", use_last_error=True).GetShortPathNameW
    get_short_path.argtypes = (ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint)
    get_short_path.restype = ctypes.c_uint
    buffer = ctypes.create_unicode_buffer(32768)
    result = get_short_path(path, buffer, len(buffer))
    if not result:
        raise ctypes.WinError(ctypes.get_last_error())

    short_path = buffer.value
    if not short_path.isascii():
        raise OSError(
            f"Vosk потребує ASCII-шлях до моделі. Перемістіть модель у папку "
            f"з латинським шляхом або ввімкніть короткі імена Windows: {model_path}"
        )
    return short_path


def initialize_speech():
    global speak_engine
    speak_engine = pyttsx3.init()
    voices = speak_engine.getProperty("voices")
    speak_engine.setProperty("voice", voices[0].id)

def initialize_recognition():
    global vosk_model

    if ASR_BACKEND == "google":
        return
    if ASR_BACKEND != "vosk":
        raise ValueError(f"Невідомий рушій розпізнавання мовлення: {ASR_BACKEND}")

    model_path = Path(__file__).resolve().parent.parent / VOSK_MODEL_PATH
    if not model_path.is_dir():
        raise FileNotFoundError(
            f"Не знайдено модель Vosk: {model_path}. "
            "Завантажте українську модель Vosk і вкажіть її папку в VOSK_MODEL_PATH."
        )

    try:
        from vosk import Model
    except ImportError as error:
        raise RuntimeError(
            "Для офлайн-розпізнавання встановіть залежності з requirements.txt."
        ) from error

    vosk_model = Model(_vosk_model_path(model_path))

def _recognize_vosk(audio):
    if vosk_model is None:
        raise RuntimeError("Модель Vosk не ініціалізована.")

    from vosk import KaldiRecognizer

    recognizer = KaldiRecognizer(vosk_model, 16000)
    recognizer.AcceptWaveform(audio.get_raw_data(convert_rate=16000, convert_width=2))
    text = json.loads(recognizer.FinalResult()).get("text", "").strip()
    if not text:
        raise sr.UnknownValueError()
    return text

def speak(what):
    print("[log] Jarvis: " + what)
    speak_engine.say(what)
    speak_engine.runAndWait()
    speak_engine.stop()

def callback(recognizer, audio):
    try:
        if ASR_BACKEND == "vosk":
            voice = _recognize_vosk(audio).lower()
        else:
            voice = recognizer.recognize_google(audio, language="uk-UA").lower()
        print("[log] Заспознано: " + voice)

        # Якщо Джарвіс "спить"
        if not state.LISTENING:
            if extract_wake_command(voice) is not None:
                state.command_queue.put(("wake", None))
            return

        # Якщо в голосі є виклик до Джарвіса
        command_text = extract_wake_command(voice)
        if command_text is None:
            return
        if not command_text:
            state.command_queue.put(("wake", None))
            return

        dynamic_command = parse_dynamic_command(command_text)
        if dynamic_command is not None:
            state.command_queue.put(dynamic_command)
            return

        if has_program_action_intent(command_text):
            state.command_queue.put(("unrecognized", command_text))
            return

        # Якщо команда пуста — нічого не робимо
        cmd = command_text
        for x in opts['tbr']:
            cmd = cmd.replace(x, "").strip()

        if not cmd.strip():
            return

        if "таймер" in cmd:
            seconds = extract_timer_seconds(voice)
            state.command_queue.put(("timer", seconds))
            return

        result = recognize_cmd(cmd)
        if result['cmd']:
            state.command_queue.put(("command", result['cmd']))
        else:
            state.command_queue.put(("unrecognized", cmd))

    except sr.UnknownValueError:
        print("[log] Голос не распознан!")
    except sr.RequestError as e:
        print("[log] Неизвестная ошибка, проверьте интернет!")
    except Exception as e:
        print("[log] Помилка обробки голосової команди:", e)

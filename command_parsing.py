"""Text normalization and voice-command parsing."""

import re

from .config import CLOSABLE_PROGRAMS, PROGRAMS, opts

def extract_wake_command(voice):
    match = re.match(r"^\s*([^\W_]+)", voice, re.UNICODE)
    if not match:
        return None

    spoken_alias = normalize_text(match.group(1))
    aliases = [normalize_text(alias) for alias in opts["alias"]]
    if spoken_alias not in aliases:
        return None

    return voice[match.end():].strip(" ,.:;")

def parse_dynamic_command(voice):
    normalized_voice = normalize_text(voice)
    for prefix in ("відкрий ", "запусти ", "відкрий сайт ", "перейди на сайт "):
        if normalized_voice.startswith(prefix):
            target = normalized_voice[len(prefix):].strip()
            if target in (
                "youtube music", "ютуб мюзик", "ютуб мьюзик",
                "ютуб музик", "ютюб мюзик", "ютюб музик",
            ):
                return ("open_website", "youtube music")

    google_search = re.match(
        r"^(?:знайди|знайти|пошукай|пошук|пошукати)\s+(?:в|у)\s+"
        r"(?:google|гугл(?:і|а|у)?)\b(?:\s+(.*))?$",
        voice.strip(),
        re.IGNORECASE,
    )
    if google_search:
        query = (google_search.group(1) or "").strip(" .,!?:;")
        return ("web_search", query)

    for prefix in ("знайди в інтернеті ", "пошукай в інтернеті ", "пошук в інтернеті ",
                   "знайди ", "пошукай ", "пошук "):
        if voice.casefold().startswith(prefix):
            query = voice[len(prefix):].strip()
            return ("web_search", query) if query else ("web_search", "")

    for prefix in ("відкрий сайт ", "перейди на сайт "):
        if voice.startswith(prefix):
            return ("open_website", voice[len(prefix):].strip(" .,!?:;"))

    close_except_match = re.match(
        r"^(?:позакривай|закрий|закривай|закрити|закри)\s+"
        r"(?:всі|усі)\s+(?:програми|програм|додатки|додатків|вікна)"
        r"(?:\s+(?:окрім|крім|за винятком)\s+(.+))?$",
        normalize_text(voice),
    )
    if close_except_match:
        keep_names = split_program_list(close_except_match.group(1) or "")
        return ("close_programs_except", resolve_program_list(keep_names, CLOSABLE_PROGRAMS))

    action, target = parse_program_action(voice)
    if action:
        catalog = CLOSABLE_PROGRAMS if action == "close" else PROGRAMS
        targets = resolve_program_list(split_program_list(target), catalog)
        if action == "open" and len(targets) == 1 and targets[0] == "браузер":
            return ("launch_browser", None)
        if action == "open" and len(targets) == 1 and is_website_target(targets[0]):
            return ("open_website", targets[0])
        operation = "launch" if action == "open" else "close"
        if len(targets) > 1:
            return (f"{operation}_programs", targets)
        if targets:
            return (f"{operation}_program", targets[0])
        return (f"{operation}_program", target)

    return None

def parse_program_action(command_text):
    normalized = normalize_text(command_text)
    words = normalized.split()
    if not words:
        return None, ""

    close_verbs = ("закрий", "закрити", "закри", "закривай", "закрийте", "закрив")
    open_verbs = ("відкрий", "відкрити", "відкри", "відкривай", "відкрийте",
                  "запусти", "запустити", "запускай", "запускайте", "включи")
    verb = words[0]
    if verb in close_verbs:
        action, consumed = "close", 1
    elif verb in open_verbs:
        action, consumed = "open", 1
    else:
        return None, ""

    if len(words) > 1 and words[1] in ("програму", "додаток", "застосунок"):
        consumed += 1
    target = " ".join(words[consumed:])
    target = re.sub(r"^(?:мені|будь ласка|пожалуйста|прошу)\s+", "", target)
    target = re.sub(r"\s+(?:будь ласка|пожалуйста|прошу)$", "", target)
    return action, target.strip()

def has_program_action_intent(command_text):
    action, _ = parse_program_action(command_text)
    return action is not None

def split_program_list(target):
    return [
        item.strip(" .,!?:;").lower()
        for item in re.split(r"\s*(?:[,;]|\b(?:і|та|й)\b)\s*", target.lower())
        if item.strip(" .,!?:;")
    ]

def normalize_text(text):
    text = text.casefold().replace("'", "").replace("’", "").replace("ʼ", "")
    text = text.replace("ё", "е")
    text = " ".join(re.sub(r"[^\w\s]", " ", text).split())
    text = re.sub(r"\b(?:будь ласка|пожалуйста|прошу)\b", " ", text)
    return " ".join(text.split())

def resolve_program_name(name, programs):
    normalized_name = normalize_text(name)
    return next(
        (alias for alias in programs if normalize_text(alias) == normalized_name),
        None,
    )

def resolve_program_list(names, programs):
    return [resolve_program_name(name, programs) or name for name in names]

def is_website_target(target):
    return bool(re.fullmatch(
        r"(?:https?://)?(?:[a-z0-9-]+\.)+[a-z]{2,}(?:/[^\s]*)?",
        target
    ))

def extract_timer_seconds(voice):
    match = re.search(
        r'(\d+)\s*(секунд\w*|хвилин\w*|хв\b|годин\w*|год\b)',
        voice
    )
    if not match:
        return None

    amount = int(match.group(1))
    unit = match.group(2)
    if unit.startswith("год"):
        return amount * 3600
    if unit.startswith("хв"):
        return amount * 60
    return amount

def recognize_cmd(cmd):

    normalized_cmd = normalize_text(cmd)

    if re.search(r"\bне\b", normalized_cmd):
        return {
            "cmd": "",
            "percent": 0
        }

    best_command = ""
    best_score = 0

    for command_name, variants in opts["cmds"].items():

        for variant in variants:

            variant = normalize_text(variant)

            # Повний збіг
            if normalized_cmd == variant:

                return {
                    "cmd": command_name,
                    "percent": 100
                }

            # Частковий збіг

            variant_words = set(
                variant.split()
            )

            command_words = set(
                normalized_cmd.split()
            )

            common = len(
                variant_words &
                command_words
            )

            score = (
                common /
                max(
                    len(variant_words),
                    1
                )
            ) * 100

            if score > best_score:

                best_score = score

                best_command = command_name

    if best_score >= 60:

        return {
            "cmd": best_command,
            "percent": int(best_score)
        }

    return {
        "cmd": "",
        "percent": 0
    }

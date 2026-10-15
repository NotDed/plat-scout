"""Sound + desktop notification, so you notice while playing.

Every alert has a sound and how many times it plays. Defaults come from the
freedesktop sound theme; you can use any audio file instead:
  - drop .ogg / .oga / .wav / .flac / .mp3 files in data/sounds/ and pick them in
    the TUI (",") — they're listed first
  - or set a full path in the TUI (",", then "f") or in data/settings.json:
    {"sounds": {"message": ["/home/me/ping.mp3", 1]}}
Played with pw-play / paplay, or mpv / ffplay for formats those can't read.
Mute is remembered in data/settings.json.
"""

import json
import shlex
import shutil
import subprocess
import time
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data"
SETTINGS = DATA / "settings.json"
USER_SOUNDS = DATA / "sounds"  # your own sound files
SOUND_DIR = Path("/usr/share/sounds/freedesktop/stereo")
AUDIO = {".ogg", ".oga", ".wav", ".flac", ".mp3", ".opus"}
# kind -> (sound, times played)
SOUNDS = {
    "message": ("phone-incoming-call.oga", 2),  # someone whispered you (or a seller answered)
    "done": ("service-login.oga", 1),           # trade successful
}
LABELS = {"message": "incoming whisper", "done": "trade done"}
GAP = 0.15  # seconds between repeats
COOLDOWN = 60  # seconds: the same person rings at most once in this window (others always ring)
_last_heard = {}  # person -> when their last sound played
# (command, file types it reads; None = anything)
PLAYERS = ((["pw-play"], {".ogg", ".oga", ".wav", ".flac"}),
           (["paplay"], {".ogg", ".oga", ".wav", ".flac"}),
           (["mpv", "--no-video", "--really-quiet"], None),
           (["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet"], None))


# ---- settings -------------------------------------------------------------
def settings():
    try:
        return json.loads(SETTINGS.read_text())
    except (OSError, ValueError):
        return {}


def save_settings(s):
    DATA.mkdir(exist_ok=True)
    SETTINGS.write_text(json.dumps(s, indent=2))


def muted():
    return bool(settings().get("muted"))


def set_muted(value):
    s = settings()
    s["muted"] = bool(value)
    save_settings(s)


# ---- which sound ----------------------------------------------------------
def resolve(name):
    """A sound setting -> file: a full path, a file in data/sounds/, or a theme sound."""
    path = Path(name).expanduser()
    if path.is_absolute():
        return path
    for folder in (USER_SOUNDS, SOUND_DIR):
        if (folder / name).exists():
            return folder / name
    return SOUND_DIR / name


def sound_for(kind):
    """(path, times) for this alert, with any override from settings.json."""
    name, times = settings().get("sounds", {}).get(kind) or SOUNDS.get(kind, SOUNDS["message"])
    return resolve(name), max(1, int(times))


def available_sounds():
    """Files to choose from: yours (data/sounds/) first, then the system theme."""
    def files(folder):
        return sorted(str(p) for p in folder.glob("*") if p.suffix.lower() in AUDIO) \
            if folder.exists() else []
    return files(USER_SOUNDS) + files(SOUND_DIR)


def is_custom(path):
    """True for your own files (anything outside the system sound theme)."""
    return Path(path).parent != SOUND_DIR


def set_sound(kind, path, times):
    """Store a sound for an alert: theme sounds by name, anything else by full path."""
    path = Path(path).expanduser()
    value = path.name if path.parent == SOUND_DIR else str(path)
    s = settings()
    s.setdefault("sounds", {})[kind] = [value, max(1, min(5, int(times)))]
    save_settings(s)


def reset_sound(kind):
    s = settings()
    s.get("sounds", {}).pop(kind, None)
    save_settings(s)


def check_file(text):
    """Validate a path typed by the user; returns (Path, error)."""
    path = Path(text.strip().strip("'\"")).expanduser()
    if not path.is_file():
        return None, f"no file at {path}"
    if path.suffix.lower() not in AUDIO:
        return None, f"{path.suffix or 'that file'} isn't a sound file ({', '.join(sorted(AUDIO))})"
    if not player_for(path):
        return None, f"nothing installed can play {path.suffix} (install mpv or ffplay)"
    return path.resolve(), None


# ---- playing --------------------------------------------------------------
def player_for(path):
    for cmd, types in PLAYERS:
        if shutil.which(cmd[0]) and (types is None or Path(path).suffix.lower() in types):
            return cmd
    return None


def _spawn(cmd):
    try:
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
        return True
    except OSError:
        return False


def play_file(path, times=1):
    """Play a file (repeated) in the background; False if it can't be played."""
    path = Path(path)
    cmd = player_for(path) if path.exists() else None
    if not cmd:
        return False
    one = " ".join(shlex.quote(part) for part in cmd + [str(path)])
    return _spawn(["sh", "-c", f"; sleep {GAP}; ".join([one] * max(1, times))])


def play(kind):
    """Play the sound for this kind of alert; False if no player could."""
    path, times = sound_for(kind)
    return play_file(path, times)


def cooldown():
    return int(settings().get("cooldownSeconds", COOLDOWN))


def set_cooldown(seconds):
    s = settings()
    s["cooldownSeconds"] = max(0, min(600, int(seconds)))
    save_settings(s)


def notify(title, body=""):
    if shutil.which("notify-send"):
        _spawn(["notify-send", "--app-name=plat-scout", title, body])


def alert(kind, title, body="", who=None, now=None):
    """Sound + desktop notification. Returns "played", "muted", "limited" (the same
    person alerted less than cooldown() seconds ago) or "failed" (no player).
    Only whisper/answer alerts ("message") are limited, and only per person."""
    if muted():
        return "muted"
    now = now or time.time()
    if who and kind == "message":
        key = who.lower()
        if now - _last_heard.get(key, -1e9) < cooldown():
            return "limited"
        _last_heard[key] = now
    notify(title, body)
    return "played" if play(kind) else "failed"

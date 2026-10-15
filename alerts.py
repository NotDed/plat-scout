"""Sound + desktop notification, so you notice while playing.

Sounds are the freedesktop ones played with pw-play (PipeWire) or paplay
(PulseAudio); the notification uses notify-send. Anything missing is skipped.
Mute is remembered in data/settings.json.
"""

import json
import shutil
import subprocess
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data"
SETTINGS = DATA / "settings.json"
SOUND_DIR = Path("/usr/share/sounds/freedesktop/stereo")
SOUNDS = {
    "message": "message-new-instant.oga",  # someone whispered / a seller answered
    "done": "complete.oga",                # trade successful
    "bell": "bell.oga",                    # a seller hasn't answered
}
PLAYERS = (["pw-play"], ["paplay"])


def settings():
    try:
        return json.loads(SETTINGS.read_text())
    except (OSError, ValueError):
        return {}


def muted():
    return bool(settings().get("muted"))


def set_muted(value):
    s = settings()
    s["muted"] = bool(value)
    DATA.mkdir(exist_ok=True)
    SETTINGS.write_text(json.dumps(s))


def _spawn(cmd):
    try:
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
        return True
    except OSError:
        return False


def play(kind):
    """Play the sound for this kind of alert; False if no player could."""
    sound = SOUND_DIR / SOUNDS.get(kind, SOUNDS["message"])
    if not sound.exists():
        return False
    for player in PLAYERS:
        if shutil.which(player[0]) and _spawn(player + [str(sound)]):
            return True
    return False


def notify(title, body=""):
    if shutil.which("notify-send"):
        _spawn(["notify-send", "--app-name=plat-scout", title, body])


def alert(kind, title, body=""):
    """Sound + desktop notification unless muted. Returns whether a sound played."""
    if muted():
        return False
    notify(title, body)
    return play(kind)

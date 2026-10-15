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
# kind -> (sound, times played). Loud enough to notice over the game; change them in
# data/settings.json: {"sounds": {"message": ["window-attention.oga", 1]}} (a name from
# the folder above or a full path to any .oga/.wav/.ogg).
SOUNDS = {
    "message": ("phone-incoming-call.oga", 2),  # someone whispered / a seller answered
    "done": ("service-login.oga", 1),           # trade successful
    "bell": ("dialog-warning.oga", 2),          # a seller hasn't answered
}
GAP = 0.15  # seconds between repeats
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


def sound_for(kind):
    """(path, times) for this alert, with any override from settings.json."""
    name, times = settings().get("sounds", {}).get(kind) or SOUNDS.get(kind, SOUNDS["message"])
    path = Path(name).expanduser()
    if not path.is_absolute():
        path = SOUND_DIR / name
    return path, max(1, int(times))


def play(kind):
    """Play the sound for this kind of alert; False if no player could."""
    sound, times = sound_for(kind)
    if not sound.exists():
        return False
    for player in PLAYERS:
        if shutil.which(player[0]):
            # repeat in one background shell so the TUI never waits
            cmd = f"; sleep {GAP}; ".join([f"{player[0]} '{sound}'"] * times)
            return _spawn(["sh", "-c", cmd])
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

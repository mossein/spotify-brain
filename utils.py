import json
import sys
from pathlib import Path

BASE_DIR = Path.home() / ".spotify-brain"
DATA_DIR = BASE_DIR / "data"
CONFIG_FILE = BASE_DIR / "config.json"
FINGERPRINT_FILE = BASE_DIR / "fingerprint.json"
PULL_META_FILE = DATA_DIR / "pull_meta.json"

# ANSI color helpers
BOLD = "\033[1m"
DIM = "\033[2m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
CYAN = "\033[36m"
MAGENTA = "\033[35m"
RED = "\033[31m"
RESET = "\033[0m"


def ensure_dirs():
    BASE_DIR.mkdir(exist_ok=True)
    DATA_DIR.mkdir(exist_ok=True)


def load_json(name):
    path = DATA_DIR / f"{name}.json"
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def save_json(name, data):
    ensure_dirs()
    path = DATA_DIR / f"{name}.json"
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def load_config():
    if not CONFIG_FILE.exists():
        return None
    with open(CONFIG_FILE) as f:
        return json.load(f)


def save_config(config):
    ensure_dirs()
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)


def format_track(track):
    artists = ", ".join(a["name"] for a in track["artists"])
    name = track["name"]
    album = track["album"]["name"] if "album" in track else ""
    year = ""
    if "album" in track and "release_date" in track["album"]:
        year = track["album"]["release_date"][:4]
    if album and year:
        return f"{artists} - {name} ({album}, {year})"
    return f"{artists} - {name}"


def format_track_short(track):
    artists = ", ".join(a["name"] for a in track["artists"])
    return f"{artists} - {track['name']}"


def print_bar_chart(data, max_width=40, color=CYAN):
    if not data:
        return
    max_val = max(data.values())
    for label, val in data.items():
        bar_len = int((val / max_val) * max_width) if max_val > 0 else 0
        bar = "█" * bar_len
        print(f"  {label:>20s}  {color}{bar}{RESET} {val:.1f}%" if isinstance(val, float)
              else f"  {label:>20s}  {color}{bar}{RESET} {val}")


def progress(current, total, prefix=""):
    pct = int((current / total) * 100) if total > 0 else 0
    sys.stdout.write(f"\r  {prefix}{current}/{total} ({pct}%)")
    sys.stdout.flush()
    if current >= total:
        print()

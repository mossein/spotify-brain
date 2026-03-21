#!/usr/bin/env python3
"""Compile the full Spotify library into a dense text file optimized for Claude to read."""

import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

DATA_DIR = Path.home() / ".spotify-brain" / "data"
OUTPUT = Path(__file__).parent / "library.txt"


def load(name):
    path = DATA_DIR / f"{name}.json"
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def compile():
    saved = load("saved_tracks") or []
    recent = load("recently_played") or []
    top_short = load("top_artists_short_term") or []
    top_medium = load("top_artists_medium_term") or []
    top_long = load("top_artists_long_term") or []
    top_tracks_short = load("top_tracks_short_term") or []
    top_tracks_medium = load("top_tracks_medium_term") or []
    top_tracks_long = load("top_tracks_long_term") or []
    meta = load("pull_meta") or {}

    saved_ids = set(item["track"]["id"] for item in saved if item.get("track"))

    lines = []
    lines.append(f"SPOTIFY LIBRARY: {meta.get('user', 'unknown')}")
    lines.append(f"Pulled: {meta.get('last_pull', 'unknown')}")
    lines.append(f"Total saved: {len(saved)}")
    lines.append("")

    # All saved tracks chronologically (oldest first)
    lines.append("=== ALL SAVED TRACKS (chronological) ===")
    for item in reversed(saved):
        t = item["track"]
        artists = ", ".join(a["name"] for a in t["artists"])
        album = t["album"]["name"]
        year = t["album"].get("release_date", "")[:4]
        added = item.get("added_at", "")[:10]
        dur = t.get("duration_ms", 0)
        dur_str = f"{dur // 60000}:{(dur % 60000) // 1000:02d}" if dur else "?"
        explicit = " [E]" if t.get("explicit") else ""
        lines.append(f"[{added}] {artists} - {t['name']} | {album} ({year}) | {dur_str}{explicit}")

    lines.append("")

    # Top artists
    lines.append("=== TOP ARTISTS (short term / 4 weeks) ===")
    for i, a in enumerate(top_short, 1):
        lines.append(f"{i}. {a['name']}")

    lines.append("")
    lines.append("=== TOP ARTISTS (medium term / 6 months) ===")
    for i, a in enumerate(top_medium, 1):
        lines.append(f"{i}. {a['name']}")

    lines.append("")
    lines.append("=== TOP ARTISTS (long term / all time) ===")
    for i, a in enumerate(top_long, 1):
        lines.append(f"{i}. {a['name']}")

    lines.append("")

    # Top tracks (with save status - the gap between played and saved is key)
    for label, tracks in [("short term / 4 weeks", top_tracks_short),
                          ("medium term / 6 months", top_tracks_medium),
                          ("long term / all time", top_tracks_long)]:
        lines.append(f"=== TOP TRACKS ({label}) ===")
        for i, t in enumerate(tracks, 1):
            artists = ", ".join(a["name"] for a in t["artists"])
            status = "SAVED" if t["id"] in saved_ids else "NOT SAVED"
            lines.append(f"{i}. {artists} - {t['name']} [{status}]")
        lines.append("")

    lines.append("")

    # Recently played
    lines.append("=== RECENTLY PLAYED ===")
    for item in recent:
        t = item["track"]
        artists = ", ".join(a["name"] for a in t["artists"])
        played = item.get("played_at", "")[:16].replace("T", " ")
        lines.append(f"[{played}] {artists} - {t['name']}")

    lines.append("")

    # Play history (accumulated sessions)
    history_path = DATA_DIR / "play_history.json"
    if history_path.exists():
        with open(history_path) as f:
            history = json.load(f)
        lines.append(f"=== PLAY HISTORY ({len(history)} total plays) ===")
        for item in history:
            t = item["track"]
            artists = ", ".join(a["name"] for a in t["artists"])
            played = item.get("played_at", "")[:16].replace("T", " ")
            in_lib = "SAVED" if t["id"] in saved_ids else "NOT SAVED"
            lines.append(f"[{played}] {artists} - {t['name']} [{in_lib}]")
        lines.append("")

    # Unsaved obsessions - most played but never saved
    lines.append("=== UNSAVED OBSESSIONS (most played but never saved) ===")
    for label, tracks in [("all time", top_tracks_long), ("6 months", top_tracks_medium),
                          ("4 weeks", top_tracks_short)]:
        unsaved = [t for t in tracks if t["id"] not in saved_ids]
        if unsaved:
            lines.append(f"  {label}:")
            for t in unsaved:
                artists = ", ".join(a["name"] for a in t["artists"])
                lines.append(f"    {artists} - {t['name']}")
    lines.append("")

    # Computed stats
    lines.append("=== COMPUTED STATS ===")

    # Artist frequency
    artist_counts = Counter()
    for item in saved:
        for a in item["track"]["artists"]:
            artist_counts[a["name"]] += 1

    lines.append("Top 30 most-saved artists:")
    for name, count in artist_counts.most_common(30):
        lines.append(f"  {name}: {count}")

    # Decade distribution
    decade_counts = Counter()
    for item in saved:
        try:
            y = int(item["track"]["album"]["release_date"][:4])
            if 1900 < y < 2030:
                decade_counts[f"{(y // 10) * 10}s"] += 1
        except (ValueError, KeyError):
            pass

    lines.append("\nDecade distribution:")
    for d, c in sorted(decade_counts.items()):
        lines.append(f"  {d}: {c}")

    # Monthly save counts
    month_counts = Counter()
    for item in saved:
        month_counts[item["added_at"][:7]] += 1

    lines.append("\nMonthly save counts:")
    for m, c in sorted(month_counts.items()):
        lines.append(f"  {m}: {c}")

    # Explicit ratio
    total = len(saved)
    explicit = sum(1 for item in saved if item["track"].get("explicit"))
    lines.append(f"\nExplicit: {explicit}/{total} ({explicit / total * 100:.0f}%)")

    # Duration stats
    durations = [item["track"]["duration_ms"] for item in saved if item["track"].get("duration_ms")]
    if durations:
        avg = sum(durations) / len(durations) / 60000
        total_hrs = sum(durations) / 3600000
        lines.append(f"Avg duration: {avg:.1f} min")
        lines.append(f"Total duration: {total_hrs:.0f} hours")

    output = "\n".join(lines)
    with open(OUTPUT, "w") as f:
        f.write(output)

    print(f"Compiled {len(saved)} tracks to {OUTPUT}")
    print(f"File size: {len(output) / 1024:.0f} KB")


if __name__ == "__main__":
    compile()

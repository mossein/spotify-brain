#!/usr/bin/env python3
"""Export a compact, shareable library snapshot for relationship readings.

This produces a single JSON file that someone can send to another person.
It contains everything needed for a deep reading but strips out raw IDs
and images to keep it small and readable.
"""

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path.home() / ".spotify-brain" / "data"
OUTPUT_DIR = Path(__file__).parent


def load(name):
    path = DATA_DIR / f"{name}.json"
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def export():
    saved = load("saved_tracks") or []
    top_tracks_short = load("top_tracks_short_term") or []
    top_tracks_medium = load("top_tracks_medium_term") or []
    top_tracks_long = load("top_tracks_long_term") or []
    top_artists_short = load("top_artists_short_term") or []
    top_artists_medium = load("top_artists_medium_term") or []
    top_artists_long = load("top_artists_long_term") or []
    recent = load("recently_played") or []
    history = load("play_history") or []
    meta = load("pull_meta") or {}

    saved_ids = set(item["track"]["id"] for item in saved if item.get("track"))

    def compact_track(t, added_at=None):
        artists = ", ".join(a["name"] for a in t.get("artists", []))
        year = t.get("album", {}).get("release_date", "")[:4]
        dur_ms = t.get("duration_ms", 0)
        result = {
            "artists": artists,
            "name": t["name"],
            "album": t.get("album", {}).get("name", ""),
            "year": year,
            "duration": f"{dur_ms // 60000}:{(dur_ms % 60000) // 1000:02d}" if dur_ms else "",
            "explicit": t.get("explicit", False),
        }
        if added_at:
            result["added"] = added_at[:10]
        return result

    # Build the export
    export_data = {
        "version": 2,
        "exported": datetime.now(timezone.utc).isoformat(),
        "user": meta.get("user", "unknown"),

        # Full saved library (chronological, oldest first)
        "saved_tracks": [
            compact_track(item["track"], item.get("added_at"))
            for item in reversed(saved) if item.get("track")
        ],

        # Top tracks with save status
        "top_tracks": {
            "short_term": [
                {**compact_track(t), "saved": t["id"] in saved_ids}
                for t in top_tracks_short
            ],
            "medium_term": [
                {**compact_track(t), "saved": t["id"] in saved_ids}
                for t in top_tracks_medium
            ],
            "long_term": [
                {**compact_track(t), "saved": t["id"] in saved_ids}
                for t in top_tracks_long
            ],
        },

        # Top artists
        "top_artists": {
            "short_term": [a["name"] for a in top_artists_short],
            "medium_term": [a["name"] for a in top_artists_medium],
            "long_term": [a["name"] for a in top_artists_long],
        },

        # Play history
        "play_history": [
            {
                "played_at": item.get("played_at", "")[:16],
                "artists": ", ".join(a["name"] for a in item["track"].get("artists", [])),
                "name": item["track"]["name"],
                "saved": item["track"]["id"] in saved_ids,
            }
            for item in history
        ],

        # Computed stats
        "stats": {
            "total_saved": len(saved),
            "unique_artists": len(set(
                a["name"] for item in saved for a in item["track"].get("artists", [])
            )),
            "explicit_pct": round(
                sum(1 for item in saved if item["track"].get("explicit")) / max(len(saved), 1) * 100
            ),
            "top_saved_artists": [
                {"name": name, "count": count}
                for name, count in Counter(
                    a["name"] for item in saved for a in item["track"].get("artists", [])
                ).most_common(30)
            ],
            "decade_distribution": dict(sorted(
                Counter(
                    f"{(int(item['track']['album']['release_date'][:4]) // 10) * 10}s"
                    for item in saved
                    if item.get("track", {}).get("album", {}).get("release_date", "")[:4].isdigit()
                    and 1900 < int(item["track"]["album"]["release_date"][:4]) < 2030
                ).items()
            )),
            "monthly_saves": dict(sorted(
                Counter(item["added_at"][:7] for item in saved).items()
            )),
        },
    }

    # Save it
    username = meta.get("user", "unknown").lower().replace(" ", "-")
    output_path = OUTPUT_DIR / f"{username}-library.json"
    with open(output_path, "w") as f:
        json.dump(export_data, f, indent=2)

    size_kb = output_path.stat().st_size / 1024
    print(f"Exported to {output_path} ({size_kb:.0f} KB)")
    print(f"Share this file with someone to get a relationship reading.")
    print(f"\nThey run:  python3 brain.py reading-together your-file.json their-file.json")
    return output_path


if __name__ == "__main__":
    export()

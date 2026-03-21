import time
from datetime import datetime, timezone

from auth import get_spotify_client
from utils import save_json, load_json, progress, BOLD, GREEN, RESET, PULL_META_FILE

import json


def pull_saved_tracks(sp):
    print(f"\n{BOLD}Fetching saved tracks...{RESET}")
    tracks = []
    offset = 0
    limit = 50
    # Get first batch to know total
    results = sp.current_user_saved_tracks(limit=limit, offset=0)
    total = results["total"]
    for item in results["items"]:
        tracks.append(item)
    offset += limit
    progress(len(tracks), total, "Saved tracks: ")

    while offset < total:
        results = sp.current_user_saved_tracks(limit=limit, offset=offset)
        for item in results["items"]:
            tracks.append(item)
        offset += limit
        progress(len(tracks), total, "Saved tracks: ")
        time.sleep(0.05)

    save_json("saved_tracks", tracks)
    print(f"  {GREEN}Saved {len(tracks)} tracks{RESET}")
    return tracks


def pull_top_items(sp):
    print(f"\n{BOLD}Fetching top tracks and artists...{RESET}")
    for time_range in ["short_term", "medium_term", "long_term"]:
        label = {"short_term": "4 weeks", "medium_term": "6 months", "long_term": "all time"}[time_range]

        # Top tracks (max 50 per request, can get up to 99 with offset)
        tracks = []
        for offset in [0, 49]:
            results = sp.current_user_top_tracks(limit=50, offset=offset, time_range=time_range)
            tracks.extend(results["items"])
            if len(results["items"]) < 50:
                break
        save_json(f"top_tracks_{time_range}", tracks)
        print(f"  Top tracks ({label}): {len(tracks)}")

        # Top artists
        artists = []
        for offset in [0, 49]:
            results = sp.current_user_top_artists(limit=50, offset=offset, time_range=time_range)
            artists.extend(results["items"])
            if len(results["items"]) < 50:
                break
        save_json(f"top_artists_{time_range}", artists)
        print(f"  Top artists ({label}): {len(artists)}")
        time.sleep(0.05)


def pull_recently_played(sp):
    print(f"\n{BOLD}Fetching recently played...{RESET}")
    results = sp.current_user_recently_played(limit=50)
    new_plays = results["items"]

    # Accumulate history instead of overwriting
    existing = load_json("play_history") or []
    existing_timestamps = set(item.get("played_at", "") for item in existing)

    added = 0
    for play in new_plays:
        if play.get("played_at", "") not in existing_timestamps:
            existing.append(play)
            added += 1

    existing.sort(key=lambda x: x.get("played_at", ""))
    save_json("play_history", existing)

    # Also keep the latest snapshot for backwards compat
    save_json("recently_played", new_plays)

    print(f"  {GREEN}Got {len(new_plays)} recent plays, {added} new (total history: {len(existing)}){RESET}")
    return new_plays


def pull_artist_details(sp):
    """Fetch full artist details (with genres) for all unique artists."""
    print(f"\n{BOLD}Fetching artist details (genres)...{RESET}")

    # Collect unique artist IDs from all sources
    artist_ids = set()

    saved = load_json("saved_tracks") or []
    for item in saved:
        for a in item["track"]["artists"]:
            artist_ids.add(a["id"])

    for time_range in ["short_term", "medium_term", "long_term"]:
        top_artists = load_json(f"top_artists_{time_range}") or []
        for a in top_artists:
            artist_ids.add(a["id"])
        top_tracks = load_json(f"top_tracks_{time_range}") or []
        for t in top_tracks:
            for a in t["artists"]:
                artist_ids.add(a["id"])

    artist_ids = [aid for aid in artist_ids if aid is not None]
    total = len(artist_ids)
    print(f"  {total} unique artists to fetch")

    # Batch requests (50 per call - API limit)
    artists = {}
    for i in range(0, total, 50):
        batch = artist_ids[i:i + 50]
        try:
            results = sp.artists(batch)
            if results and "artists" in results:
                for a in results["artists"]:
                    if a:
                        artists[a["id"]] = a
        except Exception as e:
            print(f"\n  Warning: artist batch failed ({e}), continuing...")
        progress(min(i + 50, total), total, "Artists: ")
        time.sleep(0.05)

    save_json("artist_details", artists)
    print(f"  {GREEN}Got details for {len(artists)} artists{RESET}")

    # Count genres to verify
    genre_count = sum(len(a.get("genres", [])) for a in artists.values())
    print(f"  {genre_count} genre tags total")
    return artists


def pull_audio_features(sp):
    print(f"\n{BOLD}Fetching audio features...{RESET}")

    # Collect all unique track IDs across all cached data
    track_ids = set()

    saved = load_json("saved_tracks") or []
    for item in saved:
        track_ids.add(item["track"]["id"])

    for time_range in ["short_term", "medium_term", "long_term"]:
        top = load_json(f"top_tracks_{time_range}") or []
        for t in top:
            track_ids.add(t["id"])

    recent = load_json("recently_played") or []
    for item in recent:
        track_ids.add(item["track"]["id"])

    track_ids = [tid for tid in track_ids if tid is not None]
    total = len(track_ids)
    print(f"  {total} unique tracks to analyze")

    # Batch requests (100 per call)
    features = {}
    for i in range(0, total, 100):
        batch = track_ids[i:i + 100]
        try:
            results = sp.audio_features(batch)
            if results:
                for feat in results:
                    if feat:
                        features[feat["id"]] = feat
        except Exception as e:
            print(f"\n  Warning: audio features batch failed ({e}), continuing...")
        progress(min(i + 100, total), total, "Audio features: ")
        time.sleep(0.1)

    save_json("audio_features", features)
    print(f"  {GREEN}Got features for {len(features)} tracks{RESET}")
    return features


def pull_all():
    sp = get_spotify_client()

    # Get user profile for context
    me = sp.current_user()
    print(f"\n{BOLD}Logged in as: {GREEN}{me['display_name']}{RESET}")

    pull_saved_tracks(sp)
    pull_top_items(sp)
    pull_recently_played(sp)
    pull_artist_details(sp)
    features = pull_audio_features(sp)

    # Save pull metadata
    meta = {
        "last_pull": datetime.now(timezone.utc).isoformat(),
        "user": me["display_name"],
        "user_id": me["id"],
    }
    save_json("pull_meta", meta)

    print(f"\n{BOLD}{GREEN}Pull complete!{RESET} Data cached in ~/.spotify-brain/data/")

    # Quick warning if audio features came back empty
    if not features:
        print(f"\n  {BOLD}Note:{RESET} Audio features returned empty. Spotify may have deprecated")
        print(f"  this endpoint for your app type. Insights will work with genre/artist data only.")

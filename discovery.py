import random
import time
from collections import Counter

from auth import get_spotify_client
from utils import (
    load_json, format_track, format_track_short,
    BOLD, DIM, GREEN, YELLOW, CYAN, MAGENTA, RED, RESET
)


def _get_library_track_ids():
    saved = load_json("saved_tracks") or []
    return set(item["track"]["id"] for item in saved if item.get("track"))


def _get_library_track_names():
    """Fallback matching by name when IDs don't match."""
    saved = load_json("saved_tracks") or []
    names = set()
    for item in saved:
        t = item.get("track")
        if t:
            key = f"{t['artists'][0]['name'].lower()}:{t['name'].lower()}" if t.get("artists") else t["name"].lower()
            names.add(key)
    return names


def _track_name_key(track):
    if track.get("artists"):
        return f"{track['artists'][0]['name'].lower()}:{track['name'].lower()}"
    return track["name"].lower()


def discover_deep_cuts(sp, library_ids, library_names, limit=10):
    """Find tracks from your top artists' albums that you haven't saved."""
    print(f"\n{BOLD}{'=' * 50}")
    print(f"  DEEP CUTS FROM YOUR ARTISTS")
    print(f"{'=' * 50}{RESET}")
    print(f"  {DIM}Tracks you might have missed from artists you love{RESET}\n")

    # Get top artists from different time ranges
    top_artists = []
    seen_ids = set()
    for time_range in ["short_term", "medium_term", "long_term"]:
        artists = load_json(f"top_artists_{time_range}") or []
        for a in artists:
            if a["id"] not in seen_ids:
                seen_ids.add(a["id"])
                top_artists.append(a)

    if not top_artists:
        print("  No top artists data. Run 'pull' first.")
        return

    discoveries = []
    artists_scanned = 0

    for artist in top_artists[:15]:
        print(f"  Scanning {artist['name']}...", end="", flush=True)
        found = 0

        try:
            # Get all albums
            albums = sp.artist_albums(artist["id"], album_type="album,single", limit=10)
            for album in albums["items"]:
                try:
                    tracks = sp.album_tracks(album["id"], limit=10)
                    for t in tracks["items"]:
                        # Build a pseudo-full track object
                        full_track = {
                            "id": t["id"],
                            "name": t["name"],
                            "artists": t["artists"],
                            "album": {
                                "name": album["name"],
                                "id": album["id"],
                                "release_date": album.get("release_date", ""),
                                "images": album.get("images", []),
                            },
                            "duration_ms": t.get("duration_ms", 0),
                            "external_urls": t.get("external_urls", {}),
                        }

                        # Check if not in library (by ID and by name)
                        if t["id"] not in library_ids and _track_name_key(full_track) not in library_names:
                            discoveries.append((artist["name"], full_track))
                            found += 1
                except Exception:
                    continue

                time.sleep(0.05)

        except Exception as e:
            print(f" error: {e}")
            continue

        print(f" +{found} unsaved tracks")
        artists_scanned += 1

        if artists_scanned >= 10 and len(discoveries) >= limit * 3:
            break

    if not discoveries:
        print("\n  You've already saved everything from your top artists!")
        return

    # Pick a diverse sample
    by_artist = {}
    for artist_name, track in discoveries:
        by_artist.setdefault(artist_name, []).append(track)

    # Take up to 2-3 per artist for variety
    selected = []
    for artist_name, tracks in by_artist.items():
        sample = random.sample(tracks, min(3, len(tracks)))
        selected.extend((artist_name, t) for t in sample)

    random.shuffle(selected)
    selected = selected[:limit]

    print(f"\n  {BOLD}Discovered {len(selected)} tracks you might like:{RESET}\n")
    for i, (artist_name, t) in enumerate(selected, 1):
        url = t.get("external_urls", {}).get("spotify", "")
        album = t.get("album", {}).get("name", "")
        year = t.get("album", {}).get("release_date", "")[:4]
        artists = ", ".join(a["name"] for a in t.get("artists", []))
        print(f"  {DIM}{i:>3}.{RESET} {artists} - {t['name']}")
        print(f"       {DIM}{album} ({year})  {url}{RESET}")


def discover_by_search(sp, library_ids, library_names, query, limit=10):
    """Search-based discovery - find tracks matching a query that aren't in your library."""
    print(f"\n{BOLD}{'=' * 50}")
    print(f"  SEARCH: \"{query}\"")
    print(f"{'=' * 50}{RESET}\n")

    try:
        results = sp.search(query, type="track", limit=10)
    except Exception as e:
        print(f"  Search error: {e}")
        return

    tracks = results.get("tracks", {}).get("items", [])
    new_tracks = [t for t in tracks if t["id"] not in library_ids and _track_name_key(t) not in library_names]

    if not new_tracks:
        print(f"  All results are already in your library!")
        return

    print(f"  {BOLD}{len(new_tracks)} tracks not in your library:{RESET}\n")
    for i, t in enumerate(new_tracks[:limit], 1):
        url = t.get("external_urls", {}).get("spotify", "")
        print(f"  {DIM}{i:>3}.{RESET} {format_track(t)}")
        print(f"       {DIM}{url}{RESET}")


def discover_similar_era(sp, library_ids, library_names, limit=10):
    """Find tracks from the same era and style as your library."""
    print(f"\n{BOLD}{'=' * 50}")
    print(f"  ERA EXPLORER")
    print(f"{'=' * 50}{RESET}")
    print(f"  {DIM}Searching for tracks from your favorite eras{RESET}\n")

    saved = load_json("saved_tracks") or []

    # Find your top artists + their eras
    artist_counts = Counter()
    artist_names = {}
    for item in saved:
        t = item.get("track")
        if t:
            for a in t.get("artists", []):
                artist_counts[a["id"]] += 1
                artist_names[a["id"]] = a["name"]

    # Search for tracks by combining your top artist names with era keywords
    top_artists = [artist_names[aid] for aid, _ in artist_counts.most_common(20)]

    discoveries = []
    queries_tried = set()

    # Pick random artists and search for related music
    sample_artists = random.sample(top_artists[:15], min(8, len(top_artists)))

    for artist_name in sample_artists:
        query = f"artist:{artist_name}"
        if query in queries_tried:
            continue
        queries_tried.add(query)

        try:
            results = sp.search(query, type="track", limit=10)
            tracks = results.get("tracks", {}).get("items", [])
            new = [t for t in tracks if t["id"] not in library_ids and _track_name_key(t) not in library_names]
            discoveries.extend(new[:5])
        except Exception:
            continue
        time.sleep(0.05)

    if not discoveries:
        print("  No new tracks found!")
        return

    # Deduplicate
    seen = set()
    unique = []
    for t in discoveries:
        if t["id"] not in seen:
            seen.add(t["id"])
            unique.append(t)

    random.shuffle(unique)
    unique = unique[:limit]

    print(f"  {BOLD}Found {len(unique)} tracks to explore:{RESET}\n")
    for i, t in enumerate(unique, 1):
        url = t.get("external_urls", {}).get("spotify", "")
        print(f"  {DIM}{i:>3}.{RESET} {format_track(t)}")
        print(f"       {DIM}{url}{RESET}")


def run_discovery(mood=None, deep_cuts=False, explore_genre=None):
    sp = get_spotify_client()
    library_ids = _get_library_track_ids()
    library_names = _get_library_track_names()

    print(f"\n{BOLD}{MAGENTA}spotify-brain discover{RESET}")
    print(f"  {DIM}Library has {len(library_ids)} tracks to filter against{RESET}")

    if deep_cuts:
        discover_deep_cuts(sp, library_ids, library_names)
    elif explore_genre:
        # Use search with genre as query
        discover_by_search(sp, library_ids, library_names, explore_genre)
    elif mood:
        # Use search with mood as query combined with user's style
        top_artists = load_json("top_artists_short_term") or []
        if top_artists:
            artist = random.choice(top_artists[:5])["name"]
            query = f"{mood} {artist}"
        else:
            query = mood
        discover_by_search(sp, library_ids, library_names, query)
    else:
        # Default: deep cuts + era explorer
        discover_deep_cuts(sp, library_ids, library_names, limit=10)
        discover_similar_era(sp, library_ids, library_names, limit=10)

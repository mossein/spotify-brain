import json
import numpy as np
from collections import Counter
from datetime import datetime, timezone

from utils import (
    load_json, BOLD, DIM, GREEN, YELLOW, CYAN, MAGENTA, RED, RESET,
    FINGERPRINT_FILE, BASE_DIR
)


def _compute_audio_profile():
    features = load_json("audio_features") or {}
    if not features:
        return {}

    keys = ["danceability", "energy", "valence", "acousticness",
            "instrumentalness", "speechiness", "tempo"]

    profile = {}
    for k in keys:
        vals = [f[k] for f in features.values() if k in f and f[k] is not None]
        if vals:
            profile[k] = {"mean": float(np.mean(vals)), "std": float(np.std(vals))}
    return profile


def _compute_genre_weights():
    artist_details = load_json("artist_details") or {}
    genre_counts = Counter()
    for aid, artist in artist_details.items():
        for g in artist.get("genres", []):
            genre_counts[g] += 1

    total = sum(genre_counts.values()) or 1
    return [{"genre": g, "weight": round(c / total, 4)} for g, c in genre_counts.most_common(20)]


def _compute_top_artists():
    # Weighted by recency: short_term artists get more weight
    scores = Counter()
    names = {}
    weights = {"short_term": 3, "medium_term": 2, "long_term": 1}

    for time_range, weight in weights.items():
        artists = load_json(f"top_artists_{time_range}") or []
        for i, a in enumerate(artists):
            # Higher rank = more points, multiplied by recency weight
            score = (len(artists) - i) * weight
            scores[a["id"]] += score
            names[a["id"]] = a["name"]

    total = sum(scores.values()) or 1
    top = scores.most_common(30)
    return [{"id": aid, "name": names[aid], "weight": round(s / total, 4)} for aid, s in top]


def _compute_decade_distribution():
    saved = load_json("saved_tracks") or []
    decade_counts = Counter()

    for item in saved:
        t = item.get("track")
        if t and "album" in t and "release_date" in t["album"]:
            try:
                year = int(t["album"]["release_date"][:4])
                decade = f"{(year // 10) * 10}s"
                decade_counts[decade] += 1
            except ValueError:
                pass

    total = sum(decade_counts.values()) or 1
    return {d: round(c / total, 4) for d, c in sorted(decade_counts.items())}


def _compute_popularity_profile():
    saved = load_json("saved_tracks") or []
    pops = [item["track"]["popularity"] for item in saved
            if item.get("track") and item["track"].get("popularity") is not None]

    if not pops:
        return {}

    return {
        "mean": round(float(np.mean(pops)), 1),
        "std": round(float(np.std(pops)), 1),
        "mainstream_pct": round(sum(1 for p in pops if p > 50) / len(pops), 3),
    }


def generate_fingerprint():
    print(f"\n{BOLD}{CYAN}Generating taste fingerprint...{RESET}\n")

    saved = load_json("saved_tracks") or []
    meta = load_json("pull_meta") or {}

    if not saved:
        print("  No data found. Run 'pull' first.")
        return

    fingerprint = {
        "version": 1,
        "generated": datetime.now(timezone.utc).isoformat(),
        "username": meta.get("user", "unknown"),
        "summary": {
            "total_saved_tracks": len(saved),
        },
        "audio_profile": _compute_audio_profile(),
        "top_genres": _compute_genre_weights(),
        "top_artists": _compute_top_artists(),
        "decade_distribution": _compute_decade_distribution(),
        "popularity_profile": _compute_popularity_profile(),
    }

    with open(FINGERPRINT_FILE, "w") as f:
        json.dump(fingerprint, f, indent=2)

    print(f"  {GREEN}Fingerprint saved to:{RESET} {FINGERPRINT_FILE}")
    print(f"\n  {BOLD}Quick summary:{RESET}")
    print(f"  Tracks: {fingerprint['summary']['total_saved_tracks']}")
    if fingerprint["audio_profile"]:
        ap = fingerprint["audio_profile"]
        print(f"  Energy: {ap.get('energy', {}).get('mean', '?'):.2f} | "
              f"Valence: {ap.get('valence', {}).get('mean', '?'):.2f} | "
              f"Danceability: {ap.get('danceability', {}).get('mean', '?'):.2f}")
    if fingerprint["top_genres"]:
        top3 = ", ".join(g["genre"] for g in fingerprint["top_genres"][:3])
        print(f"  Top genres: {top3}")
    if fingerprint["top_artists"]:
        top3 = ", ".join(a["name"] for a in fingerprint["top_artists"][:3])
        print(f"  Top artists: {top3}")

    print(f"\n  Share {FINGERPRINT_FILE} with a friend and run:")
    print(f"  {CYAN}python3 brain.py match <their_fingerprint.json>{RESET}")


def _gaussian_overlap(m1, s1, m2, s2):
    """Compute approximate overlap coefficient of two Gaussians."""
    from scipy.stats import norm
    # Avoid division by zero
    s1 = max(s1, 0.01)
    s2 = max(s2, 0.01)
    d = abs(m1 - m2)
    s = (s1 ** 2 + s2 ** 2) ** 0.5
    return float(2 * norm.cdf(-d / (2 * s)))


def _cosine_similarity(v1, v2):
    a = np.array(v1)
    b = np.array(v2)
    dot = np.dot(a, b)
    na = np.linalg.norm(a)
    nb = np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(dot / (na * nb))


def match_fingerprints(other_path):
    print(f"\n{BOLD}{MAGENTA}Taste Match{RESET}\n")

    # Load own fingerprint
    try:
        with open(FINGERPRINT_FILE) as f:
            mine = json.load(f)
    except FileNotFoundError:
        print("  Generate your fingerprint first: python3 brain.py fingerprint")
        return

    # Load other fingerprint
    try:
        with open(other_path) as f:
            other = json.load(f)
    except FileNotFoundError:
        print(f"  File not found: {other_path}")
        return

    my_name = mine.get("username", "You")
    their_name = other.get("username", "Them")

    print(f"  Comparing {GREEN}{my_name}{RESET} vs {CYAN}{their_name}{RESET}\n")

    # 1. Audio Profile Similarity (30%)
    audio_score = 0.5  # default if no data
    if mine.get("audio_profile") and other.get("audio_profile"):
        overlaps = []
        for feat in ["danceability", "energy", "valence", "acousticness", "instrumentalness", "tempo"]:
            if feat in mine["audio_profile"] and feat in other["audio_profile"]:
                m1 = mine["audio_profile"][feat]
                m2 = other["audio_profile"][feat]
                # Normalize tempo to 0-1 scale for comparison
                if feat == "tempo":
                    overlap = _gaussian_overlap(m1["mean"] / 200, m1["std"] / 200,
                                                m2["mean"] / 200, m2["std"] / 200)
                else:
                    overlap = _gaussian_overlap(m1["mean"], m1["std"], m2["mean"], m2["std"])
                overlaps.append(overlap)
        if overlaps:
            audio_score = np.mean(overlaps)

    # 2. Genre Overlap (35%)
    genre_score = 0.0
    my_genres = {g["genre"]: g["weight"] for g in mine.get("top_genres", [])}
    their_genres = {g["genre"]: g["weight"] for g in other.get("top_genres", [])}
    all_genres = set(my_genres.keys()) | set(their_genres.keys())
    if all_genres:
        v1 = [my_genres.get(g, 0) for g in sorted(all_genres)]
        v2 = [their_genres.get(g, 0) for g in sorted(all_genres)]
        genre_score = max(0, _cosine_similarity(v1, v2))

    # 3. Artist Overlap (20%)
    my_artists = {a["id"]: a for a in mine.get("top_artists", [])}
    their_artists = {a["id"]: a for a in other.get("top_artists", [])}
    shared_artist_ids = set(my_artists.keys()) & set(their_artists.keys())
    union_size = len(set(my_artists.keys()) | set(their_artists.keys())) or 1
    artist_score = len(shared_artist_ids) / union_size

    # 4. Era Compatibility (15%)
    era_score = 0.5
    my_decades = mine.get("decade_distribution", {})
    their_decades = other.get("decade_distribution", {})
    if my_decades and their_decades:
        all_decades = sorted(set(my_decades.keys()) | set(their_decades.keys()))
        v1 = [my_decades.get(d, 0) for d in all_decades]
        v2 = [their_decades.get(d, 0) for d in all_decades]
        era_score = max(0, _cosine_similarity(v1, v2))

    # Weighted final score
    final = (0.30 * audio_score + 0.35 * genre_score + 0.20 * artist_score + 0.15 * era_score) * 100

    # Display results
    print(f"  {BOLD}{'=' * 40}{RESET}")
    print(f"  {BOLD}  COMPATIBILITY: {_score_color(final)}{final:.0f}%{RESET}")
    print(f"  {BOLD}{'=' * 40}{RESET}\n")

    print(f"  {BOLD}Breakdown:{RESET}")
    print(f"    Audio profile:  {_score_color(audio_score * 100)}{audio_score * 100:.0f}%{RESET}")
    print(f"    Genre overlap:  {_score_color(genre_score * 100)}{genre_score * 100:.0f}%{RESET}")
    print(f"    Shared artists: {_score_color(artist_score * 100)}{artist_score * 100:.0f}%{RESET}")
    print(f"    Era match:      {_score_color(era_score * 100)}{era_score * 100:.0f}%{RESET}")

    # Shared artists
    if shared_artist_ids:
        print(f"\n  {BOLD}Shared artists ({len(shared_artist_ids)}):{RESET}")
        for aid in list(shared_artist_ids)[:10]:
            name = my_artists[aid]["name"]
            print(f"    {GREEN}*{RESET} {name}")

    # Shared genres
    shared_genres = set(my_genres.keys()) & set(their_genres.keys())
    if shared_genres:
        top_shared = sorted(shared_genres, key=lambda g: min(my_genres.get(g, 0), their_genres.get(g, 0)), reverse=True)
        print(f"\n  {BOLD}Shared genres:{RESET}")
        for g in top_shared[:8]:
            print(f"    {CYAN}*{RESET} {g}")

    # Complementary differences
    my_unique = set(my_genres.keys()) - set(their_genres.keys())
    their_unique = set(their_genres.keys()) - set(my_genres.keys())
    if my_unique or their_unique:
        print(f"\n  {BOLD}Complementary differences:{RESET}")
        if my_unique:
            top_mine = sorted(my_unique, key=lambda g: my_genres.get(g, 0), reverse=True)[:5]
            print(f"    {my_name} could share: {', '.join(top_mine)}")
        if their_unique:
            top_theirs = sorted(their_unique, key=lambda g: their_genres.get(g, 0), reverse=True)[:5]
            print(f"    {their_name} could share: {', '.join(top_theirs)}")

    # Vibe summary
    print(f"\n  {BOLD}Summary:{RESET}")
    if final >= 80:
        print(f"  {GREEN}Musical soulmates! You two have remarkably similar taste.{RESET}")
    elif final >= 60:
        print(f"  {GREEN}Strong connection - lots of common ground with room to discover.{RESET}")
    elif final >= 40:
        print(f"  {YELLOW}Decent overlap - enough shared taste to enjoy music together.{RESET}")
    elif final >= 20:
        print(f"  {YELLOW}Different worlds - but that means lots of music to exchange!{RESET}")
    else:
        print(f"  {RED}Polar opposites - one person's noise is another's treasure.{RESET}")


def _score_color(score):
    if score >= 70:
        return GREEN
    elif score >= 40:
        return YELLOW
    else:
        return RED

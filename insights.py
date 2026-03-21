import numpy as np
from collections import Counter, defaultdict
from datetime import datetime

from utils import (
    load_json, format_track, format_track_short, print_bar_chart,
    BOLD, DIM, GREEN, YELLOW, CYAN, MAGENTA, RED, RESET
)


def _get_all_tracks():
    saved = load_json("saved_tracks") or []
    return [item["track"] for item in saved if item.get("track")]


def _get_artist_details():
    return load_json("artist_details") or {}


def section_artists():
    print(f"\n{BOLD}{'=' * 50}")
    print(f"  YOUR ARTISTS")
    print(f"{'=' * 50}{RESET}\n")

    tracks = _get_all_tracks()
    if not tracks:
        print("  No saved tracks found.")
        return

    # Count tracks per artist
    artist_counts = Counter()
    artist_names = {}
    for t in tracks:
        for a in t.get("artists", []):
            artist_counts[a["id"]] += 1
            artist_names[a["id"]] = a["name"]

    total_artists = len(artist_counts)
    total_tracks = len(tracks)

    print(f"  {BOLD}Unique artists:{RESET} {YELLOW}{total_artists:,}{RESET}")
    print(f"  {BOLD}Tracks per artist:{RESET} {total_tracks / total_artists:.1f} avg\n")

    # Top 15 most saved artists
    print(f"  {BOLD}Most saved artists:{RESET}")
    top_15 = artist_counts.most_common(15)
    artist_data = {artist_names[aid]: count for aid, count in top_15}
    print_bar_chart(artist_data, color=CYAN)

    # One-hit wonders (artists with only 1 track)
    one_hit = sum(1 for c in artist_counts.values() if c == 1)
    print(f"\n  {BOLD}One-track artists:{RESET} {one_hit} ({one_hit / total_artists * 100:.0f}% of your artists)")

    # Artist loyalty score (what % of tracks come from your top 10 artists)
    top_10_tracks = sum(c for _, c in artist_counts.most_common(10))
    loyalty = top_10_tracks / total_tracks * 100
    print(f"  {BOLD}Top-10 loyalty:{RESET} {loyalty:.0f}% of your library is from your top 10 artists")
    if loyalty > 40:
        print(f"  {MAGENTA}Deep diver - you go all in on artists you love{RESET}")
    elif loyalty > 25:
        print(f"  {MAGENTA}Balanced explorer - loyal but curious{RESET}")
    else:
        print(f"  {MAGENTA}Wide explorer - you sample broadly across many artists{RESET}")


def section_genres():
    print(f"\n{BOLD}{'=' * 50}")
    print(f"  GENRE DISTRIBUTION")
    print(f"{'=' * 50}{RESET}\n")

    artist_details = _get_artist_details()

    if not artist_details:
        # Fallback: no genre data available from API
        print(f"  {DIM}Spotify API restricted genre data for this app.{RESET}")
        print(f"  {DIM}Genre analysis unavailable - see other sections for insights.{RESET}")
        return

    genre_counts = Counter()
    for aid, artist in artist_details.items():
        for g in artist.get("genres", []):
            genre_counts[g] += 1

    if not genre_counts:
        print(f"  {DIM}No genre data available from Spotify.{RESET}")
        return

    # Micro-genre top 15
    print(f"  {BOLD}Top genres:{RESET}")
    total = sum(genre_counts.values())
    top_micro = genre_counts.most_common(15)
    micro_data = {g: (c / total) * 100 for g, c in top_micro}
    print_bar_chart(micro_data, color=CYAN)


def section_gems():
    print(f"\n{BOLD}{'=' * 50}")
    print(f"  DEEP CUTS & ALBUM DEEP DIVES")
    print(f"{'=' * 50}{RESET}\n")

    tracks = _get_all_tracks()
    saved = load_json("saved_tracks") or []
    if not tracks:
        print("  No saved tracks found.")
        return

    # Find albums where you saved most/all tracks (deep dives)
    album_total_tracks = {}
    album_saved_tracks = Counter()
    album_names = {}
    for t in tracks:
        if "album" in t:
            alb = t["album"]
            album_saved_tracks[alb["id"]] += 1
            album_total_tracks[alb["id"]] = alb.get("total_tracks", 0)
            album_names[alb["id"]] = f"{t['artists'][0]['name']} - {alb['name']}"

    print(f"  {BOLD}Albums you went deep on (most tracks saved):{RESET}")
    deep_albums = sorted(album_saved_tracks.items(), key=lambda x: -x[1])
    for alb_id, saved_count in deep_albums[:10]:
        total = album_total_tracks.get(alb_id, 0)
        if total > 0:
            pct = saved_count / total * 100
            bar = "█" * int(pct / 5)
            print(f"    {album_names[alb_id]}")
            print(f"    {DIM}{saved_count}/{total} tracks ({pct:.0f}%) {GREEN}{bar}{RESET}")
        else:
            print(f"    {album_names[alb_id]}: {saved_count} tracks")

    # Single-track albums (you cherry-picked one song)
    singles = [alb_id for alb_id, c in album_saved_tracks.items()
               if c == 1 and album_total_tracks.get(alb_id, 0) > 5]
    print(f"\n  {BOLD}Cherry-picked singles:{RESET} {len(singles)} albums where you saved just 1 track from 5+")

    # Find tracks from artists you only have one track from (one-offs/discoveries)
    artist_counts = Counter()
    artist_tracks = defaultdict(list)
    for t in tracks:
        for a in t.get("artists", []):
            artist_counts[a["id"]] += 1
            artist_tracks[a["id"]].append(t)

    one_offs = []
    for aid, count in artist_counts.items():
        if count == 1:
            one_offs.extend(artist_tracks[aid])

    import random
    if one_offs:
        print(f"\n  {BOLD}Random one-off discoveries:{RESET}")
        print(f"  {DIM}(Artists you saved exactly 1 track from - {len(one_offs)} total){RESET}")
        sample = random.sample(one_offs, min(10, len(one_offs)))
        for t in sample:
            print(f"    {format_track(t)}")


def section_decades():
    print(f"\n{BOLD}{'=' * 50}")
    print(f"  DECADE BREAKDOWN")
    print(f"{'=' * 50}{RESET}\n")

    tracks = _get_all_tracks()
    if not tracks:
        print("  No saved tracks found.")
        return

    decade_counts = Counter()
    year_counts = Counter()
    for t in tracks:
        if "album" in t and "release_date" in t["album"]:
            year_str = t["album"]["release_date"][:4]
            try:
                year = int(year_str)
                if year < 1900 or year > 2030:
                    continue
                decade = f"{(year // 10) * 10}s"
                decade_counts[decade] += 1
                year_counts[year] += 1
            except ValueError:
                pass

    if not decade_counts:
        print("  No release date data available.")
        return

    total = sum(decade_counts.values())
    sorted_decades = sorted(decade_counts.items())
    decade_data = {d: (c / total) * 100 for d, c in sorted_decades}
    print_bar_chart(decade_data, color=GREEN)

    # Home decade
    home_decade = decade_counts.most_common(1)[0]
    print(f"\n  {BOLD}Your home decade:{RESET} {YELLOW}{home_decade[0]}{RESET} ({home_decade[1]} tracks, {home_decade[1] / total * 100:.0f}%)")

    # Top 5 years
    print(f"\n  {BOLD}Top 5 years:{RESET}")
    for year, count in year_counts.most_common(5):
        print(f"    {year}: {count} tracks")

    # Oldest and newest
    oldest_year = 9999
    oldest_track = None
    newest_year = 0
    newest_track = None
    for t in tracks:
        if "album" in t and "release_date" in t["album"]:
            try:
                year = int(t["album"]["release_date"][:4])
                if year < 1900 or year > 2030:
                    continue
                if year < oldest_year:
                    oldest_year = year
                    oldest_track = t
                if year > newest_year:
                    newest_year = year
                    newest_track = t
            except ValueError:
                pass

    if oldest_track:
        print(f"\n  {BOLD}Oldest track:{RESET} {format_track(oldest_track)}")
    if newest_track:
        print(f"  {BOLD}Newest track:{RESET} {format_track(newest_track)}")

    # Time span
    if oldest_year < 9999 and newest_year > 0:
        print(f"  {BOLD}Library spans:{RESET} {newest_year - oldest_year} years of music")


def section_velocity():
    print(f"\n{BOLD}{'=' * 50}")
    print(f"  LISTENING VELOCITY")
    print(f"{'=' * 50}{RESET}\n")

    short = load_json("top_artists_short_term") or []
    medium = load_json("top_artists_medium_term") or []
    long_term = load_json("top_artists_long_term") or []

    if not short and not long_term:
        print("  Not enough data for velocity analysis.")
        return

    # Build rank maps
    short_ranks = {a["id"]: i for i, a in enumerate(short)}
    long_ranks = {a["id"]: i for i, a in enumerate(long_term)}

    # Rising artists
    risers = []
    for a in short[:20]:
        short_rank = short_ranks.get(a["id"], 99)
        long_rank = long_ranks.get(a["id"], 99)
        if long_rank - short_rank > 10 or (a["id"] not in long_ranks and short_rank < 15):
            risers.append(a)

    # Falling artists
    fallers = []
    for a in long_term[:20]:
        long_rank = long_ranks.get(a["id"], 99)
        short_rank = short_ranks.get(a["id"], 99)
        if short_rank - long_rank > 10 or (a["id"] not in short_ranks and long_rank < 15):
            fallers.append(a)

    if risers:
        print(f"  {BOLD}Rising fast (getting into lately):{RESET}")
        for a in risers[:7]:
            print(f"    {GREEN}+{RESET} {a['name']}")

    if fallers:
        print(f"\n  {BOLD}Cooling off (less than before):{RESET}")
        for a in fallers[:7]:
            print(f"    {RED}-{RESET} {a['name']}")

    if not risers and not fallers:
        print("  Your taste has been pretty consistent across time periods!")

    # Show current top 10 vs all-time top 10
    if short and long_term:
        print(f"\n  {BOLD}Right now (4 weeks) vs All-time:{RESET}")
        print(f"  {'Current':>25s}  |  {'All-time':<25s}")
        print(f"  {'-' * 25}  |  {'-' * 25}")
        max_show = min(10, len(short), len(long_term))
        for i in range(max_show):
            s_name = short[i]["name"][:25] if i < len(short) else ""
            l_name = long_term[i]["name"][:25] if i < len(long_term) else ""
            print(f"  {s_name:>25s}  |  {l_name:<25s}")


def section_facts():
    print(f"\n{BOLD}{'=' * 50}")
    print(f"  FUN FACTS")
    print(f"{'=' * 50}{RESET}\n")

    saved = load_json("saved_tracks") or []
    tracks = _get_all_tracks()

    if not tracks:
        print("  No data available.")
        return

    total = len(tracks)

    # Library size
    print(f"  {BOLD}Library size:{RESET} {YELLOW}{total:,}{RESET} saved tracks\n")

    # Duration extremes
    durations = [(t, t.get("duration_ms", 0)) for t in tracks if t.get("duration_ms")]
    durations.sort(key=lambda x: x[1])

    if durations:
        shortest = durations[0]
        longest = durations[-1]
        avg_duration = np.mean([d for _, d in durations])
        print(f"\n  {BOLD}Shortest track:{RESET} {format_track_short(shortest[0])} ({shortest[1] // 1000}s)")
        print(f"  {BOLD}Longest track:{RESET} {format_track_short(longest[0])} ({longest[1] // 60000}m {(longest[1] % 60000) // 1000}s)")
        print(f"  {BOLD}Average duration:{RESET} {avg_duration / 60000:.1f} minutes")

        total_ms = sum(d for _, d in durations)
        total_hours = total_ms / 3600000
        print(f"\n  {BOLD}Total library duration:{RESET} {total_hours:.0f} hours ({total_hours / 24:.1f} days of non-stop music)")

    # Explicit content
    explicit_count = sum(1 for t in tracks if t.get("explicit"))
    print(f"\n  {BOLD}Explicit tracks:{RESET} {explicit_count} ({explicit_count / total * 100:.0f}%)")

    # Album diversity
    album_counts = Counter()
    album_names = {}
    for t in tracks:
        if "album" in t:
            album_counts[t["album"]["id"]] += 1
            album_names[t["album"]["id"]] = f"{t['artists'][0]['name']} - {t['album']['name']}"

    print(f"\n  {BOLD}Unique albums:{RESET} {len(album_counts):,}")
    print(f"  {BOLD}Most saved albums:{RESET}")
    for alb_id, count in album_counts.most_common(5):
        print(f"    {album_names[alb_id]}: {count} tracks")

    # Artist diversity
    artist_counts = Counter()
    artist_names = {}
    for t in tracks:
        for a in t.get("artists", []):
            artist_counts[a["id"]] += 1
            artist_names[a["id"]] = a["name"]

    print(f"\n  {BOLD}Unique artists:{RESET} {len(artist_counts):,}")

    top_5 = artist_counts.most_common(5)
    print(f"  {BOLD}Most saved artists:{RESET}")
    for aid, count in top_5:
        print(f"    {artist_names[aid]}: {count} tracks")

    # Collaborations (tracks with multiple artists)
    collabs = [t for t in tracks if len(t.get("artists", [])) > 1]
    print(f"\n  {BOLD}Collaborations:{RESET} {len(collabs)} tracks ({len(collabs) / total * 100:.0f}%) feature multiple artists")

    # Save timeline (when were tracks added)
    add_dates = []
    for item in saved:
        if item.get("added_at"):
            try:
                dt = datetime.fromisoformat(item["added_at"].replace("Z", "+00:00"))
                add_dates.append(dt)
            except (ValueError, TypeError):
                pass

    if add_dates:
        add_dates.sort()
        oldest_add = add_dates[0]
        newest_add = add_dates[-1]
        span_days = (newest_add - oldest_add).days

        # Monthly add rate
        month_counts = Counter()
        for dt in add_dates:
            month_counts[dt.strftime("%Y-%m")] += 1

        avg_per_month = total / max(span_days / 30, 1)
        peak_month = month_counts.most_common(1)[0]

        print(f"\n  {BOLD}Library timeline:{RESET}")
        print(f"  First save: {oldest_add.strftime('%b %d, %Y')}")
        print(f"  Latest save: {newest_add.strftime('%b %d, %Y')}")
        print(f"  Avg saves per month: {avg_per_month:.0f}")
        print(f"  Peak month: {peak_month[0]} ({peak_month[1]} tracks)")

        # Recent activity
        recent_months = sorted(month_counts.items())[-6:]
        if recent_months:
            print(f"\n  {BOLD}Recent saving activity:{RESET}")
            month_data = {m: c for m, c in recent_months}
            print_bar_chart(month_data, color=GREEN)


def section_recently_played():
    print(f"\n{BOLD}{'=' * 50}")
    print(f"  RECENT LISTENING")
    print(f"{'=' * 50}{RESET}\n")

    recent = load_json("recently_played") or []
    if not recent:
        print("  No recently played data.")
        return

    # Show recent unique tracks
    seen = set()
    unique = []
    for item in recent:
        t = item["track"]
        if t["id"] not in seen:
            seen.add(t["id"])
            unique.append((item, t))

    print(f"  {BOLD}Last {len(unique)} unique tracks you played:{RESET}")
    for item, t in unique[:15]:
        played_at = item.get("played_at", "")
        if played_at:
            try:
                dt = datetime.fromisoformat(played_at.replace("Z", "+00:00"))
                time_str = dt.strftime("%b %d %H:%M")
            except (ValueError, TypeError):
                time_str = ""
        else:
            time_str = ""
        print(f"    {DIM}{time_str}{RESET}  {format_track_short(t)}")

    # Repeat plays
    play_counts = Counter(item["track"]["id"] for item in recent)
    repeats = [(tid, c) for tid, c in play_counts.items() if c > 1]
    if repeats:
        track_map = {item["track"]["id"]: item["track"] for item in recent}
        repeats.sort(key=lambda x: -x[1])
        print(f"\n  {BOLD}On repeat:{RESET}")
        for tid, count in repeats[:5]:
            print(f"    {format_track_short(track_map[tid])} {DIM}({count}x){RESET}")


def run_insights(section=None):
    sections = {
        "artists": section_artists,
        "genres": section_genres,
        "gems": section_gems,
        "decades": section_decades,
        "velocity": section_velocity,
        "facts": section_facts,
        "recent": section_recently_played,
    }

    print(f"\n{BOLD}{CYAN}spotify-brain insights{RESET}")

    if section:
        if section in sections:
            sections[section]()
        else:
            print(f"Unknown section: {section}. Available: {', '.join(sections.keys())}")
    else:
        for fn in sections.values():
            fn()

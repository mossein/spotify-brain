#!/usr/bin/env python3
"""spotify-brain - Your Personal Music Intelligence Tool"""

import argparse
import json
import sys

from utils import (
    ensure_dirs, save_config, load_config, BOLD, GREEN, CYAN, YELLOW, RED, RESET
)


def cmd_setup(args):
    ensure_dirs()
    existing = load_config()

    print(f"\n{BOLD}spotify-brain setup{RESET}")
    print(f"  You need a Spotify Developer app.")
    print(f"  Create one at: {CYAN}https://developer.spotify.com/dashboard{RESET}")
    print(f"  Set the redirect URI to: {CYAN}http://127.0.0.1:8888/callback{RESET}\n")

    client_id = input("  Client ID: ").strip()
    client_secret = input("  Client Secret: ").strip()

    if not client_id or not client_secret:
        print(f"\n  {RED}Both client_id and client_secret are required.{RESET}")
        sys.exit(1)

    save_config({"client_id": client_id, "client_secret": client_secret})
    print(f"\n  {GREEN}Config saved!{RESET} Now run: python3 brain.py pull")


def cmd_pull(args):
    from pull import pull_all
    pull_all()


def cmd_insights(args):
    from insights import run_insights
    run_insights(section=args.section if hasattr(args, "section") else None)


def cmd_discover(args):
    from discovery import run_discovery
    run_discovery(
        mood=args.mood if hasattr(args, "mood") else None,
        deep_cuts=args.deep_cuts if hasattr(args, "deep_cuts") else False,
        explore_genre=args.explore_genre if hasattr(args, "explore_genre") else None,
    )


def cmd_fingerprint(args):
    from taste import generate_fingerprint
    generate_fingerprint()


def cmd_match(args):
    from taste import match_fingerprints
    match_fingerprints(args.file)


def cmd_export(args):
    from export import export
    export()


def cmd_dump(args):
    from utils import DATA_DIR
    data = {}
    for f in DATA_DIR.glob("*.json"):
        with open(f) as fh:
            data[f.stem] = json.load(fh)
    json.dump(data, sys.stdout, indent=2)
    print()


def main():
    parser = argparse.ArgumentParser(
        description="spotify-brain - Your Personal Music Intelligence Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("setup", help="Configure Spotify API credentials")
    sub.add_parser("pull", help="Fetch your Spotify library data")

    insights_p = sub.add_parser("insights", help="Analyze your music taste")
    insights_p.add_argument("--section", choices=["artists", "genres", "gems", "decades", "velocity", "facts", "recent"],
                            help="Show only a specific section")

    discover_p = sub.add_parser("discover", help="Discover new music")
    discover_p.add_argument("--mood", choices=["energetic", "chill", "sad", "happy", "focus", "workout"],
                            help="Filter by mood")
    discover_p.add_argument("--deep-cuts", action="store_true", help="Find hidden tracks by your top artists")
    discover_p.add_argument("--explore-genre", type=str, help="Explore an adjacent genre")

    sub.add_parser("fingerprint", help="Generate your taste fingerprint")

    match_p = sub.add_parser("match", help="Compare taste with someone else")
    match_p.add_argument("file", help="Path to the other person's fingerprint.json")

    sub.add_parser("export", help="Export library for relationship readings")
    sub.add_parser("dump", help="Dump raw cached data as JSON")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        print(f"\n{BOLD}Quick start:{RESET}")
        print(f"  1. python3 brain.py setup")
        print(f"  2. python3 brain.py pull")
        print(f"  3. python3 brain.py insights")
        sys.exit(0)

    commands = {
        "setup": cmd_setup,
        "pull": cmd_pull,
        "insights": cmd_insights,
        "discover": cmd_discover,
        "fingerprint": cmd_fingerprint,
        "match": cmd_match,
        "export": cmd_export,
        "dump": cmd_dump,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()

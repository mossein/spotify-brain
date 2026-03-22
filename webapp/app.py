#!/usr/bin/env python3
"""spotify-brain web app."""

import hashlib
import json
import os
import secrets
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

import requests
from flask import (Flask, redirect, request, render_template, session,
                   url_for, flash, jsonify)

# Add parent dir to path for engine import
sys.path.insert(0, str(Path(__file__).parent.parent))
from engine import LibraryProfile, RelationshipAnalysis, NarrativeEngine

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", secrets.token_hex(32))

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

SPOTIFY_CLIENT_ID = os.environ.get("SPOTIFY_CLIENT_ID", "")
SPOTIFY_CLIENT_SECRET = os.environ.get("SPOTIFY_CLIENT_SECRET", "")
SPOTIFY_REDIRECT_URI = os.environ.get("SPOTIFY_REDIRECT_URI", "http://127.0.0.1:5000/callback")
SPOTIFY_SCOPES = "user-library-read user-top-read user-read-recently-played"

DB_PATH = Path(__file__).parent / "spotify_brain.db"

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

def get_db():
    db = sqlite3.connect(str(DB_PATH))
    db.row_factory = sqlite3.Row
    return db


def init_db():
    db = get_db()
    db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            display_name TEXT,
            library_data TEXT,
            insights_data TEXT,
            share_code TEXT UNIQUE,
            created_at TEXT,
            updated_at TEXT
        );
        CREATE TABLE IF NOT EXISTS pairings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_a TEXT,
            user_b TEXT,
            reading_data TEXT,
            created_at TEXT,
            FOREIGN KEY (user_a) REFERENCES users(id),
            FOREIGN KEY (user_b) REFERENCES users(id)
        );
    """)
    db.commit()
    db.close()


init_db()

# ---------------------------------------------------------------------------
# Spotify OAuth + API helpers
# ---------------------------------------------------------------------------

def spotify_auth_url():
    params = {
        "client_id": SPOTIFY_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": SPOTIFY_REDIRECT_URI,
        "scope": SPOTIFY_SCOPES,
        "show_dialog": "false",
    }
    return "https://accounts.spotify.com/authorize?" + urlencode(params)


def spotify_get_token(code):
    resp = requests.post("https://accounts.spotify.com/api/token", data={
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": SPOTIFY_REDIRECT_URI,
        "client_id": SPOTIFY_CLIENT_ID,
        "client_secret": SPOTIFY_CLIENT_SECRET,
    })
    return resp.json()


def spotify_api(token, endpoint, params=None):
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(f"https://api.spotify.com/v1/{endpoint}",
                       headers=headers, params=params or {})
    if resp.status_code == 429:
        time.sleep(int(resp.headers.get("Retry-After", 2)))
        return spotify_api(token, endpoint, params)
    return resp.json()


def pull_library(token):
    """Pull full library from Spotify API. Returns export-format dict."""

    # User profile
    me = spotify_api(token, "me")
    user_id = me.get("id", "unknown")
    display_name = me.get("display_name", "unknown")

    # Saved tracks (paginate)
    saved_tracks = []
    offset = 0
    while True:
        result = spotify_api(token, "me/tracks", {"limit": 50, "offset": offset})
        items = result.get("items", [])
        if not items:
            break
        for item in items:
            t = item.get("track", {})
            if not t:
                continue
            saved_tracks.append({
                "artists": ", ".join(a["name"] for a in t.get("artists", [])),
                "name": t.get("name", ""),
                "album": t.get("album", {}).get("name", ""),
                "year": t.get("album", {}).get("release_date", "")[:4],
                "duration": f"{t.get('duration_ms', 0) // 60000}:{(t.get('duration_ms', 0) % 60000) // 1000:02d}",
                "explicit": t.get("explicit", False),
                "added": item.get("added_at", "")[:10],
                "id": t.get("id", ""),
            })
        offset += 50
        if offset >= result.get("total", 0):
            break
        time.sleep(0.05)

    # Reverse to chronological (oldest first)
    saved_tracks.reverse()
    saved_ids = set(t["id"] for t in saved_tracks)

    # Top tracks (3 time ranges)
    top_tracks = {}
    for tr in ["short_term", "medium_term", "long_term"]:
        tracks = []
        for offset in [0]:
            result = spotify_api(token, "me/top/tracks", {"limit": 50, "offset": offset, "time_range": tr})
            for t in result.get("items", []):
                tracks.append({
                    "artists": ", ".join(a["name"] for a in t.get("artists", [])),
                    "name": t.get("name", ""),
                    "album": t.get("album", {}).get("name", ""),
                    "year": t.get("album", {}).get("release_date", "")[:4],
                    "explicit": t.get("explicit", False),
                    "saved": t.get("id", "") in saved_ids,
                    "id": t.get("id", ""),
                })
        top_tracks[tr] = tracks
        time.sleep(0.05)

    # Top artists (3 time ranges)
    top_artists = {}
    for tr in ["short_term", "medium_term", "long_term"]:
        result = spotify_api(token, "me/top/artists", {"limit": 50, "time_range": tr})
        top_artists[tr] = [a.get("name", "") for a in result.get("items", [])]
        time.sleep(0.05)

    # Recently played
    result = spotify_api(token, "me/player/recently-played", {"limit": 50})
    play_history = []
    for item in result.get("items", []):
        t = item.get("track", {})
        play_history.append({
            "played_at": item.get("played_at", "")[:16],
            "artists": ", ".join(a["name"] for a in t.get("artists", [])),
            "name": t.get("name", ""),
            "saved": t.get("id", "") in saved_ids,
        })

    # Stats
    artist_counts = Counter()
    for t in saved_tracks:
        for a in t["artists"].split(", "):
            artist_counts[a.strip()] += 1

    from collections import Counter
    decade_dist = Counter()
    for t in saved_tracks:
        y = t.get("year", "")
        if y and y.isdigit() and 1900 < int(y) < 2030:
            decade_dist[f"{(int(y) // 10) * 10}s"] += 1

    monthly = Counter(t["added"][:7] for t in saved_tracks if t.get("added"))

    export_data = {
        "version": 2,
        "exported": datetime.now(timezone.utc).isoformat(),
        "user": display_name,
        "user_id": user_id,
        "saved_tracks": saved_tracks,
        "top_tracks": top_tracks,
        "top_artists": top_artists,
        "play_history": play_history,
        "stats": {
            "total_saved": len(saved_tracks),
            "unique_artists": len(artist_counts),
            "explicit_pct": round(sum(1 for t in saved_tracks if t.get("explicit")) / max(len(saved_tracks), 1) * 100),
            "top_saved_artists": [{"name": n, "count": c} for n, c in artist_counts.most_common(30)],
            "decade_distribution": dict(sorted(decade_dist.items())),
            "monthly_saves": dict(sorted(monthly.items())),
        },
    }

    return user_id, display_name, export_data


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    user_id = session.get("user_id")
    if user_id:
        return redirect(url_for("profile"))
    return render_template("index.html")


@app.route("/login")
def login():
    if not SPOTIFY_CLIENT_ID or not SPOTIFY_CLIENT_SECRET:
        return "Set SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET environment variables", 500
    return redirect(spotify_auth_url())


@app.route("/callback")
def callback():
    code = request.args.get("code")
    error = request.args.get("error")
    if error:
        return f"Spotify auth error: {error}", 400
    if not code:
        return "No code received", 400

    token_data = spotify_get_token(code)
    access_token = token_data.get("access_token")
    if not access_token:
        return "Failed to get access token", 400

    session["access_token"] = access_token

    # Pull library
    from collections import Counter
    user_id, display_name, library_data = pull_library(access_token)

    # Generate insights
    profile = LibraryProfile(library_data)
    engine = NarrativeEngine()
    insights = engine.generate_single(profile)

    # Generate share code
    share_code = hashlib.sha256(user_id.encode()).hexdigest()[:8]

    # Save to DB
    db = get_db()
    now = datetime.now(timezone.utc).isoformat()
    db.execute("""
        INSERT OR REPLACE INTO users (id, display_name, library_data, insights_data, share_code, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, COALESCE((SELECT created_at FROM users WHERE id = ?), ?), ?)
    """, (user_id, display_name, json.dumps(library_data), json.dumps(insights),
          share_code, user_id, now, now))
    db.commit()
    db.close()

    session["user_id"] = user_id
    session["display_name"] = display_name

    # Check if they came from a pair link
    pair_with = session.pop("pair_with", None)
    if pair_with and pair_with != user_id:
        _create_pairing(user_id, pair_with)
        return redirect(url_for("together", user_a=user_id, user_b=pair_with))

    return redirect(url_for("profile"))


@app.route("/profile")
def profile():
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("index"))

    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if not user:
        return redirect(url_for("index"))

    insights = json.loads(user["insights_data"])
    library = json.loads(user["library_data"])
    share_url = request.host_url.rstrip("/") + url_for("pair", code=user["share_code"])

    # Get pairings
    pairings = db.execute("""
        SELECT p.*,
               ua.display_name as name_a,
               ub.display_name as name_b
        FROM pairings p
        JOIN users ua ON p.user_a = ua.id
        JOIN users ub ON p.user_b = ub.id
        WHERE p.user_a = ? OR p.user_b = ?
        ORDER BY p.created_at DESC
    """, (user_id, user_id)).fetchall()

    db.close()

    return render_template("profile.html",
                          user=user,
                          insights=insights,
                          library=library,
                          share_url=share_url,
                          pairings=pairings)


@app.route("/pair/<code>")
def pair(code):
    db = get_db()
    other_user = db.execute("SELECT * FROM users WHERE share_code = ?", (code,)).fetchone()
    db.close()

    if not other_user:
        return "Invalid share link", 404

    user_id = session.get("user_id")
    if user_id:
        if user_id == other_user["id"]:
            return redirect(url_for("profile"))
        # Both logged in, create pairing
        _create_pairing(user_id, other_user["id"])
        return redirect(url_for("together", user_a=user_id, user_b=other_user["id"]))

    # Not logged in - save who they want to pair with and send to login
    session["pair_with"] = other_user["id"]
    return render_template("pair_landing.html", other_name=other_user["display_name"])


@app.route("/together/<user_a>/<user_b>")
def together(user_a, user_b):
    user_id = session.get("user_id")
    if not user_id or user_id not in (user_a, user_b):
        return redirect(url_for("index"))

    db = get_db()
    ua = db.execute("SELECT * FROM users WHERE id = ?", (user_a,)).fetchone()
    ub = db.execute("SELECT * FROM users WHERE id = ?", (user_b,)).fetchone()

    if not ua or not ub:
        return "One or both users not found", 404

    # Check for existing pairing
    pairing = db.execute("""
        SELECT * FROM pairings
        WHERE (user_a = ? AND user_b = ?) OR (user_a = ? AND user_b = ?)
        ORDER BY created_at DESC LIMIT 1
    """, (user_a, user_b, user_b, user_a)).fetchone()

    if pairing and pairing["reading_data"]:
        reading = json.loads(pairing["reading_data"])
    else:
        # Generate reading
        lib_a = json.loads(ua["library_data"])
        lib_b = json.loads(ub["library_data"])
        profile_a = LibraryProfile(lib_a)
        profile_b = LibraryProfile(lib_b)
        analysis = RelationshipAnalysis(profile_a, profile_b)
        engine = NarrativeEngine()

        reading = {
            "person_a": {"user": profile_a.user, "insights": engine.generate_single(profile_a)},
            "person_b": {"user": profile_b.user, "insights": engine.generate_single(profile_b)},
            "relationship": engine.generate_relationship(analysis),
        }

        # Save to pairing
        if pairing:
            db.execute("UPDATE pairings SET reading_data = ? WHERE id = ?",
                      (json.dumps(reading), pairing["id"]))
        else:
            db.execute("INSERT INTO pairings (user_a, user_b, reading_data, created_at) VALUES (?, ?, ?, ?)",
                      (user_a, user_b, json.dumps(reading), datetime.now(timezone.utc).isoformat()))
        db.commit()

    db.close()

    return render_template("together.html",
                          reading=reading,
                          user_a=ua,
                          user_b=ub)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


def _create_pairing(user_a, user_b):
    db = get_db()
    existing = db.execute("""
        SELECT id FROM pairings
        WHERE (user_a = ? AND user_b = ?) OR (user_a = ? AND user_b = ?)
    """, (user_a, user_b, user_b, user_a)).fetchone()
    if not existing:
        db.execute("INSERT INTO pairings (user_a, user_b, created_at) VALUES (?, ?, ?)",
                  (user_a, user_b, datetime.now(timezone.utc).isoformat()))
        db.commit()
    db.close()


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if not SPOTIFY_CLIENT_ID:
        print("Set environment variables:")
        print("  export SPOTIFY_CLIENT_ID=your_client_id")
        print("  export SPOTIFY_CLIENT_SECRET=your_client_secret")
        print("  export SPOTIFY_REDIRECT_URI=http://127.0.0.1:5000/callback")
        sys.exit(1)
    app.run(debug=True, port=5000)

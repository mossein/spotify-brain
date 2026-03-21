# spotify-brain

Personal music intelligence tool. Pull your Spotify library and get deep, personal music readings powered by Claude.

Not a dashboard. Not a stats page. A tool that reads your library like a diary - finding patterns you didn't know were there, connections between songs saved years apart, and music you need but haven't found yet.

## What it does

- **Pull** your full Spotify library - saved tracks, top artists/tracks across time ranges, listening history
- **Insights** - artist deep dives, decade breakdowns, listening velocity, hidden album gems
- **Discover** - find unsaved tracks from your favorite artists' catalogs, search by genre or mood
- **Taste matching** - generate a fingerprint of your music taste and compare with friends
- **`/reading`** - a Claude Code skill that ingests your entire library and gives you a live, personal music reading. Every reading is different. No templates, no canned analysis.

## Setup

1. Create a Spotify app at [developer.spotify.com/dashboard](https://developer.spotify.com/dashboard)
2. Set the redirect URI to `http://127.0.0.1:8888/callback`
3. Install dependencies and run setup:

```bash
pip install -r requirements.txt
python3 brain.py setup
```

4. Pull your library:

```bash
python3 brain.py pull
```

## Commands

```bash
python3 brain.py insights          # Full analysis of your library
python3 brain.py discover           # Find new music from your top artists
python3 brain.py discover --deep-cuts  # Hidden tracks by artists you love
python3 brain.py discover --explore-genre "shoegaze"
python3 brain.py fingerprint        # Generate taste fingerprint
python3 brain.py match <file>       # Compare with a friend's fingerprint
python3 brain.py dump               # Raw JSON to stdout
```

## The /reading skill

The real point of this project. Open Claude Code in this directory and run:

```
/reading
```

It reads your compiled library and thinks - actually thinks - about what it finds. It looks at what you save vs what you play on repeat, the songs you return to but never claim, the 3am sessions vs the afternoon listening, the gaps where you stopped saving entirely. It finds connections between tracks you saved years apart, reads the emotional arcs in your binge days, and tells you things about your listening that you didn't know.

Before running `/reading`, compile your library:

```bash
python3 compile_library.py
```

Each reading is different. You can also give it a focus:

```
/reading what am I reaching for right now
/reading find me something new to walk to
/reading read my last few sessions
```

## Accumulating play history

Spotify's API only returns your last 50 plays. Each time you run `python3 brain.py pull`, the tool accumulates your listening history into `play_history.json` rather than overwriting it. Pull regularly to build up a richer picture over time.

## Note on Spotify API restrictions

Spotify has restricted several API endpoints (audio features, artist details, recommendations) for apps in development mode. The tool handles this gracefully - insights and discovery work with available data (track metadata, artist rankings, play counts, release dates).

## Data

All data is cached locally at `~/.spotify-brain/`. Nothing is sent anywhere except to the Spotify API to fetch your own library.

# spotify-brain

> Your music library is a diary you didn't know you were writing. This tool reads it.

**spotify-brain** pulls your Spotify library and uses Claude to perform deep, personal music readings. Not stats. Not pie charts. It finds the patterns underneath your listening - what you reach for at 3am, the songs you play on repeat but never save, the connections between tracks saved years apart that reveal something you didn't know about yourself.

## How it works

```
python3 brain.py setup      # Connect your Spotify account
python3 brain.py pull        # Pull your full library
python3 compile_library.py   # Compile for analysis
/reading                     # Get a reading (in Claude Code)
```

The `/reading` command is a [Claude Code](https://claude.ai/claude-code) custom skill. It ingests your entire library - every saved track, every play count, every timestamp - and produces a live, personal reading. No templates. No canned analysis. Every reading finds something different.

## Features

### Library Pull
Fetches your saved tracks, top artists and tracks (short/medium/long term), and recently played. Play history accumulates over time rather than overwriting, building a richer picture with each pull.

### Insights
```bash
python3 brain.py insights              # Full analysis
python3 brain.py insights --section artists   # Artist deep dive
python3 brain.py insights --section decades   # Decade breakdown
python3 brain.py insights --section velocity  # What's rising/falling
python3 brain.py insights --section gems      # Albums you went deep on
python3 brain.py insights --section facts     # Library stats and timeline
python3 brain.py insights --section recent    # Recent listening
```

### Discovery
```bash
python3 brain.py discover                          # Deep cuts from your top artists
python3 brain.py discover --deep-cuts              # Hidden tracks by artists you love
python3 brain.py discover --explore-genre "shoegaze"  # Search-based genre exploration
python3 brain.py discover --mood "chill"           # Mood-based search
```

### Taste Matching
```bash
python3 brain.py fingerprint     # Generate your taste fingerprint
python3 brain.py match <file>    # Compare with someone else's
```

The fingerprint captures your audio profile, top genres, top artists, decade distribution, and popularity profile. Matching uses Gaussian overlap for audio similarity, cosine similarity for genres and eras, and weighted Jaccard for shared artists.

### The /reading Skill

The core of the project. It reads three layers of your data:

1. **The saved library** - what you chose to keep. The curated self.
2. **The play counts** - what your body actually reaches for. More honest than saves.
3. **The unsaved obsessions** - songs in your most-played that you've never saved. The most revealing data in the system.

```
/reading                                    # Go wherever the data takes you
/reading what am I reaching for right now   # Focus on current state
/reading find me something new to walk to   # Music discovery mode
/reading read my last few sessions          # Session analysis
```

## Setup

### Prerequisites

- Python 3.9+
- A [Spotify Developer](https://developer.spotify.com/dashboard) app
- [Claude Code](https://claude.ai/claude-code) (for the `/reading` skill)

### Installation

```bash
git clone https://github.com/mossein/spotify-brain.git
cd spotify-brain
pip install -r requirements.txt
```

### Spotify App Configuration

1. Go to [developer.spotify.com/dashboard](https://developer.spotify.com/dashboard)
2. Create a new app
3. Select **Web API**
4. Add `http://127.0.0.1:8888/callback` as a redirect URI
5. Copy your Client ID and Client Secret

```bash
python3 brain.py setup
# Paste your Client ID and Client Secret when prompted
```

### First Pull

```bash
python3 brain.py pull
```

This opens your browser for Spotify authorization, then fetches your full library. A local server on port 8888 captures the OAuth callback automatically.

## Data & Privacy

All data is stored locally at `~/.spotify-brain/`. Nothing is sent to any third party. The only external calls are to the Spotify API to fetch your own library data.

| File | Contents |
|------|----------|
| `config.json` | Your Spotify app credentials |
| `data/saved_tracks.json` | Full liked songs library |
| `data/top_tracks_*.json` | Most played tracks (3 time ranges) |
| `data/top_artists_*.json` | Most played artists (3 time ranges) |
| `data/play_history.json` | Accumulated listening sessions |
| `data/recently_played.json` | Latest 50 plays |
| `fingerprint.json` | Exportable taste fingerprint |

## API Limitations

Spotify has restricted several endpoints for apps in development mode (audio features, artist details with genres, recommendations, related artists). spotify-brain handles this gracefully and works with available data: track metadata, artist rankings, play counts, release dates, and album information.

## Project Structure

```
spotify-brain/
  brain.py              # CLI entry point
  auth.py               # Spotify OAuth with local callback server
  pull.py               # Library fetching and play history accumulation
  insights.py           # Library analysis engine
  discovery.py          # Music discovery via album browsing and search
  taste.py              # Fingerprint generation and matching
  utils.py              # Shared helpers
  compile_library.py    # Compiles library into dense text for readings
  .claude/
    commands/
      reading.md        # The /reading skill definition
```

## License

MIT

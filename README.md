# spotify-brain

> Your music library is a diary you didn't know you were writing. This tool reads it.

**spotify-brain** pulls your Spotify library and uses Claude to perform deep, personal music readings. Not stats. Not pie charts. It finds the patterns underneath your listening - what you reach for at 3am, the songs you play on repeat but never save, the connections between tracks saved years apart that reveal something you didn't know about yourself.

## Example: what a /reading looks like

This is real output from a reading of a 1,476-track library spanning 10 years:

> Your library has almost no anger in it. Fourteen hundred songs across ten years of a young life and there's almost zero rage. Melancholy, euphoria, longing, tenderness, swagger, drive - but when you're in pain, you don't reach for something that screams. You reach for something that glows. That's not a preference. That's a worldview.
>
> Your entire library is tuned to a specific quality of light. Not sound - light. The golden hour. That twenty minutes where day becomes night and everything goes warm and soft and slightly unreal and you can't tell if you're remembering something or living it. Dvorak's Serenade has that light. So does "Walking On A Dream." So does "Mango Bay." So does Fairuz's "Wahdon." So does "Party Rock Anthem" played at 3am when the irony melts away and it just becomes pure kinetic joy. The question you're always asking: *does this glow?*
>
> That's why genre is meaningless to you and always has been. Genre describes the vessel. You're only interested in the light inside the vessel.

It also reads the gap between what you **save** and what you **actually play**:

> The unsaved songs are the most important thing in your data. Not the 1,476 you kept. The ones you play on repeat and refuse to claim. "Don't You Forget About Me." "Come Undone." "It's My Life." These are songs you need but won't integrate into the self-portrait. Your saved library is a statement: *this is who I am.* These unsaved obsessions are the question underneath the statement: *but is it?*

And it finds patterns in your listening sessions:

> The circuit you ran twice tonight - Seal into Grizzly Bear into Newman into ZHU/Tame Impala into Empire of the Sun - that's not a playlist. That's an emotional breath. It goes: raw vulnerability, then layered tension that builds without resolving, then pure suspension where time stops, then dark forward motion, then the euphoric lift where you break the surface. And you needed two breaths.

It can also find you music. Not based on algorithms - based on understanding what you're actually looking for:

> **Floating Points, Pharoah Sanders & The London Symphony Orchestra - "Promises."** The whole thing. 46 minutes. One continuous piece. It's electronic, it's jazz, it's classical, it's spiritual. This might be the single most important piece of music you haven't heard. It is the center of your library - the thing everything you've ever saved has been pointing toward.
>
> **Midori Takada - "Through The Looking Glass."** Japanese. 1983. Percussion and marimba. Not ambient - it walks. It has the same hypnotic forward pull as Underworld's "Dark and Long" but made with wood and skin instead of circuits.
>
> **Tinariwen - "Tassili."** Tuareg guitar music from the Sahara desert. Psychedelic like Tame Impala but from a place where the psychedelia comes from endless horizon and heat instead of a studio. Music made by people who walk for a living.

Full example readings: [reading excerpt](examples/reading-excerpt.md) | [discovery mode](examples/reading-discovery.md)

## How it works

```
python3 brain.py setup      # Connect your Spotify account
python3 brain.py pull        # Pull your full library
python3 compile_library.py   # Compile for analysis
/reading                     # Get a reading (in Claude Code)
```

The `/reading` command is a [Claude Code](https://claude.ai/claude-code) custom skill. It ingests your entire library - every saved track, every play count, every timestamp - and produces a live, personal reading. No templates. No canned analysis. Every reading finds something different.

## Features

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

### First Reading

```bash
python3 compile_library.py    # Compile library for Claude
# Then in Claude Code:
/reading
```

## Data & Privacy

All data is stored locally at `~/.spotify-brain/`. Nothing is sent to any third party. The only external calls are to the Spotify API to fetch your own library data.

| File | Contents |
|------|----------|
| `config.json` | Your Spotify app credentials |
| `data/saved_tracks.json` | Full liked songs library |
| `data/top_tracks_*.json` | Most played tracks (3 time ranges) |
| `data/top_artists_*.json` | Most played artists (3 time ranges) |
| `data/play_history.json` | Accumulated listening sessions |
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
  examples/             # Example reading outputs
  .claude/
    commands/
      reading.md        # The /reading skill definition
```

## License

MIT

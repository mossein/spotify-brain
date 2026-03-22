#!/usr/bin/env python3
"""
The insight engine. No LLM. Pure computation + smart narrative generation.

Takes one or two library exports and produces deep, personal, natural-language
insights by computing dozens of metrics and routing them through a narrative
system that selects, combines, and phrases findings based on what's actually
interesting in the data.
"""

import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timedelta


# ---------------------------------------------------------------------------
# Data loading helpers
# ---------------------------------------------------------------------------

def load_export(path):
    with open(path) as f:
        return json.load(f)


def _artists_lower(track):
    return track.get("artists", "").lower()


def _artist_list(track):
    return [a.strip() for a in track.get("artists", "").split(",")]


# ---------------------------------------------------------------------------
# Single-library analysis
# ---------------------------------------------------------------------------

class LibraryProfile:
    """Compute a deep profile of a single library."""

    def __init__(self, data):
        self.data = data
        self.user = data.get("user", "someone")
        self.saved = data.get("saved_tracks", [])
        self.top_short = data.get("top_tracks", {}).get("short_term", [])
        self.top_medium = data.get("top_tracks", {}).get("medium_term", [])
        self.top_long = data.get("top_tracks", {}).get("long_term", [])
        self.artists_short = data.get("top_artists", {}).get("short_term", [])
        self.artists_medium = data.get("top_artists", {}).get("medium_term", [])
        self.artists_long = data.get("top_artists", {}).get("long_term", [])
        self.history = data.get("play_history", [])
        self.stats = data.get("stats", {})

        self._compute()

    def _compute(self):
        self.total = len(self.saved)
        self._compute_artist_profile()
        self._compute_temporal_profile()
        self._compute_nostalgia_profile()
        self._compute_unsaved_obsessions()
        self._compute_session_patterns()
        self._compute_diversity_metrics()
        self._compute_emotional_signatures()

    def _compute_artist_profile(self):
        """Artist frequency, loyalty, diversity."""
        self.artist_counts = Counter()
        for t in self.saved:
            for a in _artist_list(t):
                self.artist_counts[a] += 1

        self.unique_artists = len(self.artist_counts)
        self.one_track_artists = sum(1 for c in self.artist_counts.values() if c == 1)
        self.one_track_pct = self.one_track_artists / max(self.unique_artists, 1) * 100

        top10_tracks = sum(c for _, c in self.artist_counts.most_common(10))
        self.top10_loyalty = top10_tracks / max(self.total, 1) * 100

        # Artist sets for comparison
        self.artist_set = set(self.artist_counts.keys())
        self.top_artist_set_short = set(self.artists_short)
        self.top_artist_set_long = set(self.artists_long)

    def _compute_temporal_profile(self):
        """When they save, gaps, binges."""
        self.save_dates = []
        self.monthly_saves = Counter()
        self.yearly_saves = Counter()
        self.dow_saves = Counter()

        for t in self.saved:
            added = t.get("added", "")
            if added:
                try:
                    dt = datetime.strptime(added, "%Y-%m-%d")
                    self.save_dates.append(dt)
                    self.monthly_saves[added[:7]] += 1
                    self.yearly_saves[added[:4]] += 1
                    self.dow_saves[dt.strftime("%A")] += 1
                except ValueError:
                    pass

        self.save_dates.sort()

        # Gaps
        self.gaps = []
        for i in range(1, len(self.save_dates)):
            gap = (self.save_dates[i] - self.save_dates[i - 1]).days
            if gap > 20:
                self.gaps.append({
                    "days": gap,
                    "start": self.save_dates[i - 1].strftime("%Y-%m-%d"),
                    "end": self.save_dates[i].strftime("%Y-%m-%d"),
                })
        self.gaps.sort(key=lambda x: -x["days"])
        self.longest_gap = self.gaps[0]["days"] if self.gaps else 0

        # Binges (most saves in a single day)
        day_counts = Counter(dt.strftime("%Y-%m-%d") for dt in self.save_dates)
        self.binge_days = day_counts.most_common(5)
        self.biggest_binge = self.binge_days[0][1] if self.binge_days else 0

        # First and last save
        if self.save_dates:
            self.first_save = self.save_dates[0]
            self.last_save = self.save_dates[-1]
            self.library_span_days = (self.last_save - self.first_save).days
        else:
            self.first_save = self.last_save = None
            self.library_span_days = 0

        # Quietest year
        if self.yearly_saves:
            self.quietest_year = min(self.yearly_saves.items(), key=lambda x: x[1])
            self.busiest_year = max(self.yearly_saves.items(), key=lambda x: x[1])

    def _compute_nostalgia_profile(self):
        """How far back they reach over time."""
        self.yearly_nostalgia = {}
        yearly_gaps = defaultdict(list)

        for t in self.saved:
            added = t.get("added", "")
            year_str = t.get("year", "")
            if added and year_str and year_str.isdigit():
                save_year = int(added[:4])
                release_year = int(year_str)
                if 1900 < release_year < 2030:
                    yearly_gaps[save_year].append(save_year - release_year)

        for year, gaps in sorted(yearly_gaps.items()):
            self.yearly_nostalgia[year] = {
                "mean": sum(gaps) / len(gaps),
                "max": max(gaps),
            }

        # Overall nostalgia trajectory (is it increasing?)
        if len(self.yearly_nostalgia) >= 3:
            years = sorted(self.yearly_nostalgia.keys())
            first_third = years[:len(years) // 3]
            last_third = years[-len(years) // 3:]
            early_avg = sum(self.yearly_nostalgia[y]["mean"] for y in first_third) / len(first_third)
            late_avg = sum(self.yearly_nostalgia[y]["mean"] for y in last_third) / len(last_third)
            self.nostalgia_trend = late_avg - early_avg  # positive = reaching further back
        else:
            self.nostalgia_trend = 0

        # Decade distribution
        self.decade_dist = Counter()
        for t in self.saved:
            year_str = t.get("year", "")
            if year_str and year_str.isdigit():
                y = int(year_str)
                if 1900 < y < 2030:
                    self.decade_dist[f"{(y // 10) * 10}s"] += 1

        total_decades = sum(self.decade_dist.values()) or 1
        self.decade_pct = {d: c / total_decades * 100 for d, c in self.decade_dist.items()}
        self.home_decade = self.decade_dist.most_common(1)[0][0] if self.decade_dist else "unknown"

    def _compute_unsaved_obsessions(self):
        """Songs in top played that aren't saved."""
        self.unsaved_short = [t for t in self.top_short if not t.get("saved", True)]
        self.unsaved_medium = [t for t in self.top_medium if not t.get("saved", True)]
        self.unsaved_long = [t for t in self.top_long if not t.get("saved", True)]

        self.unsaved_pct = len(self.unsaved_long) / max(len(self.top_long), 1) * 100

    def _compute_session_patterns(self):
        """Analyze play history for session shapes."""
        if not self.history:
            self.sessions = []
            self.avg_session_length = 0
            self.late_night_pct = 0
            return

        # Group into sessions (gap > 30 min = new session)
        self.sessions = []
        current_session = [self.history[0]]

        for i in range(1, len(self.history)):
            try:
                prev_time = datetime.fromisoformat(self.history[i - 1]["played_at"].replace("Z", "+00:00"))
                curr_time = datetime.fromisoformat(self.history[i]["played_at"].replace("Z", "+00:00"))
                gap = (curr_time - prev_time).total_seconds() / 60
                if gap > 30:
                    self.sessions.append(current_session)
                    current_session = [self.history[i]]
                else:
                    current_session.append(self.history[i])
            except (ValueError, TypeError):
                current_session.append(self.history[i])

        if current_session:
            self.sessions.append(current_session)

        self.avg_session_length = sum(len(s) for s in self.sessions) / max(len(self.sessions), 1)

        # Late night listening
        late_count = 0
        total_plays = 0
        for play in self.history:
            try:
                hour = int(play["played_at"][11:13])
                total_plays += 1
                if 0 <= hour < 6:
                    late_count += 1
            except (ValueError, IndexError):
                pass
        self.late_night_pct = late_count / max(total_plays, 1) * 100

    def _compute_diversity_metrics(self):
        """How diverse is the listening?"""
        # Explicit content
        self.explicit_pct = sum(1 for t in self.saved if t.get("explicit")) / max(self.total, 1) * 100

        # Collaboration rate
        self.collab_pct = sum(1 for t in self.saved if "," in t.get("artists", "")) / max(self.total, 1) * 100

        # Duration stats
        durations = []
        for t in self.saved:
            dur_str = t.get("duration", "")
            if ":" in dur_str:
                parts = dur_str.split(":")
                try:
                    durations.append(int(parts[0]) * 60 + int(parts[1]))
                except ValueError:
                    pass

        if durations:
            self.avg_duration_sec = sum(durations) / len(durations)
            self.total_hours = sum(durations) / 3600
        else:
            self.avg_duration_sec = 0
            self.total_hours = 0

        # Rising artists (in short term but not long term)
        self.rising_artists = [a for a in self.artists_short[:20]
                               if a not in set(self.artists_long)]
        self.falling_artists = [a for a in self.artists_long[:20]
                                if a not in set(self.artists_short)]

    def _compute_emotional_signatures(self):
        """Derive emotional signatures from available data patterns."""
        # Stillness index: ratio of long tracks (>6min) - suggests tolerance for slow burns
        long_tracks = sum(1 for t in self.saved
                         if ":" in t.get("duration", "") and int(t["duration"].split(":")[0]) >= 6)
        self.long_track_pct = long_tracks / max(self.total, 1) * 100

        # Anger index: explicit + certain keywords in track names
        anger_words = ["fuck", "kill", "hate", "rage", "scream", "destroy", "war", "fight", "death"]
        anger_count = sum(1 for t in self.saved
                         if any(w in t.get("name", "").lower() for w in anger_words))
        self.anger_index = anger_count / max(self.total, 1) * 100

        # Nostalgia index: average years looking back
        if self.yearly_nostalgia:
            latest = max(self.yearly_nostalgia.keys())
            self.current_nostalgia = self.yearly_nostalgia[latest]["mean"]
        else:
            self.current_nostalgia = 0

        # All-time top dominated by recent saves?
        recent_in_alltime = 0
        one_year_ago = datetime.now() - timedelta(days=365)
        for t in self.top_long:
            # Check if this track was saved recently
            for s in self.saved:
                if s.get("name") == t.get("name") and s.get("artists") == t.get("artists"):
                    added = s.get("added", "")
                    if added:
                        try:
                            if datetime.strptime(added, "%Y-%m-%d") > one_year_ago:
                                recent_in_alltime += 1
                        except ValueError:
                            pass
                    break

        self.alltime_recency = recent_in_alltime / max(len(self.top_long), 1) * 100


# ---------------------------------------------------------------------------
# Relationship analysis
# ---------------------------------------------------------------------------

class RelationshipAnalysis:
    """Compare two library profiles and generate insights."""

    def __init__(self, profile_a, profile_b):
        self.a = profile_a
        self.b = profile_b
        self._compute()

    def _compute(self):
        self._compute_artist_overlap()
        self._compute_temporal_alignment()
        self._compute_emotional_alignment()
        self._compute_complementary_gaps()
        self._compute_unsaved_comparison()
        self._compute_trajectory_comparison()

    def _compute_artist_overlap(self):
        """How much do their libraries overlap?"""
        # Saved library overlap
        shared = self.a.artist_set & self.b.artist_set
        union = self.a.artist_set | self.b.artist_set
        self.shared_artists = shared
        self.artist_jaccard = len(shared) / max(len(union), 1)

        # Rank the shared artists by combined importance
        self.shared_ranked = []
        for artist in shared:
            a_count = self.a.artist_counts.get(artist, 0)
            b_count = self.b.artist_counts.get(artist, 0)
            self.shared_ranked.append({
                "name": artist,
                "a_count": a_count,
                "b_count": b_count,
                "combined": a_count + b_count,
            })
        self.shared_ranked.sort(key=lambda x: -x["combined"])

        # Top artist overlap (current listening)
        shared_current = self.a.top_artist_set_short & self.b.top_artist_set_short
        self.shared_current_artists = shared_current
        self.current_overlap_pct = len(shared_current) / max(
            min(len(self.a.artists_short), len(self.b.artists_short)), 1) * 100

        # Same artist, different rank (interesting divergences)
        self.rank_divergences = []
        a_ranks = {a: i for i, a in enumerate(self.a.artists_long)}
        b_ranks = {a: i for i, a in enumerate(self.b.artists_long)}
        for artist in shared:
            if artist in a_ranks and artist in b_ranks:
                diff = abs(a_ranks[artist] - b_ranks[artist])
                if diff > 15:
                    self.rank_divergences.append({
                        "name": artist,
                        "a_rank": a_ranks[artist] + 1,
                        "b_rank": b_ranks[artist] + 1,
                        "diff": diff,
                    })
        self.rank_divergences.sort(key=lambda x: -x["diff"])

    def _compute_temporal_alignment(self):
        """Do they listen at the same times? Same patterns?"""
        # Library age comparison
        self.a_span_years = self.a.library_span_days / 365
        self.b_span_years = self.b.library_span_days / 365

        # Late night alignment
        self.both_night_owls = self.a.late_night_pct > 20 and self.b.late_night_pct > 20
        self.night_diff = abs(self.a.late_night_pct - self.b.late_night_pct)

        # Binge pattern similarity
        self.a_biggest_binge = self.a.biggest_binge
        self.b_biggest_binge = self.b.biggest_binge

    def _compute_emotional_alignment(self):
        """Emotional signature comparison."""
        # Anger alignment
        self.both_low_anger = self.a.anger_index < 2 and self.b.anger_index < 2
        self.anger_diff = abs(self.a.anger_index - self.b.anger_index)

        # Nostalgia alignment
        self.nostalgia_diff = abs(self.a.current_nostalgia - self.b.current_nostalgia)
        self.both_nostalgic = self.a.current_nostalgia > 8 and self.b.current_nostalgia > 8
        self.nostalgia_trend_same = (self.a.nostalgia_trend > 0) == (self.b.nostalgia_trend > 0)

        # Explicit content alignment
        self.explicit_diff = abs(self.a.explicit_pct - self.b.explicit_pct)

        # Duration preference alignment
        self.duration_diff = abs(self.a.avg_duration_sec - self.b.avg_duration_sec)

        # Loyalty style alignment
        self.loyalty_diff = abs(self.a.top10_loyalty - self.b.top10_loyalty)
        self.both_explorers = self.a.one_track_pct > 70 and self.b.one_track_pct > 70
        self.both_loyalists = self.a.top10_loyalty > 30 and self.b.top10_loyalty > 30

        # Acceleration alignment (all-time dominated by recent)
        self.both_accelerating = self.a.alltime_recency > 50 and self.b.alltime_recency > 50

        # Home decade alignment
        self.same_home_decade = self.a.home_decade == self.b.home_decade

    def _compute_complementary_gaps(self):
        """What does one have that the other doesn't?"""
        self.a_unique_artists = self.a.artist_set - self.b.artist_set
        self.b_unique_artists = self.b.artist_set - self.a.artist_set

        # Top unique artists (most saved that the other doesn't have)
        self.a_gifts = []
        for artist, count in self.a.artist_counts.most_common():
            if artist in self.a_unique_artists:
                self.a_gifts.append({"name": artist, "count": count})
                if len(self.a_gifts) >= 10:
                    break

        self.b_gifts = []
        for artist, count in self.b.artist_counts.most_common():
            if artist in self.b_unique_artists:
                self.b_gifts.append({"name": artist, "count": count})
                if len(self.b_gifts) >= 10:
                    break

        # Decade gaps
        self.a_decades = set(d for d, p in self.a.decade_pct.items() if p > 3)
        self.b_decades = set(d for d, p in self.b.decade_pct.items() if p > 3)
        self.a_unique_decades = self.a_decades - self.b_decades
        self.b_unique_decades = self.b_decades - self.a_decades

    def _compute_unsaved_comparison(self):
        """Compare shadow selves."""
        a_unsaved_artists = set()
        for t in self.a.unsaved_long:
            for a in _artist_list(t):
                a_unsaved_artists.add(a)

        b_unsaved_artists = set()
        for t in self.b.unsaved_long:
            for a in _artist_list(t):
                b_unsaved_artists.add(a)

        self.shared_unsaved_artists = a_unsaved_artists & b_unsaved_artists
        self.a_unsaved_in_b_saved = a_unsaved_artists & self.b.artist_set
        self.b_unsaved_in_a_saved = b_unsaved_artists & self.a.artist_set

    def _compute_trajectory_comparison(self):
        """Are they converging or diverging?"""
        # Rising artists overlap
        a_rising = set(self.a.rising_artists)
        b_rising = set(self.b.rising_artists)
        self.shared_rising = a_rising & b_rising
        self.converging = len(self.shared_rising) > 2


# ---------------------------------------------------------------------------
# Narrative engine
# ---------------------------------------------------------------------------

class NarrativeEngine:
    """Turn computed metrics into natural language insights."""

    def generate_single(self, profile):
        """Generate insights for a single library."""
        insights = []

        # Identity
        insights.append(self._identity_insight(profile))

        # Emotional signature
        insights.append(self._emotional_insight(profile))

        # Temporal patterns
        insights.append(self._temporal_insight(profile))

        # Nostalgia
        insights.append(self._nostalgia_insight(profile))

        # Unsaved obsessions
        insights.append(self._unsaved_insight(profile))

        # Evolution
        insights.append(self._evolution_insight(profile))

        return [i for i in insights if i]

    def generate_relationship(self, analysis):
        """Generate insights for a relationship between two libraries."""
        a = analysis.a
        b = analysis.b
        insights = []

        # The connection
        insights.append(self._connection_insight(analysis))

        # The shared ground
        insights.append(self._shared_ground_insight(analysis))

        # The emotional alignment
        insights.append(self._emotional_alignment_insight(analysis))

        # The complementary gaps
        insights.append(self._complementary_insight(analysis))

        # The shadow selves
        insights.append(self._shadow_comparison_insight(analysis))

        # The dynamic
        insights.append(self._dynamic_insight(analysis))

        # The trajectory
        insights.append(self._trajectory_insight(analysis))

        return [i for i in insights if i]

    # --- Single library narrative blocks ---

    def _identity_insight(self, p):
        if p.one_track_pct > 75:
            style = "a wide explorer"
            desc = (f"{p.user}'s library spans {p.unique_artists:,} artists, "
                    f"and {p.one_track_pct:.0f}% of them appear only once. "
                    f"This is someone who samples broadly, always moving, rarely going back. "
                    f"The library isn't a collection of favorites - it's a trail of everywhere they've been.")
        elif p.top10_loyalty > 35:
            style = "a deep diver"
            desc = (f"{p.user} goes all in. {p.top10_loyalty:.0f}% of the entire library comes from just 10 artists. "
                    f"When {p.user} finds something, they don't sample - they excavate.")
        else:
            style = "a balanced explorer"
            desc = (f"{p.user} balances loyalty and curiosity. "
                    f"{p.unique_artists:,} artists across {p.total:,} tracks, "
                    f"deep on favorites but always discovering.")

        return {"type": "identity", "title": f"{p.user} is {style}", "body": desc}

    def _emotional_insight(self, p):
        parts = []

        if p.anger_index < 1.5:
            parts.append(
                f"This library has almost no anger in it. "
                f"{p.total:,} tracks and barely any rage. When {p.user} is in pain, "
                f"they don't reach for something that screams - they reach for something that glows. "
                f"That's not a preference. That's a worldview."
            )

        if p.explicit_pct < 12:
            parts.append(f"Only {p.explicit_pct:.0f}% explicit content - a relatively clean library.")
        elif p.explicit_pct > 25:
            parts.append(f"{p.explicit_pct:.0f}% explicit - {p.user} doesn't sanitize their listening.")

        if p.collab_pct > 35:
            parts.append(
                f"{p.collab_pct:.0f}% of the library features multiple artists. "
                f"{p.user} is drawn to collision - what happens when different voices meet."
            )

        if p.long_track_pct > 10:
            parts.append(
                f"{p.long_track_pct:.0f}% of tracks run over 6 minutes. "
                f"{p.user} has patience for the slow burn - music that takes its time arriving."
            )

        if not parts:
            return None

        return {"type": "emotional", "title": "Emotional signature", "body": " ".join(parts)}

    def _temporal_insight(self, p):
        parts = []

        if p.library_span_days > 0:
            years = p.library_span_days / 365
            parts.append(
                f"{p.total:,} tracks saved over {years:.1f} years "
                f"(since {p.first_save.strftime('%B %Y')})."
            )

        if p.longest_gap > 60:
            gap = p.gaps[0]
            parts.append(
                f"The longest silence: {gap['days']} days between "
                f"{gap['start']} and {gap['end']}. "
                f"Something happened. The music stopped, then it came back."
            )

        if hasattr(p, 'quietest_year') and hasattr(p, 'busiest_year'):
            if p.quietest_year[1] < p.busiest_year[1] * 0.25:
                parts.append(
                    f"The quietest year was {p.quietest_year[0]} with only {p.quietest_year[1]} tracks. "
                    f"Compare that to {p.busiest_year[0]} with {p.busiest_year[1]}. "
                    f"That gap isn't just less listening - it's a chapter boundary."
                )

        if p.biggest_binge > 10:
            day, count = p.binge_days[0]
            parts.append(
                f"Biggest single-day binge: {count} tracks on {day}. "
                f"That's not casual browsing - that's a 3am rabbit hole."
            )

        if not parts:
            return None

        return {"type": "temporal", "title": "The timeline", "body": " ".join(parts)}

    def _nostalgia_insight(self, p):
        if p.nostalgia_trend > 5:
            return {
                "type": "nostalgia",
                "title": "The backward reach",
                "body": (
                    f"{p.user} reaches further into the past every year. "
                    f"Currently averaging {p.current_nostalgia:.0f} years of lookback per track. "
                    f"The nostalgia trajectory has been climbing steadily - "
                    f"early saves were mostly current music, now the library is pulling from deeper wells. "
                    f"This isn't regression. It's excavation. "
                    f"{p.user} is tracing every thread back to its source."
                ),
            }
        elif p.current_nostalgia > 10:
            return {
                "type": "nostalgia",
                "title": "The archivist",
                "body": (
                    f"{p.user} listens {p.current_nostalgia:.0f} years behind the present on average. "
                    f"Home decade: {p.home_decade}. "
                    f"This is someone who trusts that the good stuff has already been made "
                    f"and the job is to find it."
                ),
            }
        return None

    def _unsaved_insight(self, p):
        if not p.unsaved_long:
            return None

        unsaved_names = [f"{t['artists']} - {t['name']}" for t in p.unsaved_long[:7]]

        return {
            "type": "unsaved",
            "title": "The unsaved obsessions",
            "body": (
                f"{p.user} has {len(p.unsaved_long)} songs in their all-time most played "
                f"that they've never saved. "
                f"These are the songs the body reaches for but the mind won't claim: "
                f"{', '.join(unsaved_names)}. "
                f"The saved library is a statement: this is who I am. "
                f"The unsaved plays are the question underneath: but is it?"
            ),
        }

    def _evolution_insight(self, p):
        parts = []

        if p.rising_artists:
            rising = ", ".join(p.rising_artists[:5])
            parts.append(f"Currently rising: {rising}.")

        if p.falling_artists:
            falling = ", ".join(p.falling_artists[:5])
            parts.append(f"Cooling off: {falling}.")

        if p.alltime_recency > 60:
            parts.append(
                f"{p.alltime_recency:.0f}% of {p.user}'s all-time most played tracks were saved "
                f"in the last year. The music is more alive right now than it has ever been. "
                f"This isn't someone settling into a lane - this is someone accelerating."
            )

        if not parts:
            return None

        return {"type": "evolution", "title": "Where it's heading", "body": " ".join(parts)}

    # --- Relationship narrative blocks ---

    def _connection_insight(self, r):
        overlap = r.artist_jaccard * 100
        shared_count = len(r.shared_artists)

        if overlap > 30:
            vibe = "deeply intertwined"
            desc = f"musical siblings - {shared_count} shared artists, a {overlap:.0f}% overlap"
        elif overlap > 15:
            vibe = "significantly connected"
            desc = f"{shared_count} artists in common, enough shared ground to build on"
        elif overlap > 5:
            vibe = "complementary"
            desc = f"only {shared_count} shared artists, but that's where it gets interesting"
        else:
            vibe = "from different planets"
            desc = f"just {shared_count} artists in common - two completely different musical worlds"

        return {
            "type": "connection",
            "title": f"{r.a.user} and {r.b.user}: {vibe}",
            "body": (
                f"These two libraries are {vibe}. {desc}. "
                f"{r.a.user} has {r.a.total:,} tracks across {r.a.unique_artists:,} artists. "
                f"{r.b.user} has {r.b.total:,} tracks across {r.b.unique_artists:,} artists."
            ),
        }

    def _shared_ground_insight(self, r):
        if not r.shared_ranked:
            return {"type": "shared", "title": "No common ground",
                    "body": "Almost nothing shared. These two exist in parallel musical universes."}

        top_shared = r.shared_ranked[:8]
        names = [s["name"] for s in top_shared]

        parts = [f"The shared ground: {', '.join(names)}."]

        # Interesting rank divergences
        if r.rank_divergences:
            div = r.rank_divergences[0]
            parts.append(
                f"But shared doesn't mean same. {div['name']} is #{div['a_rank']} for {r.a.user} "
                f"and #{div['b_rank']} for {r.b.user}. "
                f"Same artist, different weight. They hear the same music but it means different things."
            )

        if r.shared_current_artists:
            current = ", ".join(list(r.shared_current_artists)[:5])
            parts.append(f"Right now they're both listening to: {current}.")

        return {"type": "shared", "title": "Common ground", "body": " ".join(parts)}

    def _emotional_alignment_insight(self, r):
        alignments = []
        tensions = []

        if r.both_low_anger:
            alignments.append("Neither library has much anger in it - both process through beauty, not confrontation.")

        if r.both_explorers:
            alignments.append("Both are wide explorers - high one-track artist ratios, always moving to the next thing.")
        elif r.both_loyalists:
            alignments.append("Both are deep divers - they go all in on artists they love.")
        elif r.loyalty_diff > 20:
            tensions.append(
                f"{r.a.user} is {'a deep diver' if r.a.top10_loyalty > r.b.top10_loyalty else 'an explorer'} "
                f"while {r.b.user} is {'a deep diver' if r.b.top10_loyalty > r.a.top10_loyalty else 'an explorer'}. "
                f"One goes deep, the other goes wide. That's complementary."
            )

        if r.same_home_decade:
            alignments.append(f"Same home decade: {r.a.home_decade}. They grew up in the same musical era.")
        else:
            tensions.append(
                f"Different home decades - {r.a.user} lives in the {r.a.home_decade}, "
                f"{r.b.user} in the {r.b.home_decade}. They carry different eras inside them."
            )

        if r.both_nostalgic:
            alignments.append("Both reach deep into the past - fellow archivists.")
        elif r.nostalgia_diff > 8:
            who_past = r.a.user if r.a.current_nostalgia > r.b.current_nostalgia else r.b.user
            who_present = r.b.user if who_past == r.a.user else r.a.user
            tensions.append(
                f"{who_past} listens {max(r.a.current_nostalgia, r.b.current_nostalgia):.0f} years behind the present. "
                f"{who_present} stays closer to now. One is an archaeologist, the other is a reporter."
            )

        if r.explicit_diff > 15:
            who_explicit = r.a.user if r.a.explicit_pct > r.b.explicit_pct else r.b.user
            tensions.append(f"{who_explicit} runs rawer - significantly more explicit content.")

        if r.both_accelerating:
            alignments.append(
                "Both are musically accelerating - their all-time most played lists "
                "are dominated by recent discoveries. They're both more alive right now than ever."
            )

        body_parts = []
        if alignments:
            body_parts.append("What aligns: " + " ".join(alignments))
        if tensions:
            body_parts.append("Where they diverge: " + " ".join(tensions))

        if not body_parts:
            return None

        return {"type": "emotional_alignment", "title": "Emotional alignment", "body": " ".join(body_parts)}

    def _complementary_insight(self, r):
        parts = []

        if r.a_gifts:
            gifts = ", ".join(g["name"] for g in r.a_gifts[:5])
            parts.append(
                f"{r.a.user} could open these doors for {r.b.user}: {gifts}."
            )

        if r.b_gifts:
            gifts = ", ".join(g["name"] for g in r.b_gifts[:5])
            parts.append(
                f"{r.b.user} could open these doors for {r.a.user}: {gifts}."
            )

        if r.a_unique_decades:
            parts.append(
                f"{r.a.user} has explored the {', '.join(sorted(r.a_unique_decades))} "
                f"that {r.b.user} hasn't touched."
            )

        if r.b_unique_decades:
            parts.append(
                f"{r.b.user} has explored the {', '.join(sorted(r.b_unique_decades))} "
                f"that {r.a.user} hasn't touched."
            )

        if not parts:
            return None

        return {
            "type": "complementary",
            "title": "What each holds for the other",
            "body": " ".join(parts),
        }

    def _shadow_comparison_insight(self, r):
        if not r.a.unsaved_long and not r.b.unsaved_long:
            return None

        parts = []

        if r.shared_unsaved_artists:
            shared = ", ".join(list(r.shared_unsaved_artists)[:5])
            parts.append(
                f"They share unsaved obsessions: both play {shared} on repeat without saving. "
                f"Their shadow selves overlap - the things they need but won't claim are the same things."
            )

        if r.a_unsaved_in_b_saved:
            crossover = ", ".join(list(r.a_unsaved_in_b_saved)[:3])
            parts.append(
                f"What {r.a.user} plays but won't save, {r.b.user} has already claimed: {crossover}. "
                f"{r.b.user} has integrated something {r.a.user} is still circling."
            )

        if r.b_unsaved_in_a_saved:
            crossover = ", ".join(list(r.b_unsaved_in_a_saved)[:3])
            parts.append(
                f"And the reverse: {r.b.user}'s unsaved obsessions include {crossover}, "
                f"which {r.a.user} saved long ago."
            )

        if not parts:
            return None

        return {"type": "shadow", "title": "The shadow selves", "body": " ".join(parts)}

    def _dynamic_insight(self, r):
        # Determine the relational dynamic
        a_bigger = r.a.total > r.b.total * 1.5
        b_bigger = r.b.total > r.a.total * 1.5
        a_older = r.a.library_span_days > r.b.library_span_days * 1.3
        b_older = r.b.library_span_days > r.a.library_span_days * 1.3
        a_more_diverse = r.a.unique_artists > r.b.unique_artists * 1.3
        b_more_diverse = r.b.unique_artists > r.a.unique_artists * 1.3

        if a_bigger and a_more_diverse:
            return {
                "type": "dynamic",
                "title": "The dynamic",
                "body": (
                    f"{r.a.user}'s library is significantly larger and more diverse. "
                    f"In this relationship, {r.a.user} is probably the one sending songs, "
                    f"making playlists, saying 'you HAVE to hear this.' "
                    f"{r.b.user} is more focused - fewer tracks but potentially deeper attachment to each one."
                ),
            }
        elif b_bigger and b_more_diverse:
            return {
                "type": "dynamic",
                "title": "The dynamic",
                "body": (
                    f"{r.b.user}'s library is significantly larger and more diverse. "
                    f"In this relationship, {r.b.user} is probably the curator, the DJ, "
                    f"the one always finding something new. "
                    f"{r.a.user} is more selective - each save means more."
                ),
            }
        else:
            return {
                "type": "dynamic",
                "title": "The dynamic",
                "body": (
                    f"Similar sized libraries ({r.a.total:,} vs {r.b.total:,}). "
                    f"Neither is leading the other musically - "
                    f"they're parallel explorers, each on their own path, "
                    f"crossing at the shared artists and diverging into their own territories."
                ),
            }

    def _trajectory_insight(self, r):
        parts = []

        if r.converging:
            shared = ", ".join(list(r.shared_rising)[:4])
            parts.append(
                f"They're converging. Both are currently getting into: {shared}. "
                f"Their tastes are moving toward each other right now."
            )
        elif r.a.rising_artists and r.b.rising_artists:
            parts.append(
                f"They're on different trajectories. "
                f"{r.a.user} is moving toward: {', '.join(r.a.rising_artists[:3])}. "
                f"{r.b.user} is moving toward: {', '.join(r.b.rising_artists[:3])}. "
                f"Parallel paths - not converging, not diverging, just different."
            )

        if r.nostalgia_trend_same and r.a.nostalgia_trend > 3:
            parts.append("Both are reaching further into the past every year. Fellow time travelers.")
        elif not r.nostalgia_trend_same:
            who_past = r.a.user if r.a.nostalgia_trend > r.b.nostalgia_trend else r.b.user
            who_present = r.b.user if who_past == r.a.user else r.a.user
            parts.append(
                f"{who_past} is heading deeper into the past. "
                f"{who_present} is staying closer to the present. "
                f"In five years, their libraries will look more different than they do now."
            )

        if not parts:
            return None

        return {"type": "trajectory", "title": "Where it's going", "body": " ".join(parts)}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def analyze_single(export_path):
    """Analyze a single library and return insights."""
    data = load_export(export_path)
    profile = LibraryProfile(data)
    engine = NarrativeEngine()
    return engine.generate_single(profile)


def analyze_relationship(path_a, path_b):
    """Analyze the relationship between two libraries and return insights."""
    data_a = load_export(path_a)
    data_b = load_export(path_b)
    profile_a = LibraryProfile(data_a)
    profile_b = LibraryProfile(data_b)
    analysis = RelationshipAnalysis(profile_a, profile_b)
    engine = NarrativeEngine()

    # Include individual profiles too
    single_a = engine.generate_single(profile_a)
    single_b = engine.generate_single(profile_b)
    relationship = engine.generate_relationship(analysis)

    return {
        "person_a": {"user": profile_a.user, "insights": single_a},
        "person_b": {"user": profile_b.user, "insights": single_b},
        "relationship": relationship,
    }


if __name__ == "__main__":
    import sys
    if len(sys.argv) == 2:
        insights = analyze_single(sys.argv[1])
        for i in insights:
            print(f"\n--- {i['title']} ---")
            print(i["body"])
    elif len(sys.argv) == 3:
        result = analyze_relationship(sys.argv[1], sys.argv[2])
        print(f"\n{'=' * 50}")
        print(f"  {result['person_a']['user']}")
        print(f"{'=' * 50}")
        for i in result["person_a"]["insights"]:
            print(f"\n{i['body']}")

        print(f"\n{'=' * 50}")
        print(f"  {result['person_b']['user']}")
        print(f"{'=' * 50}")
        for i in result["person_b"]["insights"]:
            print(f"\n{i['body']}")

        print(f"\n{'=' * 50}")
        print(f"  THE RELATIONSHIP")
        print(f"{'=' * 50}")
        for i in result["relationship"]:
            print(f"\n{i['body']}")
    else:
        print("Usage: python3 engine.py <library.json> [other-library.json]")

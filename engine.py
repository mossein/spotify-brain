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

        # Compute archetype
        self._compute_archetype()

    def _compute_archetype(self):
        """Classify into a music archetype based on computed metrics."""

        # Axis 1: Time - when do they listen / save?
        if self.late_night_pct > 25:
            self.time_axis = "Nocturnal"
            self.time_desc = "comes alive after midnight"
        elif self.late_night_pct > 10:
            self.time_axis = "Twilight"
            self.time_desc = "lives in the golden hour"
        else:
            self.time_axis = "Daylight"
            self.time_desc = "listens in the open"

        # Axis 2: Depth - how do they explore?
        if self.one_track_pct > 75:
            self.depth_axis = "Drifter"
            self.depth_desc = "always moving, never settling"
        elif self.top10_loyalty > 30:
            self.depth_axis = "Devotee"
            self.depth_desc = "goes all in on what they love"
        else:
            self.depth_axis = "Cartographer"
            self.depth_desc = "maps the territory between deep and wide"

        # Axis 3: Time direction - past vs present
        if self.nostalgia_trend > 5 and self.current_nostalgia > 10:
            self.direction_axis = "Excavator"
            self.direction_desc = "digging deeper into the past each year"
        elif self.current_nostalgia > 8:
            self.direction_axis = "Archivist"
            self.direction_desc = "curates from across the decades"
        elif self.alltime_recency > 60:
            self.direction_axis = "Accelerator"
            self.direction_desc = "more alive musically right now than ever"
        else:
            self.direction_axis = "Navigator"
            self.direction_desc = "moves freely between past and present"

        # Axis 4: Curation style - save vs play gap
        if self.unsaved_pct > 15:
            self.curation_axis = "Phantom"
            self.curation_desc = "plays songs they won't claim as their own"
        elif self.unsaved_pct > 5:
            self.curation_axis = "Filter"
            self.curation_desc = "selective about what enters the permanent collection"
        else:
            self.curation_axis = "Collector"
            self.curation_desc = "saves everything they love"

        # Axis 5: Emotional register
        if self.anger_index < 1 and self.explicit_pct < 12:
            self.emotion_axis = "Luminist"
            self.emotion_desc = "processes everything through beauty"
        elif self.explicit_pct > 25:
            self.emotion_axis = "Realist"
            self.emotion_desc = "doesn't filter the raw edges"
        elif self.long_track_pct > 10:
            self.emotion_axis = "Contemplative"
            self.emotion_desc = "patient with the slow burn"
        else:
            self.emotion_axis = "Kinetic"
            self.emotion_desc = "needs forward motion"

        # Compound archetype: primary + secondary
        # Primary is the most distinctive axis (furthest from center)
        axes = [
            (self.time_axis, self.time_desc, self._axis_strength("time")),
            (self.depth_axis, self.depth_desc, self._axis_strength("depth")),
            (self.direction_axis, self.direction_desc, self._axis_strength("direction")),
            (self.curation_axis, self.curation_desc, self._axis_strength("curation")),
            (self.emotion_axis, self.emotion_desc, self._axis_strength("emotion")),
        ]
        axes.sort(key=lambda x: -x[2])

        self.archetype_primary = axes[0][0]
        self.archetype_secondary = axes[1][0]
        self.archetype = f"{axes[0][0]} {axes[1][0]}"
        self.archetype_desc_primary = axes[0][1]
        self.archetype_desc_secondary = axes[1][1]

        # All axes for the radar chart
        self.archetype_axes = {
            "time": self.time_axis,
            "depth": self.depth_axis,
            "direction": self.direction_axis,
            "curation": self.curation_axis,
            "emotion": self.emotion_axis,
        }

        # Radar values (0-1 scale for visualization)
        self.radar = {
            "nocturnal": min(self.late_night_pct / 40, 1.0),
            "loyalty": min(self.top10_loyalty / 50, 1.0),
            "nostalgia": min(self.current_nostalgia / 20, 1.0),
            "shadow": min(self.unsaved_pct / 20, 1.0),
            "patience": min(self.long_track_pct / 15, 1.0),
            "exploration": min(self.one_track_pct / 90, 1.0),
            "acceleration": min(self.alltime_recency / 80, 1.0),
            "rawness": min(self.explicit_pct / 30, 1.0),
        }

    def _axis_strength(self, axis):
        """How distinctive is this axis? Higher = more extreme."""
        if axis == "time":
            return abs(self.late_night_pct - 12)  # 12% is "average"
        elif axis == "depth":
            return max(self.one_track_pct - 50, self.top10_loyalty - 15)
        elif axis == "direction":
            return max(abs(self.nostalgia_trend), self.alltime_recency - 30)
        elif axis == "curation":
            return self.unsaved_pct * 2
        elif axis == "emotion":
            return max(10 - self.anger_index * 5, self.long_track_pct, abs(self.explicit_pct - 15))
        return 0


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
    """Turn computed metrics into deeply personal, data-driven narratives."""

    # --- Helpers ---

    def _v(self, variants, *seeds):
        """Deterministically pick a variant based on data seeds."""
        h = hash(tuple(str(s) for s in seeds))
        return variants[h % len(variants)]

    def _fmt(self, items, conj="and"):
        """Format list with Oxford comma: 'a, b, and c'."""
        if not items:
            return ""
        if len(items) == 1:
            return items[0]
        if len(items) == 2:
            return f"{items[0]} {conj} {items[1]}"
        return ", ".join(items[:-1]) + f", {conj} {items[-1]}"

    def _top(self, p, n=3):
        """Top n artist names from saved library."""
        return [a for a, _ in p.artist_counts.most_common(n)]

    # --- Generators ---

    def generate_single(self, profile):
        """Generate insights for a single library."""
        insights = [
            self._archetype_insight(profile),
            self._identity_insight(profile),
            self._emotional_insight(profile),
            self._temporal_insight(profile),
            self._nostalgia_insight(profile),
            self._unsaved_insight(profile),
            self._evolution_insight(profile),
        ]
        return [i for i in insights if i]

    def generate_relationship(self, analysis):
        """Generate insights for a relationship between two libraries."""
        insights = [
            self._archetype_pairing_insight(analysis),
            self._connection_insight(analysis),
            self._shared_ground_insight(analysis),
            self._emotional_alignment_insight(analysis),
            self._complementary_insight(analysis),
            self._shadow_comparison_insight(analysis),
            self._dynamic_insight(analysis),
            self._trajectory_insight(analysis),
        ]
        return [i for i in insights if i]

    # --- Single library narrative blocks ---

    def _archetype_insight(self, p):
        top3 = self._top(p, 3)
        top_str = self._fmt(top3)
        kept = p.unique_artists - p.one_track_artists

        # Build specific archetype detail based on what's most distinctive
        details = []

        if p.late_night_pct > 30:
            details.append(self._v([
                f"{p.late_night_pct:.0f}% of listening happens between midnight and dawn",
                f"nearly a third of all plays land after midnight",
                f"the hours after midnight account for {p.late_night_pct:.0f}% of all listening",
            ], p.user, "time"))
        elif p.late_night_pct > 20:
            details.append(f"{p.late_night_pct:.0f}% of plays fall in the small hours")

        if p.one_track_pct > 80:
            details.append(self._v([
                f"only {kept} out of {p.unique_artists:,} artists earned more than a single save",
                f"{p.one_track_pct:.0f}% of artists got exactly one track before {p.user} moved on",
            ], p.user, "depth"))
        elif p.top10_loyalty > 35:
            details.append(
                f"{p.top10_loyalty:.0f}% of the library belongs to just 10 artists, led by {top3[0] if top3 else 'a few favorites'}"
            )

        if p.unsaved_pct > 20:
            details.append(f"{p.unsaved_pct:.0f}% of top-played tracks were never saved")

        body = (
            f"{p.user} is a {p.archetype}. "
            f"{p.archetype_desc_primary.capitalize()} and {p.archetype_desc_secondary}."
        )
        if details:
            body += " " + ". ".join(details) + "."
        body += (
            f" Full signature: "
            f"{p.time_axis} / {p.depth_axis} / {p.direction_axis} / "
            f"{p.curation_axis} / {p.emotion_axis}."
        )

        return {
            "type": "archetype",
            "title": p.archetype,
            "body": body,
            "archetype": p.archetype,
            "axes": p.archetype_axes,
            "radar": p.radar,
        }

    def _identity_insight(self, p):
        top5 = self._top(p, 5)
        top3 = top5[:3]
        top_str = self._fmt(top3)
        kept = p.unique_artists - p.one_track_artists
        tracks_per = p.total / max(p.unique_artists, 1)

        # Top artist track counts for specificity
        top1_count = p.artist_counts[top5[0]] if top5 else 0
        top3_total = sum(p.artist_counts[a] for a in top3) if top3 else 0

        if p.one_track_pct > 85:
            # Extreme sampler — barely anyone gets a second chance
            title = f"{p.user} never looks back"
            body = self._v([
                (f"{p.unique_artists:,} artists, and {p.one_track_pct:.0f}% of them "
                 f"appear exactly once. {p.user} moves through music the way some people "
                 f"move through cities — always passing through, rarely unpacking. "
                 f"Only {kept} artists earned more than one track. "
                 f"The ones who stuck: {top_str}."),
                (f"Out of {p.unique_artists:,} artists in this library, only {kept} "
                 f"got a second save. That's a {p.one_track_pct:.0f}% single-visit rate. "
                 f"{p.user} listens like someone channel-surfing at 3am — "
                 f"everything gets a moment, almost nothing gets two. "
                 f"The rare repeats: {top_str} with {top3_total} tracks between them."),
                (f"A {p.total:,}-track library across {p.unique_artists:,} artists, "
                 f"and {p.one_track_pct:.0f}% of those artists appear once and vanish. "
                 f"{p.user} doesn't collect artists — {p.user} passes through them. "
                 f"{top_str} are the {kept} exceptions who got a return visit."),
            ], p.user, p.total)

        elif p.one_track_pct > 75:
            # Wide explorer — samples broadly
            title = f"{p.user} is a wide explorer"
            body = self._v([
                (f"{p.user}'s library spans {p.unique_artists:,} artists, "
                 f"and {p.one_track_pct:.0f}% of them appear only once. "
                 f"{top_str} are the pillars — {top3_total} tracks between them — "
                 f"but the rest is a trail of everywhere {p.user} has been."),
                (f"{p.unique_artists:,} artists. {p.one_track_pct:.0f}% show up once "
                 f"and vanish. This isn't a collection of favorites — it's a travel log. "
                 f"{top_str} are the home bases {p.user} returns to between expeditions, "
                 f"with {top1_count} tracks for {top5[0] if top5 else 'the top artist'} alone."),
                (f"A library of {p.total:,} tracks across {p.unique_artists:,} artists. "
                 f"Most of those artists are one-save encounters — {p.user} keeps moving. "
                 f"Only {kept} artists earned a return trip. "
                 f"The inner circle: {self._fmt(top5)} — but even they share the space "
                 f"with {p.one_track_artists:,} artists who got a single track."),
            ], p.user, p.total)

        elif p.one_track_pct > 60:
            # Moderate explorer — curious but gives artists a fair shot
            title = f"{p.user} explores with intention"
            body = self._v([
                (f"{p.unique_artists:,} artists, {p.one_track_pct:.0f}% appearing once. "
                 f"That's exploratory but not restless — {p.user} gives artists a real chance "
                 f"before moving on. When they return, they return properly: "
                 f"{top_str} have {top3_total} tracks between them."),
                (f"{p.total:,} tracks spread across {p.unique_artists:,} artists. "
                 f"About {p.one_track_pct:.0f}% are single-save encounters, "
                 f"but that leaves {kept} artists who made a lasting impression. "
                 f"{top5[0] if top5 else 'The top artist'} leads with {top1_count} tracks — "
                 f"the clearest signal of what {p.user} actually gravitates toward."),
            ], p.user, p.total)

        elif p.top10_loyalty > 40:
            # Extreme devotee — library is dominated by a handful of artists
            title = f"{p.user} goes all in"
            body = self._v([
                (f"{p.top10_loyalty:.0f}% of the library comes from just 10 artists. "
                 f"{top5[0] if top5 else 'The top artist'} alone accounts for {top1_count} tracks. "
                 f"When {p.user} finds something, they don't sample — they move in. "
                 f"The core rotation: {self._fmt(top5)}."),
                (f"{p.user} doesn't browse. {p.top10_loyalty:.0f}% of all {p.total:,} "
                 f"tracks belong to 10 artists. "
                 f"{top5[0] if top5 else 'The top artist'} leads with {top1_count} tracks — "
                 f"that's not casual listening, that's a relationship. "
                 f"The inner circle: {self._fmt(top5)}."),
                (f"This is a library built on loyalty. {p.top10_loyalty:.0f}% of everything "
                 f"belongs to just 10 artists: {self._fmt(top5[:4])} and a few others. "
                 f"{top1_count} tracks for {top5[0] if top5 else 'the favorite'} alone. "
                 f"{p.user} finds what works and stays there."),
            ], p.user, p.total)

        elif p.top10_loyalty > 30:
            # Deep diver — clear favorites but still explores
            title = f"{p.user} is a deep diver"
            body = self._v([
                (f"{p.top10_loyalty:.0f}% of the library comes from 10 artists — "
                 f"{top_str} leading the count. "
                 f"{top5[0] if top5 else 'The top artist'} has {top1_count} tracks. "
                 f"When {p.user} connects with an artist, they stay."),
                (f"{p.user} goes deep. {p.top10_loyalty:.0f}% of {p.total:,} tracks "
                 f"come from a core 10. {top_str} form the backbone — "
                 f"the rest of the {p.unique_artists:,} artists fill in the margins."),
            ], p.user, p.total)

        else:
            # Balanced — neither extreme
            title = f"{p.user} balances depth and range"
            body = self._v([
                (f"{p.unique_artists:,} artists across {p.total:,} tracks — "
                 f"an average of {tracks_per:.1f} tracks per artist. "
                 f"Enough depth to know what they love ({top_str} are the anchors), "
                 f"enough range to keep discovering. "
                 f"Neither obsessive nor restless — just someone who listens with intent."),
                (f"Not a drifter, not a devotee. {p.user} runs {p.total:,} tracks "
                 f"across {p.unique_artists:,} artists — a {tracks_per:.1f}-track average "
                 f"per artist. {top_str} get the most plays, "
                 f"but no single artist dominates. A library that's both wide and lived-in."),
            ], p.user, p.total)

        return {"type": "identity", "title": title, "body": body}

    def _emotional_insight(self, p):
        parts = []
        top3 = self._top(p, 3)

        # Anger / softness
        if p.anger_index < 0.5:
            parts.append(self._v([
                (f"{p.total:,} tracks and almost zero aggression. No rage, no confrontation. "
                 f"When {p.user} hurts, the music doesn't fight — it holds. "
                 f"A library built for processing, not punching."),
                (f"Scan {p.total:,} tracks and you'll barely find an edge. "
                 f"{p.user}'s library is a shelter, not a weapon — "
                 f"whatever they're going through, the music absorbs it."),
                (f"One of the gentlest libraries you'll see. {p.total:,} tracks, "
                 f"barely a trace of anger anywhere. {p.user} processes through "
                 f"beauty and warmth, never through force."),
            ], p.user, "emo"))
        elif p.anger_index < 1.5:
            parts.append(self._v([
                (f"Almost no anger in {p.total:,} tracks. When {p.user} is in pain, "
                 f"the music doesn't scream — it glows. That's not avoidance. "
                 f"That's a whole philosophy of feeling."),
                (f"Very little rage anywhere in this library. {p.user} doesn't use "
                 f"music as a weapon — it's more like weather. "
                 f"Something to be inside of, not something to wield."),
                (f"{p.total:,} tracks and barely any confrontation. "
                 f"{p.user} gravitates toward light, not heat. "
                 f"The emotional range is wide — it just doesn't include war."),
            ], p.user, "emo"))
        elif p.anger_index > 5:
            parts.append(self._v([
                (f"{p.anger_index:.1f}% of tracks carry aggression in the title. "
                 f"{p.user} doesn't flinch from the heavy stuff — this library has teeth."),
                (f"This library bites. {p.anger_index:.1f}% of track names carry anger words. "
                 f"{p.user} uses music the way some people use a punching bag."),
            ], p.user, "emo"))
        elif p.anger_index > 3:
            parts.append(
                f"A noticeable edge runs through this library — "
                f"{p.anger_index:.1f}% of tracks carry confrontation in their titles. "
                f"{p.user} isn't afraid of music that pushes back."
            )

        # Explicit content
        if p.explicit_pct < 8:
            parts.append(self._v([
                f"Only {p.explicit_pct:.0f}% explicit. One of the cleanest libraries around.",
                f"{p.explicit_pct:.0f}% explicit content — remarkably clean. "
                f"The music speaks without swearing.",
            ], p.user, "exp"))
        elif p.explicit_pct < 15:
            pass  # unremarkable, skip
        elif p.explicit_pct > 35:
            parts.append(self._v([
                (f"{p.explicit_pct:.0f}% explicit. {p.user} doesn't filter anything — "
                 f"if the music hits, the language is irrelevant."),
                (f"{p.explicit_pct:.0f}% explicit content. Unfiltered, uncensored — "
                 f"{p.user} takes music as it comes, clean version be damned."),
            ], p.user, "exp"))
        elif p.explicit_pct > 25:
            parts.append(
                f"{p.explicit_pct:.0f}% explicit. {p.user} leans raw — "
                f"the library doesn't shy from unfiltered expression."
            )
        elif p.explicit_pct > 20:
            parts.append(f"{p.explicit_pct:.0f}% explicit — a touch more edge than average.")

        # Collaborations
        if p.collab_pct > 45:
            parts.append(self._v([
                (f"{p.collab_pct:.0f}% collaborations — nearly half the library. "
                 f"{p.user} is drawn to what happens when worlds collide."),
                (f"Almost half the library ({p.collab_pct:.0f}%) features multiple artists. "
                 f"{p.user} doesn't just like artists — {p.user} likes what happens when they meet."),
            ], p.user, "coll"))
        elif p.collab_pct > 35:
            parts.append(
                f"{p.collab_pct:.0f}% of tracks feature multiple artists. "
                f"{p.user} gravitates toward collision — different voices in the same room."
            )
        elif p.collab_pct < 15:
            parts.append(
                f"Only {p.collab_pct:.0f}% collaborations. {p.user} prefers "
                f"artists in their own lane — solo visions, not committee work."
            )

        # Long tracks / patience
        if p.long_track_pct > 15:
            parts.append(self._v([
                (f"{p.long_track_pct:.0f}% of tracks run past 6 minutes. "
                 f"{p.user} has patience most don't — "
                 f"the kind that lets a song take 4 minutes just to arrive."),
                (f"{p.long_track_pct:.0f}% of the library is over 6 minutes. "
                 f"These aren't background tracks — they're commitments. "
                 f"{p.user} doesn't need the payoff in the first 30 seconds."),
            ], p.user, "long"))
        elif p.long_track_pct > 10:
            parts.append(
                f"{p.long_track_pct:.0f}% of tracks break 6 minutes. "
                f"{p.user} has room for the slow burn."
            )

        if not parts:
            return None

        return {"type": "emotional", "title": "Emotional signature", "body": " ".join(parts)}

    def _temporal_insight(self, p):
        parts = []

        if p.library_span_days > 0:
            years = p.library_span_days / 365
            rate = p.total / max(years, 0.1)

            if rate > 200:
                pace_desc = "a voracious pace"
            elif rate > 100:
                pace_desc = "a steady stream"
            elif rate > 50:
                pace_desc = "a measured drip"
            else:
                pace_desc = "a slow, deliberate accumulation"

            parts.append(self._v([
                (f"{p.total:,} tracks saved over {years:.1f} years "
                 f"(since {p.first_save.strftime('%B %Y')}). "
                 f"That's roughly {rate:.0f} tracks per year — {pace_desc}."),
                (f"The first save was {p.first_save.strftime('%B %Y')}. "
                 f"{years:.1f} years and {p.total:,} tracks later, still going. "
                 f"Average pace: {rate:.0f} tracks a year."),
                (f"Started saving in {p.first_save.strftime('%B %Y')}. "
                 f"{p.total:,} tracks across {years:.1f} years — "
                 f"about {rate:.0f} a year, {rate / 12:.0f} a month."),
            ], p.user, "temp"))

        # Gaps
        if p.longest_gap > 365:
            gap = p.gaps[0]
            years_gap = gap['days'] / 365
            parts.append(self._v([
                (f"Then there's the silence: {gap['days']:,} days — "
                 f"nearly {years_gap:.1f} years — between {gap['start']} and {gap['end']}. "
                 f"Not a hiatus. A disappearance. When the music came back, "
                 f"it came back different."),
                (f"The gap between {gap['start']} and {gap['end']}: "
                 f"{gap['days']:,} days of nothing. {years_gap:.1f} years "
                 f"without a single save. Whatever happened in that window, "
                 f"Spotify wasn't part of it."),
                (f"{gap['days']:,} days of silence. From {gap['start']} to {gap['end']}, "
                 f"the library flatlined. {years_gap:.1f} years. "
                 f"Something closed. And when it reopened, a new era started."),
            ], p.user, gap['days']))
        elif p.longest_gap > 120:
            gap = p.gaps[0]
            months = gap['days'] / 30
            parts.append(self._v([
                (f"The longest silence: {gap['days']} days between "
                 f"{gap['start']} and {gap['end']}. "
                 f"Nearly {months:.0f} months without saving. "
                 f"When {p.user} came back, the library entered a new chapter."),
                (f"A {gap['days']}-day gap between {gap['start']} and {gap['end']}. "
                 f"{months:.0f} months of radio silence. "
                 f"Something shifted during that window."),
            ], p.user, gap['days']))
        elif p.longest_gap > 60:
            gap = p.gaps[0]
            parts.append(
                f"The longest break: {gap['days']} days between "
                f"{gap['start']} and {gap['end']}. A pause, not a stop."
            )

        # Quiet vs busy years
        if hasattr(p, 'quietest_year') and hasattr(p, 'busiest_year'):
            ratio = p.quietest_year[1] / max(p.busiest_year[1], 1)
            if ratio < 0.1:
                parts.append(self._v([
                    (f"In {p.quietest_year[0]}: {p.quietest_year[1]} tracks. "
                     f"In {p.busiest_year[0]}: {p.busiest_year[1]}. "
                     f"That's not a difference in habit — it's a different person."),
                    (f"{p.quietest_year[0]} had just {p.quietest_year[1]} saves. "
                     f"{p.busiest_year[0]} had {p.busiest_year[1]}. "
                     f"A {p.busiest_year[1] // max(p.quietest_year[1], 1)}x difference "
                     f"that marks a complete transformation."),
                ], p.user, "quiet"))
            elif ratio < 0.25:
                parts.append(self._v([
                    (f"Quietest year: {p.quietest_year[0]} with {p.quietest_year[1]} tracks. "
                     f"Busiest: {p.busiest_year[0]} with {p.busiest_year[1]}. "
                     f"That gap is a chapter boundary."),
                    (f"{p.quietest_year[0]}: {p.quietest_year[1]} tracks. "
                     f"{p.busiest_year[0]}: {p.busiest_year[1]}. "
                     f"The library has seasons — and {p.busiest_year[0]} was summer."),
                ], p.user, "quiet"))

        # Binges
        if p.biggest_binge > 20:
            day, count = p.binge_days[0]
            parts.append(self._v([
                (f"Biggest binge: {count} tracks on {day}. "
                 f"That's not browsing — that's a fever. "
                 f"Something was being chased."),
                (f"{count} tracks saved in a single day ({day}). "
                 f"Whatever happened that day, the music was the only way to process it."),
            ], p.user, count))
        elif p.biggest_binge > 12:
            day, count = p.binge_days[0]
            parts.append(self._v([
                (f"Biggest single-day save: {count} tracks on {day}. "
                 f"A rabbit hole that went deep."),
                (f"{count} tracks on {day}. That's a late-night discovery session "
                 f"that refused to end."),
            ], p.user, count))
        elif p.biggest_binge > 8:
            day, count = p.binge_days[0]
            parts.append(
                f"Peak saving day: {count} tracks on {day}."
            )

        if not parts:
            return None

        return {"type": "temporal", "title": "The timeline", "body": " ".join(parts)}

    def _nostalgia_insight(self, p):
        # Build decade breakdown for specificity
        significant_decades = sorted(
            [(d, pct) for d, pct in p.decade_pct.items() if pct > 5],
            key=lambda x: -x[1]
        )
        decade_str = ", ".join(f"{d} ({pct:.0f}%)" for d, pct in significant_decades[:4])
        num_decades = len([d for d, pct in p.decade_pct.items() if pct > 3])

        if p.nostalgia_trend > 8:
            # Extreme excavation
            return {
                "type": "nostalgia",
                "title": "The backward reach",
                "body": self._v([
                    (f"{p.user} is on a one-way trip into the past. "
                     f"Currently averaging {p.current_nostalgia:.0f} years of lookback, "
                     f"and the number keeps climbing. Early saves were mostly current — "
                     f"now the library pulls from wells decades deep. "
                     f"The spread: {decade_str}. "
                     f"Someone tracing every sound back to its origin."),
                    (f"The nostalgia trajectory is steep and accelerating. "
                     f"{p.user} started by saving what was new, "
                     f"now averages {p.current_nostalgia:.0f} years behind the present. "
                     f"Home decade: {p.home_decade}, but the reach extends across "
                     f"{num_decades} decades: {decade_str}. "
                     f"This isn't regression. It's archaeology."),
                ], p.user, "nost"),
            }

        elif p.nostalgia_trend > 5:
            return {
                "type": "nostalgia",
                "title": "The backward reach",
                "body": self._v([
                    (f"{p.user} reaches further into the past every year. "
                     f"Currently averaging {p.current_nostalgia:.0f} years of lookback. "
                     f"The spread: {decade_str}. "
                     f"This isn't nostalgia — it's excavation. "
                     f"Tracing every thread back to its source."),
                    (f"Each year, {p.user}'s saves reach a little further back. "
                     f"Average lookback: {p.current_nostalgia:.0f} years. "
                     f"The library has been migrating from {p.home_decade} outward, "
                     f"now spanning {decade_str}."),
                ], p.user, "nost"),
            }

        elif p.current_nostalgia > 12:
            return {
                "type": "nostalgia",
                "title": "The archivist",
                "body": self._v([
                    (f"{p.user} listens {p.current_nostalgia:.0f} years behind the present "
                     f"on average. Home decade: {p.home_decade}. "
                     f"Distribution: {decade_str}. "
                     f"A curator, not just a consumer — someone who believes "
                     f"the canon wasn't built yesterday."),
                    (f"An average lookback of {p.current_nostalgia:.0f} years. "
                     f"The library lives in the {p.home_decade} but branches into {decade_str}. "
                     f"{p.user} treats music history as a living thing, not a museum."),
                ], p.user, "nost"),
            }

        elif p.current_nostalgia > 8:
            return {
                "type": "nostalgia",
                "title": "The archivist",
                "body": self._v([
                    (f"{p.user} listens {p.current_nostalgia:.0f} years behind the present "
                     f"on average. Home decade: {p.home_decade}. "
                     f"Someone who trusts that the best stuff has already been made "
                     f"and the job is to find it."),
                    (f"Average lookback: {p.current_nostalgia:.0f} years. "
                     f"Rooted in the {p.home_decade} with a spread across {decade_str}. "
                     f"{p.user} keeps one ear in the past and one in the present."),
                ], p.user, "nost"),
            }

        elif p.current_nostalgia < 3 and p.total > 100:
            return {
                "type": "nostalgia",
                "title": "Living in the present",
                "body": (
                    f"{p.user} listens almost exclusively to what's current — "
                    f"only {p.current_nostalgia:.1f} years of lookback on average. "
                    f"The library is a snapshot of right now, not a dig through history. "
                    f"{p.home_decade} dominates everything."
                ),
            }

        return None

    def _unsaved_insight(self, p):
        if not p.unsaved_long:
            return None

        unsaved_names = [f"{t['artists']} - {t['name']}" for t in p.unsaved_long[:7]]
        count = len(p.unsaved_long)

        # Look for repeat artists in unsaved
        unsaved_artists = [t['artists'] for t in p.unsaved_long]
        repeat_artists = [a for a in set(unsaved_artists) if unsaved_artists.count(a) > 1]

        body_parts = []

        if count > 10:
            body_parts.append(self._v([
                (f"{count} songs in the all-time most played that {p.user} has never saved. "
                 f"That's a significant shadow library — "
                 f"music the body wants but the identity won't claim."),
                (f"{p.user} has {count} top-played tracks that never got saved. "
                 f"These aren't accidents. These are songs on repeat "
                 f"that never made it to the permanent collection."),
                (f"A shadow library of {count} tracks. Played enough to rank in the all-time top, "
                 f"but never saved. {p.user} keeps these at arm's length."),
            ], p.user, "unsaved"))
        elif count > 5:
            body_parts.append(self._v([
                (f"{count} songs in {p.user}'s most-played that were never saved. "
                 f"Played on repeat but kept at arm's length."),
                (f"{p.user} has {count} top-played tracks they never hit save on. "
                 f"The music gets played — it just doesn't get claimed."),
            ], p.user, "unsaved"))
        else:
            body_parts.append(
                f"{p.user} has {count} songs in their all-time most played "
                f"that they've never saved."
            )

        body_parts.append(
            f"The unnamed obsessions: {', '.join(unsaved_names)}."
        )

        if repeat_artists:
            body_parts.append(
                f"{self._fmt(repeat_artists)} shows up multiple times in the unsaved — "
                f"an artist {p.user} keeps circling without committing to."
            )

        body_parts.append(self._v([
            "The saved library is a self-portrait. "
            "The unsaved plays are the parts that got painted over.",
            "What you save is who you say you are. "
            "What you play without saving is who you are when nobody's looking.",
            "The gap between saved and played is the gap between identity and instinct.",
            "Saving is a declaration. Playing without saving is a confession.",
        ], p.user, count))

        return {
            "type": "unsaved",
            "title": "The unsaved obsessions",
            "body": " ".join(body_parts),
        }

    def _evolution_insight(self, p):
        parts = []

        if p.rising_artists:
            rising = self._fmt(p.rising_artists[:5])
            parts.append(self._v([
                f"Currently rising: {rising}.",
                f"What's new in the rotation: {rising}.",
                f"The current obsessions: {rising}.",
                f"Lately it's been: {rising}.",
            ], p.user, "rise"))

        if p.falling_artists:
            falling = self._fmt(p.falling_artists[:5])
            parts.append(self._v([
                f"Cooling off: {falling}.",
                f"Fading from rotation: {falling}.",
                f"Stepping back from: {falling}.",
            ], p.user, "fall"))

        if p.alltime_recency > 75:
            parts.append(self._v([
                (f"{p.alltime_recency:.0f}% of {p.user}'s all-time most played "
                 f"were saved in the last year. The entire musical identity "
                 f"is being rewritten in real time."),
                (f"{p.alltime_recency:.0f}% of the all-time heavy rotation is from the past year. "
                 f"{p.user}'s music is more alive right now than it has ever been — "
                 f"the old favorites are being replaced wholesale."),
                (f"This is a library in transformation. {p.alltime_recency:.0f}% of the all-time "
                 f"most played were saved recently. {p.user} isn't settling — "
                 f"{p.user} is accelerating."),
            ], p.user, "rec"))
        elif p.alltime_recency > 60:
            parts.append(self._v([
                (f"{p.alltime_recency:.0f}% of {p.user}'s all-time most played were saved "
                 f"in the last year. The music is more alive right now than ever. "
                 f"This isn't someone coasting on nostalgia."),
                (f"{p.alltime_recency:.0f}% of the all-time top tracks are recent saves. "
                 f"{p.user} isn't living off old favorites — "
                 f"the current era is the most active one yet."),
            ], p.user, "rec"))
        elif p.alltime_recency < 20 and p.total > 200:
            parts.append(self._v([
                (f"Only {p.alltime_recency:.0f}% of {p.user}'s all-time favorites "
                 f"are from the last year. The classics are locked in — "
                 f"new discoveries have to compete with years of history."),
                (f"{p.alltime_recency:.0f}% all-time recency. {p.user}'s musical identity "
                 f"was shaped years ago — recent saves orbit the existing core, "
                 f"they don't replace it."),
            ], p.user, "rec"))

        if not parts:
            return None

        return {"type": "evolution", "title": "Where it's heading", "body": " ".join(parts)}

    # --- Relationship narrative blocks ---

    def _archetype_pairing_insight(self, r):
        a = r.a
        b = r.b

        # Find shared and different axes
        shared_axes = []
        different_axes = []
        for axis in ["time", "depth", "direction", "curation", "emotion"]:
            a_val = a.archetype_axes[axis]
            b_val = b.archetype_axes[axis]
            if a_val == b_val:
                shared_axes.append(a_val)
            else:
                different_axes.append((axis, a_val, b_val))

        parts = [f"A {a.archetype} and a {b.archetype}."]

        if len(shared_axes) >= 4:
            parts.append(
                f"Nearly identical profiles. They share: {', '.join(shared_axes).lower()}. "
                f"These two process music the same way — "
                f"the differences are in the details, not the structure."
            )
        elif len(shared_axes) >= 2:
            parts.append(self._v([
                (f"They share: {', '.join(shared_axes).lower()}. "
                 f"These are the frequencies where they naturally sync."),
                (f"Common wiring: both are {', '.join(shared_axes).lower()}. "
                 f"This is where the connection has its foundation."),
                (f"Shared axes: {', '.join(shared_axes).lower()}. "
                 f"These traits mean they process music through some of the same filters."),
            ], a.user, b.user))
        elif shared_axes:
            parts.append(
                f"They share one axis: {shared_axes[0].lower()}. "
                f"A single thread connecting otherwise different musical wiring."
            )

        if different_axes:
            tensions = []
            for axis, a_val, b_val in different_axes:
                tensions.append(f"{a.user} is a {a_val}, {b.user} is a {b_val}")

            if len(different_axes) >= 4:
                parts.append(self._v([
                    (f"Almost everything else diverges. "
                     f"{'. '.join(tensions)}. "
                     f"These aren't just different tastes — they're different "
                     f"relationships with music entirely."),
                    (f"Where it splits: {'. '.join(tensions)}. "
                     f"More contrast than overlap — which means more to discover "
                     f"in each other's libraries."),
                ], a.user, b.user))
            else:
                parts.append(self._v([
                    (f"Where they diverge: {'. '.join(tensions)}. "
                     f"The tension between these positions is where the relationship lives."),
                    (f"The splits: {'. '.join(tensions)}. "
                     f"This is where they challenge each other — "
                     f"the gaps where one can show the other something new."),
                    (f"Different on: {'. '.join(tensions)}. "
                     f"These divergences aren't friction — they're the interesting part."),
                ], a.user, b.user))

        # Specific interesting pairings
        if a.archetype_primary == b.archetype_primary:
            parts.append(self._v([
                (f"Same primary archetype ({a.archetype_primary}). "
                 f"They recognize each other immediately — mirror energy, "
                 f"for better and worse."),
                (f"Both lead with {a.archetype_primary}. "
                 f"Instant recognition — they'll understand each other's instincts "
                 f"without explanation."),
            ], a.user, "pair"))
        elif (a.archetype_primary in ("Excavator", "Archivist") and
              b.archetype_primary in ("Accelerator", "Navigator")) or \
             (b.archetype_primary in ("Excavator", "Archivist") and
              a.archetype_primary in ("Accelerator", "Navigator")):
            past_person = a.user if a.archetype_primary in ("Excavator", "Archivist") else b.user
            now_person = b.user if past_person == a.user else a.user
            parts.append(
                f"{past_person} pulls from the past, {now_person} lives in the now. "
                f"Together they cover the full timeline."
            )

        return {
            "type": "archetype_pairing",
            "title": f"{a.archetype} meets {b.archetype}",
            "body": " ".join(parts),
        }

    def _connection_insight(self, r):
        overlap = r.artist_jaccard * 100
        shared_count = len(r.shared_artists)
        total_union = len(r.a.artist_set | r.b.artist_set)

        if overlap > 40:
            vibe = "practically the same person"
            desc = self._v([
                (f"{shared_count} shared artists out of {total_union} total — "
                 f"a {overlap:.0f}% overlap. These libraries grew up together."),
                (f"A {overlap:.0f}% artist overlap. {shared_count} artists in common. "
                 f"At this level, they're sharing a musical nervous system."),
            ], r.a.user, "conn")
        elif overlap > 30:
            vibe = "deeply intertwined"
            desc = (f"musical siblings — {shared_count} shared artists, "
                    f"a {overlap:.0f}% overlap. They could swap playlists and feel at home.")
        elif overlap > 20:
            vibe = "significantly connected"
            desc = self._v([
                (f"{shared_count} artists in common ({overlap:.0f}% overlap). "
                 f"Solid shared ground — they could trade recommendations all day."),
                (f"A {overlap:.0f}% overlap across {shared_count} artists. "
                 f"They speak the same musical language, "
                 f"even if they say different things with it."),
            ], r.a.user, "conn")
        elif overlap > 10:
            vibe = "connected"
            desc = self._v([
                (f"{shared_count} artists in common ({overlap:.0f}% overlap). "
                 f"Enough to bond over, enough difference to keep it interesting."),
                (f"A {overlap:.0f}% overlap — {shared_count} shared artists. "
                 f"Not twins, but they share enough DNA to understand each other."),
            ], r.a.user, "conn")
        elif overlap > 5:
            vibe = "complementary"
            desc = self._v([
                (f"Only {shared_count} shared artists ({overlap:.0f}%). "
                 f"Different worlds, but the edges touch — "
                 f"that's where the interesting part is."),
                (f"{overlap:.0f}% overlap — just {shared_count} artists in common. "
                 f"More different than alike, which means more to offer each other."),
            ], r.a.user, "conn")
        else:
            vibe = "from different universes"
            desc = self._v([
                (f"Just {shared_count} artists in common ({overlap:.0f}%). "
                 f"Two completely different musical worlds. "
                 f"The value here is in the distance between them."),
                (f"{overlap:.0f}% overlap. {shared_count} shared artists out of {total_union}. "
                 f"These libraries are perpendicular — "
                 f"everything one offers is new to the other."),
            ], r.a.user, "conn")

        return {
            "type": "connection",
            "title": f"{r.a.user} and {r.b.user}: {vibe}",
            "body": (
                f"These two libraries are {vibe}. {desc} "
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

        parts = [self._v([
            f"The shared ground: {', '.join(names)}.",
            f"Where they meet: {', '.join(names)}.",
            f"Common territory: {', '.join(names)}.",
        ], r.a.user, "shared")]

        # Interesting rank divergences
        if r.rank_divergences:
            div = r.rank_divergences[0]
            parts.append(self._v([
                (f"But shared doesn't mean same. {div['name']} is #{div['a_rank']} "
                 f"for {r.a.user} and #{div['b_rank']} for {r.b.user}. "
                 f"Same artist, different weight — "
                 f"they hear the same music but it means different things."),
                (f"Shared artists hit differently. {div['name']}: "
                 f"#{div['a_rank']} for {r.a.user}, #{div['b_rank']} for {r.b.user}. "
                 f"Same sound, different place in the story."),
            ], r.a.user, "div"))

        if r.shared_current_artists:
            current = ", ".join(list(r.shared_current_artists)[:5])
            parts.append(self._v([
                f"Right now they're both listening to: {current}.",
                f"Currently overlapping on: {current}.",
                f"In real time, they're both in: {current}.",
            ], r.a.user, "curr"))

        return {"type": "shared", "title": "Common ground", "body": " ".join(parts)}

    def _emotional_alignment_insight(self, r):
        alignments = []
        tensions = []

        if r.both_low_anger:
            alignments.append(self._v([
                "Neither library carries much anger — both process through beauty, not confrontation.",
                "Low aggression on both sides. These two share a soft emotional palette.",
                "Both libraries lean gentle — almost no rage in either collection.",
            ], r.a.user, "anger"))

        if r.both_explorers:
            alignments.append(self._v([
                (f"Both wide explorers — {r.a.user} at {r.a.one_track_pct:.0f}% one-track artists, "
                 f"{r.b.user} at {r.b.one_track_pct:.0f}%. Always moving to the next thing."),
                "Both restless samplers with high one-track artist ratios. "
                "Neither stays long — they bond over the chase, not the catch.",
            ], r.a.user, "expl"))
        elif r.both_loyalists:
            alignments.append(self._v([
                (f"Both deep divers — {r.a.user} at {r.a.top10_loyalty:.0f}% top-10 loyalty, "
                 f"{r.b.user} at {r.b.top10_loyalty:.0f}%. They go all in on what they love."),
                "Both concentrate their libraries around a core few artists. "
                "Loyalty as a shared language.",
            ], r.a.user, "loy"))
        elif r.loyalty_diff > 20:
            explorer = r.a.user if r.a.one_track_pct > r.b.one_track_pct else r.b.user
            devotee = r.b.user if explorer == r.a.user else r.a.user
            tensions.append(
                f"{explorer} explores widely while {devotee} goes deep. "
                f"One maps the territory, the other builds a home in it."
            )

        if r.same_home_decade:
            alignments.append(self._v([
                f"Same home decade: {r.a.home_decade}. They grew up in the same musical era.",
                f"Both rooted in the {r.a.home_decade}. A shared sonic foundation.",
            ], r.a.user, "decade"))
        else:
            tensions.append(self._v([
                (f"Different home decades — {r.a.user} in the {r.a.home_decade}, "
                 f"{r.b.user} in the {r.b.home_decade}. "
                 f"They carry different eras inside them."),
                (f"{r.a.user} lives in the {r.a.home_decade}, "
                 f"{r.b.user} in the {r.b.home_decade}. "
                 f"Different soundtracks for different timelines."),
            ], r.a.user, "decade"))

        if r.both_nostalgic:
            alignments.append(self._v([
                (f"Both reach deep into the past — "
                 f"{r.a.user} averages {r.a.current_nostalgia:.0f} years back, "
                 f"{r.b.user} {r.b.current_nostalgia:.0f}. Fellow archivists."),
                "Both pull from deep wells. They share a belief that the good stuff "
                "isn't all happening right now.",
            ], r.a.user, "nost"))
        elif r.nostalgia_diff > 8:
            who_past = r.a.user if r.a.current_nostalgia > r.b.current_nostalgia else r.b.user
            who_present = r.b.user if who_past == r.a.user else r.a.user
            past_val = max(r.a.current_nostalgia, r.b.current_nostalgia)
            present_val = min(r.a.current_nostalgia, r.b.current_nostalgia)
            tensions.append(
                f"{who_past} listens {past_val:.0f} years behind the present. "
                f"{who_present} stays closer to now ({present_val:.0f} years back). "
                f"One is an archaeologist, the other a reporter."
            )

        if r.explicit_diff > 15:
            who_explicit = r.a.user if r.a.explicit_pct > r.b.explicit_pct else r.b.user
            who_clean = r.b.user if who_explicit == r.a.user else r.a.user
            tensions.append(
                f"{who_explicit} runs rawer ({max(r.a.explicit_pct, r.b.explicit_pct):.0f}% explicit) "
                f"while {who_clean} keeps it cleaner ({min(r.a.explicit_pct, r.b.explicit_pct):.0f}%). "
                f"Different comfort zones with unfiltered expression."
            )

        if r.both_accelerating:
            alignments.append(self._v([
                (f"Both musically accelerating — their all-time favorites are dominated "
                 f"by recent discoveries ({r.a.user}: {r.a.alltime_recency:.0f}%, "
                 f"{r.b.user}: {r.b.alltime_recency:.0f}%). "
                 f"Both more alive right now than ever."),
                "Both in a phase of musical acceleration. Their heaviest-played tracks "
                "are mostly recent saves — they're both rewriting their identity in real time.",
            ], r.a.user, "accel"))

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
            top_gift = r.a_gifts[0]
            parts.append(self._v([
                (f"{r.a.user} could open these doors for {r.b.user}: {gifts}. "
                 f"{top_gift['name']} alone has {top_gift['count']} tracks — "
                 f"a deep well {r.b.user} hasn't tapped."),
                f"{r.a.user} could introduce {r.b.user} to: {gifts}.",
                (f"What {r.a.user} has that {r.b.user} doesn't: {gifts}. "
                 f"Starting with {top_gift['name']} ({top_gift['count']} tracks)."),
            ], r.a.user, "gift"))

        if r.b_gifts:
            gifts = ", ".join(g["name"] for g in r.b_gifts[:5])
            top_gift = r.b_gifts[0]
            parts.append(self._v([
                (f"{r.b.user} could open these doors for {r.a.user}: {gifts}. "
                 f"{top_gift['name']} leads with {top_gift['count']} tracks."),
                f"{r.b.user} could introduce {r.a.user} to: {gifts}.",
                (f"What {r.b.user} has that {r.a.user} doesn't: {gifts}. "
                 f"{top_gift['name']} ({top_gift['count']} tracks) is the starting point."),
            ], r.b.user, "gift"))

        if r.a_unique_decades:
            decades_str = ", ".join(sorted(r.a_unique_decades))
            parts.append(
                f"{r.a.user} has explored the {decades_str} "
                f"that {r.b.user} hasn't touched."
            )

        if r.b_unique_decades:
            decades_str = ", ".join(sorted(r.b_unique_decades))
            parts.append(
                f"{r.b.user} has explored the {decades_str} "
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
            parts.append(self._v([
                (f"They share unsaved obsessions: both play {shared} on repeat without saving. "
                 f"Their shadow selves overlap — the things they need but won't claim are the same."),
                (f"Both circle {shared} without committing. "
                 f"A shared shadow — music they both need but neither will save."),
            ], r.a.user, "shadow"))

        if r.a_unsaved_in_b_saved:
            crossover = ", ".join(list(r.a_unsaved_in_b_saved)[:3])
            parts.append(self._v([
                (f"What {r.a.user} plays but won't save, "
                 f"{r.b.user} has already claimed: {crossover}. "
                 f"{r.b.user} has integrated something {r.a.user} is still circling."),
                (f"{r.a.user} keeps playing {crossover} without saving. "
                 f"{r.b.user} saved them long ago. "
                 f"What one resists, the other has embraced."),
            ], r.a.user, "cross"))

        if r.b_unsaved_in_a_saved:
            crossover = ", ".join(list(r.b_unsaved_in_a_saved)[:3])
            parts.append(self._v([
                (f"The reverse: {r.b.user}'s unsaved obsessions include {crossover}, "
                 f"which {r.a.user} saved long ago."),
                (f"And {r.b.user} circles {crossover} without saving — "
                 f"artists {r.a.user} committed to already."),
            ], r.b.user, "cross"))

        if not parts:
            return None

        return {"type": "shadow", "title": "The shadow selves", "body": " ".join(parts)}

    def _dynamic_insight(self, r):
        a_bigger = r.a.total > r.b.total * 1.5
        b_bigger = r.b.total > r.a.total * 1.5
        a_more_diverse = r.a.unique_artists > r.b.unique_artists * 1.3
        b_more_diverse = r.b.unique_artists > r.a.unique_artists * 1.3
        size_ratio = max(r.a.total, r.b.total) / max(min(r.a.total, r.b.total), 1)

        if a_bigger and a_more_diverse:
            return {
                "type": "dynamic",
                "title": "The dynamic",
                "body": self._v([
                    (f"{r.a.user}'s library is {size_ratio:.1f}x larger and spans "
                     f"{r.a.unique_artists:,} artists to {r.b.user}'s {r.b.unique_artists:,}. "
                     f"In this relationship, {r.a.user} is probably the one always sending songs, "
                     f"making playlists, saying 'you have to hear this.' "
                     f"{r.b.user} is more selective — fewer tracks, "
                     f"potentially deeper attachment to each one."),
                    (f"{r.a.total:,} tracks vs {r.b.total:,}. "
                     f"{r.a.unique_artists:,} artists vs {r.b.unique_artists:,}. "
                     f"{r.a.user} casts a wider net — the curator, the DJ. "
                     f"{r.b.user} is more deliberate — each save carries more weight."),
                ], r.a.user, "dyn"),
            }
        elif b_bigger and b_more_diverse:
            return {
                "type": "dynamic",
                "title": "The dynamic",
                "body": self._v([
                    (f"{r.b.user}'s library is {size_ratio:.1f}x larger and spans "
                     f"{r.b.unique_artists:,} artists to {r.a.user}'s {r.a.unique_artists:,}. "
                     f"{r.b.user} is probably the curator in this relationship — "
                     f"the one always finding something new. "
                     f"{r.a.user} is more selective — each save means more."),
                    (f"{r.b.total:,} tracks vs {r.a.total:,}. "
                     f"{r.b.unique_artists:,} artists vs {r.a.unique_artists:,}. "
                     f"{r.b.user} is the one with the bigger map. "
                     f"{r.a.user} travels lighter but knows their territory deeply."),
                ], r.b.user, "dyn"),
            }
        else:
            return {
                "type": "dynamic",
                "title": "The dynamic",
                "body": self._v([
                    (f"Similar-sized libraries ({r.a.total:,} vs {r.b.total:,} tracks, "
                     f"{r.a.unique_artists:,} vs {r.b.unique_artists:,} artists). "
                     f"Neither is leading the other musically — "
                     f"parallel explorers on their own paths, "
                     f"crossing at the shared artists and diverging into their own territories."),
                    (f"{r.a.total:,} tracks meets {r.b.total:,}. "
                     f"Roughly balanced. Neither is the DJ or the passenger — "
                     f"they navigate independently and compare notes."),
                ], r.a.user, "dyn"),
            }

    def _trajectory_insight(self, r):
        parts = []

        if r.converging:
            shared = ", ".join(list(r.shared_rising)[:4])
            parts.append(self._v([
                (f"They're converging. Both currently getting into: {shared}. "
                 f"Their tastes are moving toward each other."),
                (f"Converging trajectories. Both are discovering: {shared}. "
                 f"Whatever algorithm or instinct is guiding them, "
                 f"it's pulling them to the same place."),
            ], r.a.user, "traj"))
        elif r.a.rising_artists and r.b.rising_artists:
            parts.append(self._v([
                (f"Different trajectories. "
                 f"{r.a.user} is moving toward: {', '.join(r.a.rising_artists[:3])}. "
                 f"{r.b.user} is moving toward: {', '.join(r.b.rising_artists[:3])}. "
                 f"Parallel paths — not converging, not diverging."),
                (f"{r.a.user}'s current direction: {', '.join(r.a.rising_artists[:3])}. "
                 f"{r.b.user}'s: {', '.join(r.b.rising_artists[:3])}. "
                 f"They're headed to different places from here."),
                (f"Right now {r.a.user} is discovering {', '.join(r.a.rising_artists[:3])}, "
                 f"while {r.b.user} is into {', '.join(r.b.rising_artists[:3])}. "
                 f"Different vectors — each could become the other's next recommendation."),
            ], r.a.user, "traj"))

        if r.nostalgia_trend_same and r.a.nostalgia_trend > 3:
            parts.append(self._v([
                "Both reaching further into the past each year. Fellow time travelers.",
                "Both on the same backward trajectory — digging deeper every year. "
                "They'll keep finding older music to share.",
            ], r.a.user, "nost_traj"))
        elif not r.nostalgia_trend_same and abs(r.a.nostalgia_trend - r.b.nostalgia_trend) > 5:
            who_past = r.a.user if r.a.nostalgia_trend > r.b.nostalgia_trend else r.b.user
            who_present = r.b.user if who_past == r.a.user else r.a.user
            parts.append(self._v([
                (f"{who_past} is heading deeper into the past while "
                 f"{who_present} stays closer to the present. "
                 f"Their libraries will look more different over time."),
                (f"Diverging timelines: {who_past} keeps excavating older music, "
                 f"{who_present} stays current. "
                 f"The gap between their decades will widen."),
            ], r.a.user, "nost_traj"))

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

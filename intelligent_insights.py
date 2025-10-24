"""Intelligent insight utilities for Hunt Pro.

This module analyses historical hunt logs to surface stand recommendations
and wildlife movement patterns. The implementation favours explainability and
works with small datasets while still capturing correlations between weather,
time, and observed success.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from math import exp, log
from typing import (
    Dict,
    Iterable,
    List,
    Mapping,
    MutableMapping,
    Optional,
    Sequence,
)

from game_log import (
    EntryType,
    GameEntry,
    GameSpecies,
    WeatherCondition,
    WindDirection,
)


@dataclass(frozen=True)
class StandRecommendation:
    """A scored recommendation for a hunting stand or blind."""

    location: str
    probability: float
    supporting_entries: int
    contributing_factors: Mapping[str, str]


@dataclass(frozen=True)
class MovementPrediction:
    """Predicted wildlife movement information for a species."""

    species: GameSpecies
    peak_hours: Sequence[int]
    hourly_intensity: Mapping[int, float]
    hotspot_locations: Sequence[str]


@dataclass(frozen=True)
class PerformanceBreakdown:
    """Aggregated performance statistics for a specific category."""

    label: str
    attempts: int
    successes: int
    success_rate: float


@dataclass(frozen=True)
class AfterActionReport:
    """Structured summary of a hunt session portfolio."""

    total_entries: int
    encounter_entries: int
    harvests: int
    sightings: int
    scouting_sessions: int
    harvest_success_rate: float
    top_locations: Sequence[PerformanceBreakdown]
    weather_outcomes: Sequence[PerformanceBreakdown]
    improvement_opportunities: Sequence[str]


_UNKNOWN_LOCATION_LABEL = "Unspecified Location"


class HistoricalHuntInsightModel:
    """Learn correlations from historical hunts to power insights.

    The model uses a naive Bayes style learner to estimate how well a stand's
    historical conditions match a requested context (species, weather, time).
    """

    _UNKNOWN_STAND_LABEL = "Unknown Stand"

    def __init__(self, smoothing: float = 1.0) -> None:
        if smoothing <= 0:
            raise ValueError("smoothing must be positive")
        self._smoothing = float(smoothing)
        self._location_feature_counts: MutableMapping[str, MutableMapping[str, Counter]] = (
            defaultdict(lambda: defaultdict(Counter))
        )
        self._location_totals: Counter = Counter()
        self._feature_value_catalogue: MutableMapping[str, set] = defaultdict(set)
        self._species_hour_counts: MutableMapping[GameSpecies, Counter] = defaultdict(Counter)
        self._species_location_counts: MutableMapping[GameSpecies, Counter] = defaultdict(Counter)
        self._fitted = False

    def fit(self, entries: Iterable[GameEntry]) -> None:
        """Fit the model on historical hunt entries."""

        # Reset internal state in case the model is re-fit.
        self._location_feature_counts.clear()
        self._location_totals.clear()
        self._feature_value_catalogue.clear()
        self._species_hour_counts.clear()
        self._species_location_counts.clear()

        for entry in entries:
            if not isinstance(entry, GameEntry):
                raise TypeError("entries must contain GameEntry instances")

            location_name = (entry.location.name if entry.location and entry.location.name else None)
            location = location_name or self._UNKNOWN_STAND_LABEL

            weight = self._determine_weight(entry.entry_type)
            if weight == 0:
                continue

            context_features = self._extract_context(entry)
            feature_counters = self._location_feature_counts[location]
            for feature, value in context_features.items():
                feature_counters[feature][value] += weight
                self._feature_value_catalogue[feature].add(value)
            self._location_totals[location] += weight

            hour_bucket = context_features["hour"]
            self._species_hour_counts[entry.species][hour_bucket] += weight
            self._species_location_counts[entry.species][location] += weight

        self._fitted = True

    def recommend_stands(
        self,
        *,
        species: GameSpecies,
        weather: Optional[WeatherCondition] = None,
        wind: Optional[WindDirection] = None,
        hour: Optional[int] = None,
        top_n: int = 3,
    ) -> List[StandRecommendation]:
        """Return the top ``n`` stand recommendations for the given context."""

        self._ensure_fitted()
        if top_n <= 0:
            return []

        context = {
            "species": species.value,
            "weather": (weather or WeatherCondition.CLEAR).value,
            "wind": (wind or WindDirection.CALM).value,
            "hour": int(hour if hour is not None else 6),
        }

        log_scores: Dict[str, float] = {}
        for location, totals in self._location_totals.items():
            log_prior = log(totals + self._smoothing)
            log_likelihood = 0.0
            feature_counters = self._location_feature_counts[location]
            for feature, target_value in context.items():
                counter = feature_counters.get(feature)
                if not counter:
                    continue
                total_for_feature = sum(counter.values())
                possible_values = max(len(self._feature_value_catalogue[feature]), 1)
                observed = counter.get(target_value, 0.0)
                likelihood = (observed + self._smoothing) / (
                    total_for_feature + self._smoothing * possible_values
                )
                log_likelihood += log(likelihood)
            log_scores[location] = log_prior + log_likelihood

        if not log_scores:
            return []

        max_log_score = max(log_scores.values())
        exp_scores: Dict[str, float] = {
            location: exp(score - max_log_score) for location, score in log_scores.items()
        }
        normaliser = sum(exp_scores.values()) or 1.0

        recommendations: List[StandRecommendation] = []
        for location, raw_score in exp_scores.items():
            probability = raw_score / normaliser
            contributing_factors = self._summarise_factors(location, context)
            recommendations.append(
                StandRecommendation(
                    location=location,
                    probability=probability,
                    supporting_entries=int(round(self._location_totals[location])),
                    contributing_factors=contributing_factors,
                )
            )

        recommendations.sort(key=lambda rec: rec.probability, reverse=True)
        return recommendations[:top_n]

    def predict_movement_patterns(
        self,
        species: GameSpecies,
        *,
        top_hours: int = 3,
        top_locations: int = 3,
    ) -> MovementPrediction:
        """Predict key movement patterns for ``species``."""

        self._ensure_fitted()
        hour_counts = self._species_hour_counts.get(species, Counter())
        location_counts = self._species_location_counts.get(species, Counter())

        total_activity = sum(hour_counts.values()) or 1.0
        hourly_intensity = {
            hour: count / total_activity for hour, count in sorted(hour_counts.items())
        }

        peak_hours = [hour for hour, _ in hour_counts.most_common(top_hours)]
        hotspot_locations = [
            location for location, _ in location_counts.most_common(top_locations)
        ]

        return MovementPrediction(
            species=species,
            peak_hours=peak_hours,
            hourly_intensity=hourly_intensity,
            hotspot_locations=hotspot_locations,
        )

    def _ensure_fitted(self) -> None:
        if not self._fitted:
            raise RuntimeError("The model must be fit before generating insights.")

    @staticmethod
    def _determine_weight(entry_type: EntryType) -> float:
        weights: Mapping[EntryType, float] = {
            EntryType.HARVEST: 3.0,
            EntryType.SIGHTING: 2.0,
            EntryType.TRACK: 1.2,
            EntryType.SCOUT: 1.0,
            EntryType.SETUP: 0.5,
            EntryType.WEATHER: 0.0,
        }
        return weights.get(entry_type, 1.0)

    @staticmethod
    def _extract_context(entry: GameEntry) -> Dict[str, str]:
        timestamp = entry.datetime_obj
        hour_bucket = timestamp.hour
        weather_condition = (
            entry.weather.condition.value if entry.weather else WeatherCondition.CLEAR.value
        )
        wind_direction = (
            entry.weather.wind_direction.value
            if entry.weather
            else WindDirection.CALM.value
        )
        return {
            "species": entry.species.value,
            "weather": weather_condition,
            "wind": wind_direction,
            "hour": hour_bucket,
        }

    def _summarise_factors(
        self, location: str, context: Mapping[str, str]
    ) -> Dict[str, str]:
        summaries: Dict[str, str] = {}
        feature_counters = self._location_feature_counts.get(location, {})
        for feature, target_value in context.items():
            counter = feature_counters.get(feature)
            if not counter:
                continue
            total = sum(counter.values())
            if total == 0:
                continue
            match_ratio = counter.get(target_value, 0.0) / total
            if match_ratio > 0:
                summaries[feature] = f"{match_ratio:.0%} historical match for {target_value}"
        return summaries


def generate_after_action_report(entries: Sequence[GameEntry]) -> AfterActionReport:
    """Build a structured after-action report from historical entries."""

    history = list(entries)
    for entry in history:
        if not isinstance(entry, GameEntry):
            raise TypeError("entries must contain GameEntry instances")

    total_entries = len(history)
    encounter_types = {EntryType.SIGHTING, EntryType.HARVEST, EntryType.TRACK}
    encounter_entries = [entry for entry in history if entry.entry_type in encounter_types]
    encounter_count = len(encounter_entries)

    harvests = sum(1 for entry in history if entry.entry_type == EntryType.HARVEST)
    sightings = sum(1 for entry in history if entry.entry_type == EntryType.SIGHTING)
    scouting_sessions = sum(1 for entry in history if entry.entry_type == EntryType.SCOUT)

    location_attempts: MutableMapping[str, int] = defaultdict(int)
    location_successes: MutableMapping[str, int] = defaultdict(int)
    weather_attempts: MutableMapping[str, int] = defaultdict(int)
    weather_successes: MutableMapping[str, int] = defaultdict(int)

    for entry in encounter_entries:
        location_label = _normalise_location_label(entry)
        location_attempts[location_label] += 1
        if entry.entry_type == EntryType.HARVEST:
            location_successes[location_label] += 1

        weather_label = (
            entry.weather.condition.value if entry.weather else WeatherCondition.CLEAR.value
        )
        weather_attempts[weather_label] += 1
        if entry.entry_type == EntryType.HARVEST:
            weather_successes[weather_label] += 1

    top_locations = _build_breakdowns(location_attempts, location_successes)
    weather_outcomes = _build_breakdowns(weather_attempts, weather_successes)

    harvest_success_rate = (
        harvests / encounter_count if encounter_count > 0 else 0.0
    )

    improvement_opportunities = _identify_improvements(
        total_entries=total_entries,
        encounter_count=encounter_count,
        harvest_success_rate=harvest_success_rate,
        harvests=harvests,
        scouting_sessions=scouting_sessions,
        location_breakdowns=top_locations,
        weather_breakdowns=weather_outcomes,
    )

    return AfterActionReport(
        total_entries=total_entries,
        encounter_entries=encounter_count,
        harvests=harvests,
        sightings=sightings,
        scouting_sessions=scouting_sessions,
        harvest_success_rate=harvest_success_rate,
        top_locations=top_locations,
        weather_outcomes=weather_outcomes,
        improvement_opportunities=improvement_opportunities,
    )


def _build_breakdowns(
    attempts: Mapping[str, int], successes: Mapping[str, int]
) -> List[PerformanceBreakdown]:
    breakdowns: List[PerformanceBreakdown] = []
    for label, attempts_count in attempts.items():
        success_count = successes.get(label, 0)
        success_rate = success_count / attempts_count if attempts_count else 0.0
        breakdowns.append(
            PerformanceBreakdown(
                label=label,
                attempts=attempts_count,
                successes=success_count,
                success_rate=success_rate,
            )
        )

    breakdowns.sort(
        key=lambda breakdown: (
            -breakdown.success_rate,
            -breakdown.successes,
            -breakdown.attempts,
            breakdown.label,
        )
    )
    return breakdowns


def _normalise_location_label(entry: GameEntry) -> str:
    if entry.location:
        if entry.location.name and entry.location.name.strip():
            return entry.location.name.strip()
        if entry.location.description and entry.location.description.strip():
            return entry.location.description.strip()
    return _UNKNOWN_LOCATION_LABEL


def _identify_improvements(
    *,
    total_entries: int,
    encounter_count: int,
    harvest_success_rate: float,
    harvests: int,
    scouting_sessions: int,
    location_breakdowns: Sequence[PerformanceBreakdown],
    weather_breakdowns: Sequence[PerformanceBreakdown],
) -> List[str]:
    improvements: List[str] = []

    def _add(message: str) -> None:
        if message and message not in improvements:
            improvements.append(message)

    if total_entries == 0:
        _add(
            "No hunt entries were logged; capture sightings, tracks, or harvests to generate after-action insights."
        )
    else:
        if encounter_count == 0:
            _add(
                "No encounter entries were logged; record sightings, tracks, or harvests to unlock actionable insights."
            )
        else:
            if harvest_success_rate < 0.3:
                percentage = f"{harvest_success_rate:.0%}"
                _add(
                    f"Harvest success rate was {percentage} across {encounter_count} encounters; evaluate stand setups and follow-up on high-activity zones."
                )

            for breakdown in location_breakdowns:
                if breakdown.attempts >= 2 and breakdown.success_rate < 0.2:
                    _add(
                        f"{breakdown.label} recorded {breakdown.attempts} encounters but only {breakdown.successes} harvests; consider repositioning or limiting time spent there."
                    )
                if len(improvements) >= 3:
                    break

            for weather in weather_breakdowns:
                if weather.attempts >= 3 and weather.success_rate < 0.2:
                    percentage = f"{weather.success_rate:.0%}"
                    _add(
                        f"Hunts during {weather.label.lower()} conditions yielded {percentage} success across {weather.attempts} encounters; adjust tactics or scheduling for that weather pattern."
                    )
                    break

    if total_entries > 0:
        if scouting_sessions == 0:
            _add(
                "No scouting sessions were logged; schedule dedicated reconnaissance to refresh movement intelligence."
            )
        elif (scouting_sessions / total_entries) < 0.15:
            _add(
                f"Only {scouting_sessions} of {total_entries} entries were scouting sessions; increase reconnaissance to broaden future opportunities."
            )

    if not improvements:
        _add(
            "Strong performance across recorded hunts; continue reinforcing successful tactics."
        )

    return improvements[:4]

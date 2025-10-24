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
from typing import Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence

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

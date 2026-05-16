"""
Tests for the normalizer module.

Covers:
- American odds → implied probability conversion (both signs)
- Full event normalization from a realistic API payload
- Edge cases: no bookmakers, no h2h market
"""

import pytest
from phase_1_discovery.normalizer.normalizer import (
    american_to_implied_prob,
    normalize_events,
    NormalizedEvent,
)


# ── american_to_implied_prob ─────────────────────────────────────────────────

class TestAmericanToImpliedProb:
    def test_negative_odds_favourite(self):
        # -110 means you risk 110 to win 100
        result = american_to_implied_prob(-110)
        assert abs(result - 0.5238) < 0.0001

    def test_positive_odds_underdog(self):
        # +110 means you risk 100 to win 110
        result = american_to_implied_prob(110)
        assert abs(result - 0.4762) < 0.0001

    def test_even_money(self):
        result = american_to_implied_prob(100)
        assert abs(result - 0.5) < 0.0001

    def test_heavy_favourite(self):
        result = american_to_implied_prob(-300)
        assert abs(result - 0.75) < 0.0001

    def test_big_underdog(self):
        result = american_to_implied_prob(300)
        assert abs(result - 0.25) < 0.0001

    def test_result_is_between_zero_and_one(self):
        for odds in [-500, -200, -110, 100, 150, 300, 1000]:
            result = american_to_implied_prob(odds)
            assert 0 < result < 1, f"Failed for odds={odds}: got {result}"


# ── normalize_events ─────────────────────────────────────────────────────────

SAMPLE_RAW_RESPONSE = [
    {
        "id": "event_abc123",
        "home_team": "Los Angeles Lakers",
        "away_team": "Boston Celtics",
        "commence_time": "2026-05-20T01:00:00Z",
        "bookmakers": [
            {
                "key": "draftkings",
                "markets": [
                    {
                        "key": "h2h",
                        "outcomes": [
                            {"name": "Los Angeles Lakers", "price": -110},
                            {"name": "Boston Celtics", "price": -110},
                        ],
                    }
                ],
            },
            {
                "key": "fanduel",
                "markets": [
                    {
                        "key": "h2h",
                        "outcomes": [
                            {"name": "Los Angeles Lakers", "price": 105},
                            {"name": "Boston Celtics", "price": -125},
                        ],
                    }
                ],
            },
        ],
    }
]


class TestNormalizeEvents:
    def test_returns_list_of_normalized_events(self):
        result = normalize_events(SAMPLE_RAW_RESPONSE)
        assert len(result) == 1
        assert isinstance(result[0], NormalizedEvent)

    def test_event_metadata_is_correct(self):
        event = normalize_events(SAMPLE_RAW_RESPONSE)[0]
        assert event.event_id == "event_abc123"
        assert event.home_team == "Los Angeles Lakers"
        assert event.away_team == "Boston Celtics"

    def test_both_outcomes_present(self):
        event = normalize_events(SAMPLE_RAW_RESPONSE)[0]
        assert "Los Angeles Lakers" in event.outcomes
        assert "Boston Celtics" in event.outcomes

    def test_both_books_present_for_each_outcome(self):
        event = normalize_events(SAMPLE_RAW_RESPONSE)[0]
        lakers_books = {o.book for o in event.outcomes["Los Angeles Lakers"]}
        assert "draftkings" in lakers_books
        assert "fanduel" in lakers_books

    def test_implied_probs_are_correct(self):
        event = normalize_events(SAMPLE_RAW_RESPONSE)[0]
        # DraftKings -110 → ~0.5238
        dk_lakers = next(o for o in event.outcomes["Los Angeles Lakers"] if o.book == "draftkings")
        assert abs(dk_lakers.implied_prob - 0.5238) < 0.0001

    def test_non_h2h_markets_are_ignored(self):
        raw = [
            {
                "id": "event_xyz",
                "home_team": "Team A",
                "away_team": "Team B",
                "commence_time": "2026-05-20T01:00:00Z",
                "bookmakers": [
                    {
                        "key": "betmgm",
                        "markets": [
                            {"key": "spreads", "outcomes": [{"name": "Team A", "price": -110}]},
                        ],
                    }
                ],
            }
        ]
        event = normalize_events(raw)[0]
        assert event.outcomes == {}

    def test_empty_bookmakers_returns_event_with_no_outcomes(self):
        raw = [{"id": "x", "home_team": "A", "away_team": "B", "commence_time": "2026-05-20T01:00:00Z", "bookmakers": []}]
        event = normalize_events(raw)[0]
        assert event.outcomes == {}

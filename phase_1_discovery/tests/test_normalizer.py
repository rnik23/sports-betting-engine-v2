"""
Tests for the normalizer module.

Covers:
- American odds → implied probability conversion (both signs)
- Full event normalization from a realistic OddsPapi /v4/odds payload
- Edge cases: no bookmakerOdds, inactive bookmaker, suspended market, non-mainLine markets
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
        result = american_to_implied_prob(-110)
        assert abs(result - 0.5238) < 0.0001

    def test_positive_odds_underdog(self):
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


# ── helpers ──────────────────────────────────────────────────────────────────

def make_player(price_american: str, main_line: bool = True) -> dict:
    return {
        "active": True,
        "mainLine": main_line,
        "priceAmerican": price_american,
        "price": None,
        "priceFractional": None,
        "limit": None,
        "playerName": None,
    }


def make_fixture(
    fixture_id="event_abc123",
    p1="Los Angeles Lakers",
    p2="Boston Celtics",
    bookmaker_odds=None,
) -> dict:
    """Build a minimal OddsPapi /v4/odds fixture response."""
    return {
        "fixtureId": fixture_id,
        "participant1Name": p1,
        "participant2Name": p2,
        "startTime": "2026-05-20T01:00:00.000Z",
        "bookmakerOdds": bookmaker_odds or {},
    }


def make_h2h_bookmaker(p1_price: str, p2_price: str, active: bool = True, suspended: bool = False) -> dict:
    """Build a bookmaker entry with a single h2h mainLine market."""
    return {
        "bookmakerIsActive": active,
        "suspended": suspended,
        "markets": {
            "111": {
                "marketActive": True,
                "outcomes": {
                    "111": {"players": {"0": make_player(p1_price)}},
                    "112": {"players": {"0": make_player(p2_price)}},
                },
            }
        },
    }


# Sample fixture matching the real OddsPapi response shape
SAMPLE_RAW_RESPONSE = [
    make_fixture(
        bookmaker_odds={
            "draftkings": make_h2h_bookmaker("-110", "-110"),
            "fanduel":    make_h2h_bookmaker("105",  "-125"),
        }
    )
]


# ── normalize_events ─────────────────────────────────────────────────────────

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

    def test_non_mainline_markets_are_ignored(self):
        """A bookmaker with no mainLine=True outcomes produces no outcomes."""
        raw = [make_fixture(
            fixture_id="event_xyz",
            p1="Team A", p2="Team B",
            bookmaker_odds={
                "betmgm": {
                    "bookmakerIsActive": True,
                    "suspended": False,
                    "markets": {
                        "999": {
                            "marketActive": True,
                            "outcomes": {
                                "999": {"players": {"0": make_player("-110", main_line=False)}},
                            },
                        }
                    },
                }
            },
        )]
        event = normalize_events(raw)[0]
        assert event.outcomes == {}

    def test_empty_bookmaker_odds_returns_event_with_no_outcomes(self):
        raw = [make_fixture(bookmaker_odds={})]
        event = normalize_events(raw)[0]
        assert event.outcomes == {}

    def test_inactive_bookmaker_is_skipped(self):
        raw = [make_fixture(
            bookmaker_odds={
                "betmgm": make_h2h_bookmaker("-110", "-110", active=False),
            }
        )]
        event = normalize_events(raw)[0]
        assert event.outcomes == {}

    def test_suspended_bookmaker_is_skipped(self):
        raw = [make_fixture(
            bookmaker_odds={
                "betmgm": make_h2h_bookmaker("-110", "-110", suspended=True),
            }
        )]
        event = normalize_events(raw)[0]
        assert event.outcomes == {}

"""
Tests for the detector module.

Covers:
- True arb detected when sum of best implied probs < 1.0
- No arb when books agree (no spread)
- Correct book is selected for each side (lowest implied prob = best odds)
- Margin calculation accuracy
- Edge cases: single-outcome events, min_margin_pct filter
"""

import pytest
from phase_1_discovery.normalizer.normalizer import NormalizedEvent, Outcome
from phase_1_discovery.detector.detector import (
    find_arb_opportunities,
    find_best_outcome,
    ArbOpportunity,
)


def make_event(event_id, home, away, outcomes_by_name) -> NormalizedEvent:
    """Helper to build a NormalizedEvent with minimal boilerplate."""
    event = NormalizedEvent(
        event_id=event_id,
        home_team=home,
        away_team=away,
        commence_time="2026-05-20T01:00:00Z",
    )
    event.outcomes = outcomes_by_name
    return event


# ── find_best_outcome ────────────────────────────────────────────────────────

class TestFindBestOutcome:
    def test_returns_outcome_with_lowest_implied_prob(self):
        outcomes = [
            Outcome("Lakers", "draftkings", 0.526),
            Outcome("Lakers", "fanduel", 0.488),   # best — lowest prob = highest odds
            Outcome("Lakers", "betmgm", 0.510),
        ]
        best = find_best_outcome(outcomes)
        assert best.book == "fanduel"

    def test_single_outcome_returns_it(self):
        outcomes = [Outcome("Lakers", "draftkings", 0.526)]
        assert find_best_outcome(outcomes).book == "draftkings"


# ── find_arb_opportunities ───────────────────────────────────────────────────

class TestFindArbOpportunities:
    def test_detects_clear_arb(self):
        """
        Lakers at +110 (prob 0.476) on DraftKings
        Celtics at +110 (prob 0.476) on FanDuel
        Sum = 0.952 → 4.8% margin — obvious arb
        """
        event = make_event("e1", "Los Angeles Lakers", "Boston Celtics", {
            "Los Angeles Lakers": [Outcome("Los Angeles Lakers", "draftkings", 0.476)],
            "Boston Celtics":     [Outcome("Boston Celtics", "fanduel", 0.476)],
        })
        opps = find_arb_opportunities([event])
        assert len(opps) == 1
        assert opps[0].margin_pct > 0

    def test_no_arb_when_books_are_equal(self):
        """
        Both sides -110 at same book → sum = 1.048 → no arb (vig in the book's favour)
        """
        event = make_event("e2", "Team A", "Team B", {
            "Team A": [Outcome("Team A", "draftkings", 0.5238)],
            "Team B": [Outcome("Team B", "draftkings", 0.5238)],
        })
        opps = find_arb_opportunities([event])
        assert opps == []

    def test_picks_best_book_per_side(self):
        """
        Lakers: DraftKings 0.526, FanDuel 0.490 → should pick FanDuel
        Celtics: DraftKings 0.526, BetMGM 0.460 → should pick BetMGM
        """
        event = make_event("e3", "Los Angeles Lakers", "Boston Celtics", {
            "Los Angeles Lakers": [
                Outcome("Los Angeles Lakers", "draftkings", 0.526),
                Outcome("Los Angeles Lakers", "fanduel", 0.490),
            ],
            "Boston Celtics": [
                Outcome("Boston Celtics", "draftkings", 0.526),
                Outcome("Boston Celtics", "betmgm", 0.460),
            ],
        })
        opps = find_arb_opportunities([event])
        assert len(opps) == 1
        assert opps[0].best_outcomes["Los Angeles Lakers"].book == "fanduel"
        assert opps[0].best_outcomes["Boston Celtics"].book == "betmgm"

    def test_margin_calculation_is_correct(self):
        """0.476 + 0.476 = 0.952 → margin = 4.8%"""
        event = make_event("e4", "A", "B", {
            "A": [Outcome("A", "book1", 0.476)],
            "B": [Outcome("B", "book2", 0.476)],
        })
        opps = find_arb_opportunities([event])
        assert abs(opps[0].margin_pct - 4.8) < 0.01

    def test_single_outcome_event_is_skipped(self):
        """Can't arb a one-sided market."""
        event = make_event("e5", "A", "B", {
            "A": [Outcome("A", "book1", 0.476)],
        })
        opps = find_arb_opportunities([event])
        assert opps == []

    def test_min_margin_filter(self):
        """Only return opportunities above the threshold."""
        event = make_event("e6", "A", "B", {
            "A": [Outcome("A", "book1", 0.490)],
            "B": [Outcome("B", "book2", 0.490)],
        })
        # Sum = 0.98 → margin = 2.0%
        assert len(find_arb_opportunities([event], min_margin_pct=1.0)) == 1
        assert len(find_arb_opportunities([event], min_margin_pct=3.0)) == 0

    def test_returns_empty_list_for_no_events(self):
        assert find_arb_opportunities([]) == []

    def test_multiple_events_multiple_arbs(self):
        events = [
            make_event("e7", "A", "B", {
                "A": [Outcome("A", "b1", 0.476)],
                "B": [Outcome("B", "b2", 0.476)],
            }),
            make_event("e8", "C", "D", {
                "C": [Outcome("C", "b1", 0.476)],
                "D": [Outcome("D", "b2", 0.476)],
            }),
        ]
        opps = find_arb_opportunities(events)
        assert len(opps) == 2

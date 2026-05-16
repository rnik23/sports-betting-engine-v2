"""
Detector — identifies arbitrage opportunities from normalized event data.

An arbitrage opportunity exists when the sum of the best implied
probabilities across all outcomes for a single event is less than 1.0.

Example (two-outcome moneyline):
  Lakers best implied prob:  0.476  (DraftKings, +110)
  Celtics best implied prob: 0.510  (FanDuel, -104)
  Sum = 0.986 → arb margin = 1.4%

The margin is the guaranteed profit percentage regardless of outcome.
"""

from dataclasses import dataclass
from phase_1_discovery.normalizer.normalizer import NormalizedEvent, Outcome


@dataclass
class ArbOpportunity:
    event_id: str
    home_team: str
    away_team: str
    commence_time: str
    # Best outcome per side: outcome_name → Outcome
    best_outcomes: dict[str, Outcome]
    # Sum of implied probs across best outcomes (< 1.0 = arb)
    implied_prob_sum: float
    # Guaranteed profit margin as a percentage
    margin_pct: float


def find_best_outcome(outcomes: list[Outcome]) -> Outcome:
    """
    Return the outcome with the lowest implied probability (i.e. highest odds).
    Lower implied prob = better payout = the book we want to bet with.
    """
    return min(outcomes, key=lambda o: o.implied_prob)


def find_arb_opportunities(
    events: list[NormalizedEvent],
    min_margin_pct: float = 0.0,
) -> list[ArbOpportunity]:
    """
    Scan normalized events for arbitrage opportunities.

    For each event, find the best available odds for each outcome across
    all books. If the sum of best implied probabilities is < 1.0, it's an arb.

    min_margin_pct: only return opportunities above this threshold.
    Set to 0 during POC to capture everything, including marginal cases.
    """
    opportunities = []

    for event in events:
        if len(event.outcomes) < 2:
            # Need at least two sides to have an arb
            continue

        best_per_outcome = {
            name: find_best_outcome(outcome_list)
            for name, outcome_list in event.outcomes.items()
        }

        total_prob = sum(o.implied_prob for o in best_per_outcome.values())
        margin_pct = (1 - total_prob) * 100

        if total_prob < 1.0 and margin_pct >= min_margin_pct:
            opportunities.append(
                ArbOpportunity(
                    event_id=event.event_id,
                    home_team=event.home_team,
                    away_team=event.away_team,
                    commence_time=event.commence_time,
                    best_outcomes=best_per_outcome,
                    implied_prob_sum=round(total_prob, 6),
                    margin_pct=round(margin_pct, 4),
                )
            )

    return opportunities

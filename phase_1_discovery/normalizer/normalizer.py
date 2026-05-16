"""
Normalizer — converts raw OddsPapi /v4/odds responses to a clean internal format.

All odds are converted to implied probability so the detector can work
with a single consistent representation regardless of source format.

OddsPapi response shape (per fixture):
  {
    "fixtureId": "id1100013270505004",
    "participant1Name": "Detroit Pistons",   ← home team
    "participant2Name": "Cleveland Cavaliers", ← away team
    "startTime": "2026-05-18T00:00:00.000Z",
    "bookmakerOdds": {
      "draftkings": {
        "bookmakerIsActive": true,
        "suspended": false,
        "markets": {
          "111": {                            ← h2h moneyline market
            "marketActive": true,
            "outcomes": {
              "111": {"players": {"0": {"priceAmerican": "-182", "mainLine": true, ...}}},
              "112": {"players": {"0": {"priceAmerican": "150",  "mainLine": true, ...}}}
            }
          },
          ...                                ← other markets (spreads, totals) — ignored
        }
      }
    }
  }

Market identification: the h2h moneyline is the market that contains
outcomes with mainLine=True. Outcome IDs are sorted numerically; the
lower ID maps to participant1 (home) and the higher to participant2 (away).

Implied probability formula:
  American odds > 0:  1 / ((odds / 100) + 1)
  American odds < 0:  abs(odds) / (abs(odds) + 100)
"""

from dataclasses import dataclass, field


@dataclass
class Outcome:
    name: str           # e.g. "Detroit Pistons"
    book: str           # e.g. "draftkings"
    implied_prob: float # e.g. 0.654


@dataclass
class NormalizedEvent:
    event_id: str
    home_team: str
    away_team: str
    commence_time: str
    # Keyed by team name → list of outcomes across all books
    outcomes: dict[str, list[Outcome]] = field(default_factory=dict)


def american_to_implied_prob(odds: int) -> float:
    """
    Convert American odds to implied probability.

    >>> american_to_implied_prob(-110)
    0.5238095238095238
    >>> american_to_implied_prob(100)
    0.5
    >>> american_to_implied_prob(200)
    0.3333333333333333
    """
    if odds > 0:
        return 1 / ((odds / 100) + 1)
    else:
        return abs(odds) / (abs(odds) + 100)


def _find_h2h_market(markets: dict) -> dict | None:
    """
    Return the h2h moneyline market from a bookmaker's markets dict.

    Identified by the presence of outcomes with mainLine=True. This is
    the primary two-outcome market (home win / away win) that OddsPapi
    consistently exposes for all basketball fixtures.
    """
    for market in markets.values():
        for outcome in market.get("outcomes", {}).values():
            for player in outcome.get("players", {}).values():
                if player.get("mainLine"):
                    return market
    return None


def normalize_events(raw_response: list[dict]) -> list[NormalizedEvent]:
    """
    Parse a list of raw OddsPapi /v4/odds fixture responses into NormalizedEvent objects.

    Each fixture dict contains bookmakerOdds keyed by bookmaker name.
    We extract the h2h moneyline market per bookmaker and convert prices
    to implied probability.
    """
    events = []

    for raw_fixture in raw_response:
        event = NormalizedEvent(
            event_id=raw_fixture["fixtureId"],
            home_team=raw_fixture["participant1Name"],
            away_team=raw_fixture["participant2Name"],
            commence_time=raw_fixture["startTime"],
        )

        teams = [raw_fixture["participant1Name"], raw_fixture["participant2Name"]]

        for book_key, book_data in raw_fixture.get("bookmakerOdds", {}).items():
            if not book_data.get("bookmakerIsActive") or book_data.get("suspended"):
                continue

            h2h = _find_h2h_market(book_data.get("markets", {}))
            if not h2h or not h2h.get("marketActive"):
                continue

            # Sort outcome IDs numerically: lower = participant1 (home), higher = participant2 (away)
            outcome_ids = sorted(h2h["outcomes"].keys(), key=lambda x: int(x))

            for outcome_id, team_name in zip(outcome_ids, teams):
                for player in h2h["outcomes"][outcome_id].get("players", {}).values():
                    if not player.get("active"):
                        continue
                    price_str = player.get("priceAmerican")
                    if price_str is None:
                        continue
                    try:
                        price = int(price_str)
                    except (ValueError, TypeError):
                        continue
                    implied_prob = american_to_implied_prob(price)
                    event.outcomes.setdefault(team_name, []).append(
                        Outcome(name=team_name, book=book_key, implied_prob=implied_prob)
                    )

        events.append(event)

    return events

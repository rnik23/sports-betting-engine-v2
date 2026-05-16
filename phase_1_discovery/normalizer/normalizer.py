"""
Normalizer — converts raw OddsPapi responses to a clean internal format.

All odds are converted to implied probability so the detector can work
with a single consistent representation regardless of source format.

Implied probability formula:
  American odds > 0:  1 / ((odds / 100) + 1)
  American odds < 0:  abs(odds) / (abs(odds) + 100)
"""

from dataclasses import dataclass, field


@dataclass
class Outcome:
    name: str           # e.g. "Los Angeles Lakers"
    book: str           # e.g. "draftkings"
    implied_prob: float # e.g. 0.526


@dataclass
class NormalizedEvent:
    event_id: str
    home_team: str
    away_team: str
    commence_time: str
    # Keyed by outcome name → list of outcomes across all books
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


def normalize_events(raw_response: list[dict]) -> list[NormalizedEvent]:
    """
    Parse a raw OddsPapi response into NormalizedEvent objects.

    Each event contains multiple bookmakers, each with one or more markets.
    We extract h2h (moneyline) outcomes and convert to implied probability.
    """
    events = []

    for raw_event in raw_response:
        event = NormalizedEvent(
            event_id=raw_event["id"],
            home_team=raw_event["home_team"],
            away_team=raw_event["away_team"],
            commence_time=raw_event["commence_time"],
        )

        for bookmaker in raw_event.get("bookmakers", []):
            book_key = bookmaker["key"]
            for market in bookmaker.get("markets", []):
                if market["key"] != "h2h":
                    continue
                for outcome in market.get("outcomes", []):
                    name = outcome["name"]
                    price = outcome["price"]
                    implied_prob = american_to_implied_prob(price)
                    event.outcomes.setdefault(name, []).append(
                        Outcome(name=name, book=book_key, implied_prob=implied_prob)
                    )

        events.append(event)

    return events

"""
Lines logger — appends every book's price for every poll snapshot to CSV.

Unlike the arb logger (which only writes when an opportunity is detected),
this writes ALL lines every cycle. This is the primary research artifact
for post-game analysis:

  - Arb frequency:   group by snapshot_at, compute implied_prob_sum per
                     snapshot, count rows where sum < 1.0
  - Arb persistence: find consecutive snapshots where sum < 1.0,
                     measure duration between first and last in each run

Schema (one row per snapshot × team × book):
  snapshot_at    ISO timestamp of this poll cycle
  snapshot_num   sequential poll number (1, 2, 3, ...)
  fixture_id     OddsPapi fixture ID
  home_team      participant1Name
  away_team      participant2Name
  team_name      which side this line is for
  book           bookmaker slug (e.g. "draftkings")
  price_american American odds string (e.g. "-182", "150")
  implied_prob   converted implied probability
"""

import csv
from datetime import datetime, timezone
from pathlib import Path

from phase_1_discovery.normalizer.normalizer import NormalizedEvent

DATA_DIR = Path("data")
LINES_FILE = DATA_DIR / "lines.csv"

FIELDNAMES = [
    "snapshot_at",
    "snapshot_num",
    "fixture_id",
    "home_team",
    "away_team",
    "team_name",
    "book",
    "price_american",
    "implied_prob",
]


def _ensure_file() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    if not LINES_FILE.exists():
        with open(LINES_FILE, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            writer.writeheader()


def log_lines(events: list[NormalizedEvent], snapshot_num: int, raw_fixture: dict) -> None:
    """
    Append all lines from this snapshot to lines.csv.

    raw_fixture is the original /v4/odds response dict — used to pull
    price_american directly since NormalizedEvent only stores implied_prob.
    """
    _ensure_file()

    now = datetime.now(timezone.utc).isoformat()
    fixture_id = raw_fixture.get("fixtureId", "")
    home_team = raw_fixture.get("participant1Name", "")
    away_team = raw_fixture.get("participant2Name", "")

    # Build a price lookup: team_name → book → price_american
    price_lookup: dict[str, dict[str, str]] = {}
    teams = [home_team, away_team]

    for book_key, book_data in raw_fixture.get("bookmakerOdds", {}).items():
        if not book_data.get("bookmakerIsActive") or book_data.get("suspended"):
            continue
        h2h = book_data.get("markets", {}).get("111")
        if not h2h or not h2h.get("marketActive"):
            continue
        outcome_ids = sorted(h2h["outcomes"].keys(), key=lambda x: int(x))
        for outcome_id, team_name in zip(outcome_ids, teams):
            for player in h2h["outcomes"][outcome_id].get("players", {}).values():
                if player.get("active") and player.get("priceAmerican") is not None:
                    price_lookup.setdefault(team_name, {})[book_key] = player["priceAmerican"]

    rows = []
    for event in events:
        for team_name, outcomes in event.outcomes.items():
            for outcome in outcomes:
                rows.append({
                    "snapshot_at": now,
                    "snapshot_num": snapshot_num,
                    "fixture_id": fixture_id,
                    "home_team": home_team,
                    "away_team": away_team,
                    "team_name": team_name,
                    "book": outcome.book,
                    "price_american": price_lookup.get(team_name, {}).get(outcome.book, ""),
                    "implied_prob": round(outcome.implied_prob, 6),
                })

    if rows:
        with open(LINES_FILE, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            writer.writerows(rows)

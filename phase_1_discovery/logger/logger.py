"""
Logger — persists detected arbitrage opportunities to CSV.

Each row captures:
  - When the opportunity was detected
  - Which event it was on
  - Which books to use for each side
  - The margin (guaranteed profit %)

The CSV is our primary research artifact for Phase 1 analysis:
  - Frequency: how many rows per hour / session
  - Duration: compare timestamps between first and last appearance of same event_id
  - Book pairs: which books appear most often in best_outcomes
"""

import csv
import os
from datetime import datetime, timezone
from pathlib import Path

from phase_1_discovery.detector.detector import ArbOpportunity

DATA_DIR = Path("data")
OUTPUT_FILE = DATA_DIR / "opportunities.csv"

FIELDNAMES = [
    "detected_at",
    "event_id",
    "home_team",
    "away_team",
    "commence_time",
    "implied_prob_sum",
    "margin_pct",
    "outcome_books",   # JSON-style string: {"Lakers": "draftkings", "Celtics": "fanduel"}
]


def _ensure_output_file() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    if not OUTPUT_FILE.exists():
        with open(OUTPUT_FILE, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            writer.writeheader()


def log_opportunities(opportunities: list[ArbOpportunity]) -> None:
    """Append detected opportunities to the CSV store."""
    _ensure_output_file()

    with open(OUTPUT_FILE, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        now = datetime.now(timezone.utc).isoformat()

        for opp in opportunities:
            outcome_books = {
                name: outcome.book
                for name, outcome in opp.best_outcomes.items()
            }
            writer.writerow({
                "detected_at": now,
                "event_id": opp.event_id,
                "home_team": opp.home_team,
                "away_team": opp.away_team,
                "commence_time": opp.commence_time,
                "implied_prob_sum": opp.implied_prob_sum,
                "margin_pct": opp.margin_pct,
                "outcome_books": str(outcome_books),
            })

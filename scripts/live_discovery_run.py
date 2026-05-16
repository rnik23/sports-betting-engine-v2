"""
Live discovery run — polls a single NBA game every 60 seconds and logs
all bookmaker lines to data/lines.csv for post-game analysis.

Target: Detroit Pistons vs Cleveland Cavaliers
        2026-05-18  8:00 PM ET  (fixtureId: id1100013270505004)

Stops after MAX_DURATION_HOURS or when request quota is exhausted.

Answers after the game:
  - How frequently do true arb opportunities appear (implied_prob_sum < 1.0)?
  - What is the median time an arb window persists before lines move to close it?

Usage:
    source venv/bin/activate
    python scripts/live_discovery_run.py
"""

import sys
import time
import logging
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from phase_1_discovery.poller.client import OddsAPIClient, QuotaWarning
from phase_1_discovery.normalizer.normalizer import normalize_events
from phase_1_discovery.detector.detector import find_arb_opportunities
from phase_1_discovery.logger.logger import log_opportunities
from phase_1_discovery.logger.lines_logger import log_lines

# ── Config ───────────────────────────────────────────────────────────────────

FIXTURE_ID = "id1100013270505004"   # Pistons vs Cavaliers, 2026-05-18
HOME_TEAM = "Detroit Pistons"
AWAY_TEAM = "Cleveland Cavaliers"

POLL_INTERVAL_SECONDS = 60
MAX_DURATION_HOURS = 3
MAX_SNAPSHOTS = MAX_DURATION_HOURS * 60  # 180 polls

BOOKMAKERS = ["draftkings", "fanduel", "betmgm", "caesars", "pinnacle"]

# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ── Main ─────────────────────────────────────────────────────────────────────

def format_lines(event) -> str:
    """One-line summary of best available price per side."""
    parts = []
    for team, outcomes in event.outcomes.items():
        best = min(outcomes, key=lambda o: o.implied_prob)
        label = "HOME" if team == HOME_TEAM else "AWAY"
        parts.append(f"{label} {team} → {best.book} {best.implied_prob:.4f}")
    return "  |  ".join(parts)


def run() -> None:
    client = OddsAPIClient()

    log.info("=" * 64)
    log.info(f"Live discovery run: {HOME_TEAM} vs {AWAY_TEAM}")
    log.info(f"Fixture ID : {FIXTURE_ID}")
    log.info(f"Poll every : {POLL_INTERVAL_SECONDS}s  |  Max duration: {MAX_DURATION_HOURS}h ({MAX_SNAPSHOTS} snapshots)")
    log.info(f"Books      : {', '.join(BOOKMAKERS)}")
    log.info(f"Output     : data/lines.csv  +  data/opportunities.csv")
    log.info("=" * 64)
    log.info("Press Ctrl+C to stop early.\n")

    snapshot_num = 0
    arb_count = 0

    for snapshot_num in range(1, MAX_SNAPSHOTS + 1):
        cycle_start = time.time()

        log.info(f"[snap {snapshot_num:>3}/{MAX_SNAPSHOTS}]  req #{client.request_count + 1}  fetching...")

        try:
            raw = client.fetch_fixture_odds(FIXTURE_ID, BOOKMAKERS)
        except QuotaWarning as e:
            log.warning(f"Quota limit reached: {e}")
            break
        except Exception as e:
            log.error(f"Fetch failed: {e}")
            # Don't exit — retry next cycle
            time.sleep(POLL_INTERVAL_SECONDS)
            continue

        events = normalize_events([raw])
        opportunities = find_arb_opportunities(events)

        # Log all lines every cycle
        log_lines(events, snapshot_num, raw)

        # Log arb opportunities when found
        if opportunities:
            log_opportunities(opportunities)
            arb_count += 1
            for opp in opportunities:
                log.info(
                    f"  *** ARB DETECTED  margin={opp.margin_pct:.4f}%  "
                    f"sum={opp.implied_prob_sum:.6f}"
                )
        else:
            for event in events:
                if event.outcomes:
                    best_per_side = {
                        team: min(outcomes, key=lambda o: o.implied_prob)
                        for team, outcomes in event.outcomes.items()
                    }
                    prob_sum = sum(o.implied_prob for o in best_per_side.values())
                    log.info(f"  no arb  sum={prob_sum:.6f}  {format_lines(event)}")

        # Sleep for the remainder of the interval
        elapsed = time.time() - cycle_start
        sleep_for = max(0, POLL_INTERVAL_SECONDS - elapsed)
        if snapshot_num < MAX_SNAPSHOTS:
            time.sleep(sleep_for)

    log.info("\n" + "=" * 64)
    log.info(f"Run complete.")
    log.info(f"  Snapshots collected : {snapshot_num}")
    log.info(f"  Arb windows found   : {arb_count}")
    log.info(f"  API requests used   : {client.request_count}")
    log.info(f"  Lines logged to     : data/lines.csv")
    log.info("=" * 64)


if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        print("\nStopped early by user.")

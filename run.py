"""
Poller — orchestrates the Phase 1 data collection loop.

Flow each cycle:
  OddsPapi → normalize → detect → log

Polling interval: every 3 minutes during active windows.
Budget: 250 requests/month ÷ ~20 polling sessions = ~12 requests/session max.
"""

import schedule
import time
import logging

from phase_1_discovery.poller.client import OddsAPIClient, QuotaWarning
from phase_1_discovery.normalizer.normalizer import normalize_events
from phase_1_discovery.detector.detector import find_arb_opportunities
from phase_1_discovery.logger.logger import log_opportunities

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

POLL_INTERVAL_MINUTES = 3


def poll_cycle(client: OddsAPIClient) -> None:
    log.info(f"Polling... (request #{client.request_count + 1} this session)")

    try:
        raw = client.fetch_nba_odds()
    except QuotaWarning as e:
        log.warning(str(e))
        return
    except Exception as e:
        log.error(f"Fetch failed: {e}")
        return

    events = normalize_events(raw)
    opportunities = find_arb_opportunities(events)

    if opportunities:
        log.info(f"  {len(opportunities)} arb opportunity(ies) found")
        log_opportunities(opportunities)
    else:
        log.info("  No arb opportunities this cycle")


def run() -> None:
    client = OddsAPIClient()
    log.info("Poller started. NBA odds, polling every 3 minutes.")
    log.info("Press Ctrl+C to stop.\n")

    # Run once immediately, then on schedule
    poll_cycle(client)
    schedule.every(POLL_INTERVAL_MINUTES).minutes.do(poll_cycle, client=client)

    while True:
        schedule.run_pending()
        time.sleep(10)


if __name__ == "__main__":
    run()

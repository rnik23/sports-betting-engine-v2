"""
Integration smoke test — runs the full pipeline against saved static data.

No API calls. Loads raw_fixtures.json + raw_odds_sample.json from
phase_1_discovery/research/, pipes them through normalize → detect → log,
and prints results at each stage.

Usage:
    source venv/bin/activate
    python scripts/run_pipeline_on_static_data.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from phase_1_discovery.normalizer.normalizer import normalize_events
from phase_1_discovery.detector.detector import find_arb_opportunities
from phase_1_discovery.logger.logger import log_opportunities

RESEARCH_DIR = Path("phase_1_discovery/research")


def load(filename: str) -> dict | list:
    path = RESEARCH_DIR / filename
    if not path.exists():
        print(f"  ✗ {filename} not found — run scripts/fetch_sample_response.py first")
        sys.exit(1)
    return json.loads(path.read_text())


def main():
    print("=" * 60)
    print("Pipeline smoke test on static data")
    print("=" * 60)

    # ── Load ─────────────────────────────────────────────────────
    print("\n[1] Loading static data...")
    fixtures = load("raw_fixtures.json")
    odds_sample = load("raw_odds_sample.json")

    fixture_list = fixtures if isinstance(fixtures, list) else fixtures.get("data", [])
    print(f"  fixtures:    {len(fixture_list)} games")
    print(f"  odds sample: 1 fixture ({odds_sample.get('participant1Name')} vs {odds_sample.get('participant2Name')})")

    # Build the input the pipeline expects: a list of /v4/odds responses.
    # We have one real odds payload; pad with fixture stubs (no bookmakerOdds)
    # so normalize_events sees all 6 fixtures.
    raw_pipeline_input = [odds_sample]
    for f in fixture_list:
        if f["fixtureId"] != odds_sample["fixtureId"]:
            raw_pipeline_input.append(f)  # no bookmakerOdds — will normalize to empty outcomes

    # ── Normalize ────────────────────────────────────────────────
    print("\n[2] Normalizing...")
    events = normalize_events(raw_pipeline_input)
    print(f"  {len(events)} events normalized")
    for e in events:
        outcome_count = sum(len(v) for v in e.outcomes.values())
        print(f"  {e.home_team} vs {e.away_team}  —  {outcome_count} outcome/book entries")
        for team, outcomes in e.outcomes.items():
            for o in outcomes:
                print(f"    {team:30s}  {o.book:12s}  implied_prob={o.implied_prob:.4f}")

    # ── Detect ───────────────────────────────────────────────────
    print("\n[3] Detecting arb opportunities...")
    opportunities = find_arb_opportunities(events)
    if opportunities:
        for opp in opportunities:
            print(f"  ✓ ARB FOUND: {opp.home_team} vs {opp.away_team}")
            print(f"    margin={opp.margin_pct:.4f}%  sum_prob={opp.implied_prob_sum}")
            for name, outcome in opp.best_outcomes.items():
                print(f"    best {name}: {outcome.book} @ implied_prob={outcome.implied_prob:.4f}")
    else:
        print("  No arb opportunities found (expected for real market data with vig)")

    # ── Log ──────────────────────────────────────────────────────
    print("\n[4] Logging...")
    log_opportunities(opportunities)
    if opportunities:
        print(f"  {len(opportunities)} opportunity(ies) written to data/opportunities.csv")
    else:
        print("  Nothing to log (no arbs detected)")

    print("\n✓ Pipeline ran end-to-end on static data with no errors")
    print("=" * 60)


if __name__ == "__main__":
    main()

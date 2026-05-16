"""
One-off exploration script — fetches real OddsPapi payloads and saves them
to phase_1_discovery/research/ so we can inspect the response shapes and
update the normalizer accordingly.

Cost: ~3 API requests (tournaments + fixtures + 1 odds call).
Sports are read from the already-saved raw_sports.json if it exists.
Run once, inspect the files, then keep for reference.

Usage:
    source venv/bin/activate
    python scripts/fetch_sample_response.py
"""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from phase_1_discovery.poller.client import OddsAPIClient

OUT_DIR = Path("phase_1_discovery/research")
OUT_DIR.mkdir(parents=True, exist_ok=True)

SLEEP = 0.6  # slightly above the 500ms API cooldown


def save(name: str, data) -> None:
    path = OUT_DIR / name
    path.write_text(json.dumps(data, indent=2))
    print(f"  saved → {path}  ({path.stat().st_size} bytes)")


def main():
    client = OddsAPIClient()
    print(f"API key loaded: {client.api_key[:8]}...\n")

    # Step 1 — sports (read from disk if already fetched, otherwise hit API)
    sports_file = OUT_DIR / "raw_sports.json"
    if sports_file.exists():
        sports = json.loads(sports_file.read_text())
        print(f"Step 1: sports loaded from disk ({len(sports)} sports)")
    else:
        print("Step 1: fetching sports list...")
        sports = client._get("/sports", {})
        save("raw_sports.json", sports)
        print(f"  {len(sports)} sports found")
        time.sleep(SLEEP)

    # Seed sport ID cache from local data — no extra API call
    for sport in sports:
        if "basketball" in sport.get("sportName", "").lower():
            client._nba_sport_id = sport["sportId"]
            break
    print(f"  NBA sport ID → {client._nba_sport_id}")

    # Step 2 — tournaments (seed cache directly, we already have this file too)
    tournaments_file = OUT_DIR / "raw_tournaments.json"
    if tournaments_file.exists():
        tournaments = json.loads(tournaments_file.read_text())
        print(f"\nStep 2: tournaments loaded from disk ({len(tournaments)} total)")
    else:
        print("\nStep 2: fetching NBA tournaments...")
        tournaments = client._get("/tournaments", {"sportId": client._nba_sport_id})
        save("raw_tournaments.json", tournaments)
        print(f"  {len(tournaments)} tournaments found")
        time.sleep(SLEEP)

    nba_tournaments = [t for t in tournaments if t.get("tournamentSlug") == "nba"]
    client._nba_tournament_ids = [t["tournamentId"] for t in nba_tournaments]
    print(f"  NBA tournament ID → {client._nba_tournament_ids}")

    # Step 3 — fixtures for NBA only (singular tournamentId, upcoming + has odds)
    print("\nStep 3: fetching NBA fixtures...")
    fixtures_raw = client._get("/fixtures", {
        "tournamentId": client._nba_tournament_ids[0],
        "statusId": 0,
        "hasOdds": "true",
    })
    save("raw_fixtures.json", fixtures_raw)
    fixture_list = fixtures_raw if isinstance(fixtures_raw, list) else fixtures_raw.get("data", [])
    print(f"  {len(fixture_list)} fixtures found")

    if not fixture_list:
        print("\nNo fixtures available right now (NBA off-season or no scheduled games).")
        print("Sports and tournament shapes saved — enough to validate discovery.")
        print(f"\nTotal requests used: {client.request_count}")
        return

    time.sleep(SLEEP)

    # Step 4 — find the first fixture that actually has bookmaker odds posted
    print("\nStep 4: scanning fixtures for live odds...")
    odds = None
    for fixture in fixture_list:
        fixture_id = fixture.get("fixtureId")
        p1 = fixture.get("participant1Name", "?")
        p2 = fixture.get("participant2Name", "?")
        print(f"  trying {fixture_id} ({p1} vs {p2})...")

        candidate = client._get("/odds", {
            "fixtureId": fixture_id,
            "bookmakers": "draftkings,fanduel,betmgm,pinnacle",
            "oddsFormat": "american",
            "language": "en",
            "verbosity": 3,
        })
        time.sleep(SLEEP)

        if candidate.get("bookmakerOdds"):
            odds = candidate
            print(f"  ✓ odds found for {fixture_id}")
            break
        print(f"  ✗ no bookmakerOdds yet")

    if odds:
        save("raw_odds_sample.json", odds)
    else:
        print("  No fixtures with live odds found yet — odds may not be posted for upcoming games.")

    print(f"\nDone. Total requests used this session: {client.request_count}")
    print(f"\nFiles written to {OUT_DIR}/:")
    for f in sorted(OUT_DIR.glob("raw_*.json")):
        print(f"  {f.name}")


if __name__ == "__main__":
    main()
